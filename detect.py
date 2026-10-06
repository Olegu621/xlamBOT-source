import time
import threading
import os
from contextlib import nullcontext

import cv2
import numpy as np
import onnxruntime as ort
from utils import load_toml_as_dict
import warnings

# GPU drivers share process-wide resources. Serializing creation and inference
# also avoids a second device creating a DirectML session during another run.
_GPU_RUNTIME_LOCK = threading.RLock()

warnings.filterwarnings(
    "ignore",
    message=".*'pin_memory' argument is set as true but no accelerator is found.*",
    category=UserWarning
)


def _numpy_nms(boxes, scores, iou_threshold=0.6):
    if len(boxes) == 0:
        return np.array([], dtype=np.int32)

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]

    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]

    keep = []

    while order.size > 0:
        i = order[0]
        keep.append(i)

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)

        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)

        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]

    return np.array(keep, dtype=np.int32)


def _normalize_yolo_output(raw_output):
    """
    Accepts either:
        outputs
        outputs[0]

    Supports common YOLO ONNX shapes:
        (1, 84, 8400)
        (1, 8400, 84)
        (84, 8400)
        (8400, 84)

    Returns:
        prediction with shape (num_boxes, num_channels)
    """

    if isinstance(raw_output, (list, tuple)):
        prediction = raw_output[0]
    else:
        prediction = raw_output

    prediction = np.asarray(prediction)

    if prediction.ndim == 3:
        prediction = prediction[0]

    if prediction.ndim != 2:
        raise ValueError(f"Unexpected YOLO output shape: {prediction.shape}")

    # YOLOv8 ONNX often gives (84, 8400), needs transpose to (8400, 84)
    if prediction.shape[0] < prediction.shape[1] and prediction.shape[0] <= 256:
        prediction = prediction.T

    return prediction


def _postprocess_raw(raw_output, conf_tresh=0.6, iou_thresh=0.6):
    prediction = _normalize_yolo_output(raw_output)

    n_detections = prediction.shape[0]
    n_classes = prediction.shape[1] - 4

    if n_classes <= 0:
        return []

    boxes_cxcywh = prediction[:, :4]
    class_scores = prediction[:, 4:]

    class_ids = np.argmax(class_scores, axis=1)
    confidences = class_scores[np.arange(n_detections), class_ids]

    mask = (confidences >= conf_tresh) & np.isfinite(prediction).all(axis=1)
    mask &= (boxes_cxcywh[:, 2] > 0) & (boxes_cxcywh[:, 3] > 0)

    if not np.any(mask):
        return []

    boxes_cxcywh = boxes_cxcywh[mask]
    confidences = confidences[mask]
    class_ids = class_ids[mask]

    x1 = boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] / 2
    y1 = boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] / 2
    x2 = boxes_cxcywh[:, 0] + boxes_cxcywh[:, 2] / 2
    y2 = boxes_cxcywh[:, 1] + boxes_cxcywh[:, 3] / 2

    boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)

    results = []

    for cls in np.unique(class_ids):
        cls_mask = class_ids == cls

        cls_boxes = boxes_xyxy[cls_mask]
        cls_scores = confidences[cls_mask]

        keep = _numpy_nms(cls_boxes, cls_scores, iou_thresh)

        if len(keep) == 0:
            continue

        kept_boxes = cls_boxes[keep]
        kept_scores = cls_scores[keep]
        kept_cls = np.full((len(keep), 1), cls, dtype=np.float32)

        det = np.hstack(
            [
                kept_boxes,
                kept_scores.reshape(-1, 1),
                kept_cls,
            ]
        ).astype(np.float32, copy=False)

        results.append(det)

    return results


class Detect:
    def detect_objects(self, *args, **kwargs):
        with self._inference_lock:
            started = time.perf_counter()
            try:
                return self._detect_objects(*args, **kwargs)
            finally:
                self.last_inference_ms = (time.perf_counter() - started) * 1000

    def __init__(self, model_path, ignore_classes=None, classes=None, input_size=(640, 640)):
        self._inference_lock = threading.RLock()
        threads_to_use = load_toml_as_dict("cfg/general_config.toml")['used_threads']

        def get_optimal_threads(max_limit=6):
            threads = os.cpu_count()
            threads_amount = min(max(2, threads // 2), max_limit)
            return threads_amount

        # Each device loads several ONNX sessions. A large pool per session
        # oversubscribes the CPU when two emulators run together.
        self.optimal_threads_amount = min(2, get_optimal_threads()) if threads_to_use == "auto" else max(1, min(16, int(threads_to_use)))
        print(f"Using {self.optimal_threads_amount} CPU threads per detector.")
        self.preferred_device = str(
            load_toml_as_dict("cfg/general_config.toml").get("cpu_or_gpu", "auto") or "auto"
        ).strip().lower()
        self.model_path = model_path
        self.last_inference_ms = 0.0
        self.last_detections = []
        self.classes = classes
        self.ignore_classes = set(ignore_classes) if ignore_classes else set()
        self.input_size = input_size
        self.model, self.device = self.load_model()
        self.input_name = self.model.get_inputs()[0].name
        self._padded_img_buffer = np.full(
            (1, 3, self.input_size[0], self.input_size[1]),
            128.0 / 255.0,
            dtype=np.float32
        )

    def load_model(self, cpu_only=False):
        available_providers = ort.get_available_providers()
        providers = []

        if not cpu_only and self.preferred_device in ("gpu", "auto"):
            if "CUDAExecutionProvider" in available_providers:
                providers.append("CUDAExecutionProvider")
            if "DmlExecutionProvider" in available_providers:
                providers.append("DmlExecutionProvider")

        providers.append("CPUExecutionProvider")
        if self.preferred_device == "cpu":
            providers = ["CPUExecutionProvider"]

        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.intra_op_num_threads = self.optimal_threads_amount
        so.inter_op_num_threads = 1
        if "DmlExecutionProvider" in providers:
            so.enable_mem_pattern = False
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        try:
            with _GPU_RUNTIME_LOCK if len(providers) > 1 else nullcontext():
                model = ort.InferenceSession(self.model_path, sess_options=so, providers=providers)
        except Exception:
            if providers == ["CPUExecutionProvider"]:
                raise
            print(f"GPU initialization failed for {os.path.basename(self.model_path)}; using CPU.")
            return self.load_model(cpu_only=True)

        used_provider = model.get_providers()[0]
        if used_provider == "CUDAExecutionProvider":
            print("Using CUDA GPU")
        elif used_provider == "DmlExecutionProvider":
            print("Using GPU")
        elif self.preferred_device != "cpu":
            print("Using CPU as no GPU provider found")

        return model, used_provider

    def preprocess_image(self, img):
        if img is None or getattr(img, 'ndim', 0) != 3 or img.shape[2] != 3 or not img.size:
            raise ValueError('Detector requires a non-empty RGB image')
        h, w = img.shape[:2]

        scale = min(self.input_size[0] / h, self.input_size[1] / w)
        new_w = max(1, min(self.input_size[1], int(w * scale)))
        new_h = max(1, min(self.input_size[0], int(h * scale)))

        resized_img = cv2.resize(
            img,
            (new_w, new_h),
            interpolation=cv2.INTER_LINEAR
        )

        # A previous square crop must not remain below a later widescreen frame.
        self._padded_img_buffer.fill(128.0 / 255.0)
        # Normalize directly into the reusable planar tensor. uint8 + float32
        # retains the original float32 rounding without a full RGB float copy.
        if resized_img.dtype not in (np.dtype(np.uint8), np.dtype(np.float32)):
            resized_img = resized_img.astype(np.float32, copy=False)
        np.multiply(resized_img.transpose(2, 0, 1), np.float32(1.0 / 255.0),
                    out=self._padded_img_buffer[0, :, :new_h, :new_w])

        return self._padded_img_buffer, new_w, new_h

    def postprocess(self, raw_output, orig_img_shape, resized_shape, conf_tresh=0.6):
        detections = _postprocess_raw(
            raw_output,
            conf_tresh=conf_tresh,
            iou_thresh=0.6
        )

        orig_h, orig_w = orig_img_shape
        resized_w, resized_h = resized_shape

        scale_w = orig_w / resized_w
        scale_h = orig_h / resized_h

        results = []

        for det in detections:
            if len(det):
                det[:, 0] *= scale_w
                det[:, 1] *= scale_h
                det[:, 2] *= scale_w
                det[:, 3] *= scale_h
                det[:, [0, 2]] = np.clip(det[:, [0, 2]], 0, orig_w)
                det[:, [1, 3]] = np.clip(det[:, [1, 3]], 0, orig_h)
                valid = (det[:, 2] > det[:, 0]) & (det[:, 3] > det[:, 1])
                if np.any(valid):
                    results.append(det[valid])

        return results

    def _detect_objects(self, img, conf_tresh=0.6):
        orig_h, orig_w = img.shape[:2]

        preprocessed_img, resized_w, resized_h = self.preprocess_image(img)

        try:
            with _GPU_RUNTIME_LOCK if self.device in ("DmlExecutionProvider", "CUDAExecutionProvider") else nullcontext():
                outputs = self.model.run(None, {self.input_name: preprocessed_img})
        except Exception:
            if self.device not in ("DmlExecutionProvider", "CUDAExecutionProvider"):
                raise
            # A GPU shared with multiple emulators may run out of resources.
            # Some Windows drivers even fail to decode their native error.
            # Retry this frame once on CPU, retaining CPU for this session.
            print(f"GPU inference failed for {os.path.basename(self.model_path)}; switching this detector to CPU.")
            self.model = None
            self.model, self.device = self.load_model(cpu_only=True)
            self.input_name = self.model.get_inputs()[0].name
            outputs = self.model.run(None, {self.input_name: preprocessed_img})

        detections = self.postprocess(
            outputs,
            (orig_h, orig_w),
            (resized_w, resized_h),
            conf_tresh
        )

        results = {}
        self.last_detections = []

        for detection in detections:
            for row in detection:
                if not np.isfinite(row[:6]).all():
                    continue
                x1, y1 = max(0, int(row[0])), max(0, int(row[1]))
                x2, y2 = min(orig_w, int(row[2])), min(orig_h, int(row[3]))
                if x2 <= x1 or y2 <= y1:
                    continue
                class_id = int(row[5])

                if self.classes is None:
                    class_name = str(class_id)
                else:
                    if class_id < 0 or class_id >= len(self.classes):
                        print(
                            f"WARNING: class_id {class_id} is out of range "
                            f"(classes length: {len(self.classes)}). Detection ignored."
                        )
                        continue

                    class_name = self.classes[class_id]

                if class_id in self.ignore_classes or class_name in self.ignore_classes:
                    continue

                if class_name not in results:
                    results[class_name] = []

                results[class_name].append([x1, y1, x2, y2])
                self.last_detections.append({"class": class_name, "box": [x1,y1,x2,y2], "confidence": float(row[4])})

        return results

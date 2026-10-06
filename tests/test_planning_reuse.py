"""Exact safety decisions while sharing one immutable gas observation."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import navigation_safety as nav
from play import Play
from detect import Detect

spec = importlib.util.spec_from_file_location('navigation_revision32', ROOT/'tests/fixtures/navigation_revision32.py')
reference = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reference; spec.loader.exec_module(reference)


class PlanningReuseTests(unittest.TestCase):
    def test_input_tensor_is_identical_across_sizes_and_dtypes(self):
        detector = Detect.__new__(Detect)
        detector.input_size = (640, 640)
        detector._padded_img_buffer = np.empty((1,3,640,640), np.float32)
        rng = np.random.default_rng(33)
        for shape, dtype in [((640,640,3),np.uint8), ((720,1280,3),np.uint8),
                             ((400,180,3),np.uint8), ((91,200,3),np.float64),
                             ((192,80,3),np.float32), ((720,1280,3),np.uint8)]:
            image = rng.integers(0,256,shape,dtype=np.uint8).astype(dtype)
            scale = min(640/shape[0], 640/shape[1])
            w, h = max(1,int(shape[1]*scale)), max(1,int(shape[0]*scale))
            rgb = cv2.resize(image,(w,h),interpolation=cv2.INTER_LINEAR).astype(np.float32)
            np.multiply(rgb,1/255,out=rgb)
            expected = np.full((1,3,640,640),128/255,np.float32)
            expected[0,:,:h,:w] = rgb.transpose(2,0,1)
            actual, aw, ah = detector.preprocess_image(image)
            self.assertEqual((aw,ah),(w,h))
            np.testing.assert_array_equal(actual,expected)

    def test_all_budgets_preserve_every_direction_and_score(self):
        rng = np.random.default_rng(33)
        for count, steps in [(8, 2), (8, 3), (12, 3), (16, 4), (24, 5)]:
            old, new = reference.MovementArbiter(), nav.MovementArbiter()
            old.direction_count = new.direction_count = count
            old.planning_steps = new.planning_steps = steps
            for i in range(12):
                mask = rng.integers(0, 256, (90, 160), dtype=np.uint8)
                params = dict(center=(80+i, 45), radius=3.7, tile=8, mask=mask,
                              walls_block=lambda m, d: m[0] < -.5 and d >= 16,
                              frame_size=(160, 90), escape=bool(i%2),
                              observed_y=(12, 90), enemies=[(110, 20)], teammates=[(70, 40)])
                desired = (0., 0.) if i%3 == 0 else (12.3, -7.1)
                self.assertEqual(new.choose(desired, **params), old.choose(desired, **params))
                params['mask'] = nav.prepare_gas_mask(mask)
                actual = new.choose(desired, **params)
                params['mask'] = mask
                self.assertEqual(actual, old.choose(desired, **params))

    def test_new_observation_and_resize_cannot_reuse_stale_sums(self):
        p = Play.__new__(Play)
        p.gas_mask = np.zeros((90, 160), np.uint8)
        first = p.gas_risk_mask()
        self.assertIs(p.gas_risk_mask(), first)
        p.gas_mask = np.full((90, 160), 255, np.uint8)
        second = p.gas_risk_mask()
        self.assertIsNot(second, first)
        self.assertEqual(nav.patch_share(second, 80, 45, 4), 1.)
        self.assertEqual(nav.patch_share(first, 80, 45, 4), 0.)
        p.gas_mask = np.zeros((45, 80), np.uint8)
        self.assertEqual(p.gas_risk_mask().shape, (45, 80))
        p.gas_mask = None
        self.assertIsNone(p.gas_risk_mask())
        self.assertIsNone(p._gas_risk_source)

    def test_first_wall_step_checked_once_per_candidate(self):
        checks = []
        def walls(move, distance):
            checks.append((move, distance))
            return False
        nav.MovementArbiter().choose((2, 3), mask=None, center=(80,45), radius=4,
                                    frame_size=(160,90), tile=8, walls_block=walls)
        self.assertEqual(len(checks), 9*3)
        self.assertEqual(len(checks), len(set(checks)))

    def test_integral_uses_wide_sums_above_int32_capacity(self):
        # A broadcast view needs no large input allocation. Mock only the kernel.
        small = nav.prepare_gas_mask(np.zeros((90, 160), np.uint8))
        self.assertEqual(small.sums.dtype, np.int32)
        large = np.broadcast_to(np.uint8(255), (2161, 4096))
        with patch.object(nav.cv2, 'integral', return_value=None) as integral:
            nav.prepare_gas_mask(large)
        integral.assert_called_once_with(large, sdepth=nav.cv2.CV_64F)


if __name__ == '__main__': unittest.main()

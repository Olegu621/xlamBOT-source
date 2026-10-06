"""Recognize the Team Up overlay from stable heading and close-button artwork.

Templates are cropped from the user-provided game screenshot. No usernames or
account details are embedded. Matches use device pixels, independent of language
preference and per-device button calibration.
"""
import base64
from functools import lru_cache
import cv2
import numpy as np

HEADING = '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'
CLOSE = 'iVBORw0KGgoAAAANSUhEUgAAABkAAAAUCAIAAAD3FQHqAAACm0lEQVR4nKVUX0hTYRQ/59673bGmU+d0bPgvh5YZNXswfZB8yocIJHxo9hK+RS8F9raegl4kEKKHICpwCiL1FoFaSLAkiuwlKL3Trbl/urF/bk63fXG/O6fde1/Sw8d3z+/8+X3n+zj34BnHSwACJRR3QhAQQFTpTqgLABARsEShGMbQXQoQvVAiSK0UILWKGdRQ5kPqkmjFc8oW6agypJFU576cX4DjCsOxvMHAAD7+tjIddmJ8ZBhOJqfqavcJd2neziV9gtJdAhjwRXTFwvxpm3SNfImM+UNTrVZlcNIHqeoGwE7pveRydTMWCIfXtrZvbIQA4Hdud/b6yFIwfM/7RzXeG/IisipcN7PF1UBA0r+GwsPrQdvMG5fLxbLs85+/llM7ypSPiSwiy8ms09HY+MRkBTIM8z26VYFms9ltP3s56pdleTJZ1Cvq6qs2jN8a9Xg8qndxOp0bHxaV9pWdHDIaeV1tOv6pvXl48Eowm2NZ9qjr2tCQ8GnpXXeHkovQPlV5r4XM7g+fX0YEAK/d7gFj1WEvHxGG4QAVXK8i2xNen8ViUSaYTKYnq+uP/EEVLjSo1BXbL3R3dVXgbi6XSiYrkOf5mURGyaXR1FOugx9WWvdtFj7g73U4ACCdTttra9rMZikhHo/bDIZenVaWki8SjbYeABkiTofDBQRmO9uJsNrf39/T2PCwyTrWaLIajW/n5nps1ruN9S/srbKUZKGo17eLE0a4eEFZc4GQMe+6y2a163QA8CwSeZ9ITrQ0d1AoEyGfv7N/W6s14do5Fa7/ksVUbrLqAQBwwmbTCbk+7wlQJSrcciF6fBqCieLeVCFI25cgr28RP8y/PSg+qjR/6SRFLE/tg0laEp+dQuSMNX11tYMA8Be0yQ5r4AJxzgAAAABJRU5ErkJggg=='
REFERENCE_SIZE = (445, 247)

@lru_cache(maxsize=24)
def _template(encoded, width, height):
    image = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), np.uint8), cv2.IMREAD_COLOR)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return cv2.resize(image, (max(1, round(image.shape[1]*width/REFERENCE_SIZE[0])),
                              max(1, round(image.shape[0]*height/REFERENCE_SIZE[1]))))

def _match(frame, encoded, bounds):
    height, width = frame.shape[:2]
    x1,y1,x2,y2 = bounds
    left,top = int(width*x1),int(height*y1)
    crop = frame[top:int(height*y2),left:int(width*x2)]
    template = _template(encoded,width,height)
    if crop.size == 0 or any(crop.shape[i] < template.shape[i] for i in (0,1)):
        return 0.,None
    score,location = cv2.minMaxLoc(cv2.matchTemplate(crop,template,cv2.TM_CCOEFF_NORMED))[1::2]
    return score,(left+location[0]+template.shape[1]//2,top+location[1]+template.shape[0]//2)

def team_panel_close_position(frame, russian_heading=False):
    """Return the visible close-button center only with positive overlay evidence."""
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        return None
    if not russian_heading:
        heading_score,_ = _match(frame,HEADING,(.46,0,.80,.10))
        if heading_score < .85:
            return None
    close_score,position = _match(frame,CLOSE,(.88,0,1.,.13))
    return position if close_score >= .80 else None

"""Recognize the English Idle Disconnect dialog from user-provided evidence."""
import base64
from functools import lru_cache

import cv2
import numpy as np

TITLE = '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'
RELOAD = 'iVBORw0KGgoAAAANSUhEUgAAAD0AAAASCAIAAABn+kFdAAAEEUlEQVRIDdXBXUxTdxgH4N8f2rVIWRm0jLBOmZmHU9rCHAGHCVnyJkt2YezwpNLCmGwzS9wNZkaNuji6jALWwLoITISAG8Zs2cY2l31ly5Y5i6VB+XLKh3OJoogCppS2tqecJU246F0v9KLPw4gISYgREZIQIyIkIUZESEKMiPBIpcjlkKRVUcTjxIgI8Z5/bVtu6YsApGjUf2fu+vc/+WdvF9Zas3gOa6YHzq1GxIKdlRc/OiYGQ4hJlcv5aksWzzHGFq5NTX9zLuzzYc1L7x9Ympqe/HIAMQU7d2iLjQAifv8dz/Ct8+7VSAQJY0SEeJxg1hQZL7k6ZErlph3bn8hQeZpbjbuq5Rmqq/1fICayEsg26Hmr4G5wiMEQAMbY5vo9MoViordfkqTCmqpIIDDW1YsY9XMbTLt3sZSUi43OiH8FgN5myVivG+vqU+XlbhK23xu7MvPtD0gYIyLE4wSzxmRw25sgSbllJZxgdjc08VU7UtOUo509WJOzuZi3Cu4GhxgMAZCnp5cfPeh1uoL3FwBk8Zzxzdc9jccf+nxgrOzA3qXJ6ad47r9ffp+/PApAb7OodHlepwtAtkFveMM21NIWWlxCYhgRIR4nmDVFBu8xF4Cid+qkaPTSJ58a62rUG/P9c/OIGe/u0xgKeavgbnCIwRAAhVq95fA+t71ZDAQAKDMzyw69d6XvzMLVSVmasvyDQ0PNrfmv0Loc7eX2LgB6m0Wly/M6XYipaLaPd59+MPMvEsOICPE4wZxbVoKYlbm7I+2nouGwsa4mTau5+ed5xNy9NKItMvFWwd3gEIMhAAq1esvhfYP25kggAECZqS47tG+i78zi1UldxdaN2179+4hdoc4sPVA/7OpYuT2nt1lUujyv04WYimb7ePdnD2auIzGMiBCPE8wak8HjcGpMBs5SOdx6IjB/z1hXk5qmHO3swZqczcW8VXA3OMRgCIA8Pb386EHvsY+DC4sAsgo2Gd+q9TQej6ysbLUfSZGlRsNhAKkKxc0//rrx8296m0Wly/M6XQC0RQZ9TdVQS1tocQmJYUSEeJxg1pgMbnsTJKl0f/3yrdlrZ78y1tXI0tdd6e1HjBiOaE0G3ioMtbRFQyEAkoTiPbtlSsVIe5e0KhnfrhWDwbGTveuezinZ++5wW/tqNApAV1GeXaj3OI7rbZaMZ5+5fOLkk/kbOEvl/bGJ6YFzSBgjIsTjBLPGZHDbmyBJ2iKjvtoy0nFqPb2cpS/Amhs//vrQt8xbBazx374z2tnDV1uyCjjGsDg5PfX1d2HfMmepzC4sGPywBZIEIE2TXbq//p/Pz2pNRu0LJgBh3/LshcHZC57VSAQJY0SER0qmVAIQQyE8ToyIkIQYESEJMSJCEmJEhCT0P4B4oA7vJIbjAAAAAElFTkSuQmCC'
REFERENCE_SIZE = (680, 380)


@lru_cache(maxsize=24)
def _template(encoded, width, height):
    image = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), np.uint8), cv2.IMREAD_COLOR)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return cv2.resize(image, (max(1, round(image.shape[1] * width / REFERENCE_SIZE[0])),
                              max(1, round(image.shape[0] * height / REFERENCE_SIZE[1]))))


def _match(frame, encoded, bounds):
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = bounds
    left, top = int(width * x1), int(height * y1)
    crop = frame[top:int(height * y2), left:int(width * x2)]
    template = _template(encoded, width, height)
    if crop.size == 0 or any(crop.shape[i] < template.shape[i] for i in (0, 1)):
        return 0.0, None
    result = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(result)
    return score, (left + location[0] + template.shape[1] // 2,
                   top + location[1] + template.shape[0] // 2)


def idle_disconnect_reload_position(frame):
    """Return RELOAD center only when the title and button are both visible."""
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        return None
    title_score, _ = _match(frame, TITLE, (.18, .28, .58, .49))
    reload_score, position = _match(frame, RELOAD, (.18, .48, .48, .69))
    if title_score < .84 or reload_score < .78:
        return None
    return position

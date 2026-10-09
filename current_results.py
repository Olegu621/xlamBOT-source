"""Recognize the current fourth-place result with a confirmed Proceed control."""
import cv2
import numpy as np
from reward_receipts import _valid, _find, _glyph

RANK_FOUR = 'iVBORw0KGgoAAAANSUhEUgAAAQQAAABWCAAAAAAMUreeAAAFB0lEQVR4Ae3BAXaDSBIFwcz7H/qvaBBVjZGQ38i7nrUi5AP5QD6QD+QD+UD+oIA08neERor8CeFIivwF4Qsp8heEI2nk1wkLeZ/whTTyq4SdvEv4Shr5TUKRNwknpJHfJBR5j3BGGvlNQpH3CCekk18kFHmPcEY6+UVCkbcIp6STZ0IjPy0UeYtwSjr5IjwkPyoUeYdwSiZyFJ6RHxSKvEE4JxM5Ck/JjwlF3iA8IBM5Cs/JTwlF3iDsDI1M5ChckB8SivxzoRgamchBuCI/JBS5EgZ5JBQJRWZyEK7IDwlFurCQVWjkgVCEUGQmB+GS/IhQZBOKrEIjD4SdQCgyk4NwSX5EKLIKRTahkXOhCKGRmRyES/LPhI10ocgQimxCI+dCEQiNzGQWrsm3hBvZhE5KKDKEndyFRk6FIjehyIHMwiX5Kqzki7CSm3Agd6HIEIrchUZOhZ0sQpEDmYVGFmEmszCRSbgTwheyCUUWocguNHImFFmEIgcyC40MYSIlfCVNuCCbUOQmFCmhkROhyCI0ciCz0MgQJrILZ6SEK7IKRW7CTkpo5EQoMoRGDmQSOlmFTu7CKdmFS7IKRSDspAmNnAg7WYUiRzIJjWxCI7twTu7CJRlCEQhFmtDIV6HIKhQ5kkloZBMa2YVzchcuyRCKEIp0oZEvQpFNKHIkk9DIKnSyC+fkLlySIRQh7KQLjXwRimzCkTTShU5WoZESzslduCRDKBJ2MgsLeSC8RBrpQidDaKQJKwmdbMI1GUIx7ORbwmukkS40MoROmoBsQpG7cCA3ocgQHpBvCa+RRrrQyCJ08kgochcmMoQiQzgn3xNeIp10oREIE3koFGlCkSEUGcI5+Z7wEumkCRfkkVCkC0WGUGQI5+R7wkukkyY8JafCgTShkSEUGcI5+Z7wEumkCc/IUTglTSiyCjsZwiPyPeEFMpEmPCEH4QFpQpEhFBnCI/I94QUykSY8IZPwkDShyBCKDOER+Z7wAplICc9IFx6SLhQZQpEhFEMn3xOekRNSwjPShMekCY0MYSdDKEJopAtFTgWkhE5OSAlPyS48IU0osgo7GUIRQiNNaOQVoZMTUsJTchc6gVCkCUWGUGQIRQidlNDIC8JETkgJjRBmsglFFqFIE4oMocgQihA62YVGXhEmckJ2oRPCTDZhJ0PYSReKDKHIEIoQOtmFRl4ROjkju9AIhJmsQpFFKNKERoawkyEUuQmd3IVGXhE6OSO70MhNmMkQiixCIyUUWYWdDKHITejkLjTygjCRM7ILjdyEmSxCI4swk00oMoQiQyhyEzrZhEZeESZyRu5CJzdhJovQyE04kE0oMoQiQyhyEzrZhEZeETo5JXehk5twIDehE8KRrEIjQygyhJ0MoZNVaOQVoZFzchcaGcJMbsI1GUKRVdjJEIoMoZNVaOQ1YSFPyF1oZAgHAuGSrEKRIRQZQpEhTGQIjbyN3IVGhnAgEC7JKhQZQpEhFBnCRBahkfeRTehkCAdyEy7IJhQZQpEhFFmFThZhJ+8km9DJEA7kJlyQVWhkCEUWocgmLOS/QjahkU2YyCJckFUosgo7GcJG/kdkExrZhE5W4UgId7IJRVZhkF9ENqGRTSiyCzO5CSsp4UZ+OVmFTjZhJ01oZBUW8q8jq9DJXVjJLGzk309WoZFdWMj/NVmFIn+MfCAfyAfygXwgH8gH8oF8IB/IB/KBfCAfyAf/AUUZhGafw7/PAAAAAElFTkSuQmCC'
PROCEED = 'iVBORw0KGgoAAAANSUhEUgAAAI8AAAAfCAAAAAD7bsEMAAACAElEQVRYCc3BUYLqOBAEMNX9D13bNsTJLLx/pPgt8Vvit8RWL/FWb/FQWzzVFqOOoI6g3uJfYqsjlrrFSx1xqUtQR1BHULf4Kra6xaiHWOohXuoI6gjqCOohvomtHoJ6iFF/xFK3oI6gjqCe4ovY6iGop1D/E6OOGHUEdQT1FF/EViPUEmqEWkJtobagtqAxasSlRlxqRL3Ep9hqhFpCjVBLqCVGLUEtcdSIS4241AhqiU+x1Qi1hBqhlqglthpBjbjViEuNuNQIaolPsdUItYQaoZaoJbZaopa41RJvtcRbjaCW+BRbjaglqBG1hFpiqyVqiVu9xVJvsdSIUSM+xVYPQd2CWmKrJWqJW73FUm+x1IhRIz7FVrcYdQtqia2WqCVu9RZLvcVSI6glPsVWRyx1C2qJrZaoJW414lIjLjWCWuJTbHWJrUZqiVEjllqCWuKoEZcacakR1BKfYqsljhpRS1BLjFqCWuKoEZcacakR1BKfYqsRtxpRS1Bb1EtQL1GCGnGpEZcaUVt8EVuNuNUItQT1Ryx1C+oI6gjqKb6IrUbcaoTaQv0RSz2EOoI6gnqIb2KrEbcaQS1BPcRL3UIdQR1B3eKr2GrErUZQxEu9xVGXoI6gjqCO+C5eSjyVWCqOGvFXjdjqEqMuMWqJf4vfEr8lfkv8lvgt8Vvit/wHuqW9IO31SN8AAAAASUVORK5CYII='


def current_fourth_place(frame):
    if not _valid(frame):
        return False
    h,w=frame.shape[:2]
    crop=frame[:round(h*.18),:round(w*.30)]
    yellow=((crop[:,:,0]>200)&(crop[:,:,1]>200)).astype(np.uint8)*255
    glyph=_glyph(RANK_FOUR,h)
    if not np.any(glyph) or np.all(glyph):
        return False
    if any(yellow.shape[i]<glyph.shape[i] for i in (0,1)):
        return False
    score=cv2.minMaxLoc(cv2.matchTemplate(yellow,glyph,cv2.TM_CCOEFF_NORMED))[1]
    if score<.9 or _find(frame,PROCEED,(.77,.84,1,1)) is None:
        return False
    button=frame[round(h*.88):round(h*.97),round(w*.8):round(w*.97)]
    blue=(button[:,:,0]<85)&(button[:,:,1]>60)&(button[:,:,2]>170)
    return bool(blue.size and blue.mean()>.4)

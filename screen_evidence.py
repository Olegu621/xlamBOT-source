"""Local UI evidence independent of game scenery and ADB transport type."""
import base64
from functools import lru_cache
import cv2
import numpy as np

MENU = "iVBORw0KGgoAAAANSUhEUgAAABAAAAALCAIAAAD5gJpuAAAB9UlEQVQoFQXBy2sTQRwA4PnNzs5uJllN3KZNxNrWnrRYG2ii+CrtRZBKkVJasSf9PzwoaBE8i+DdHMSjHjwq2oM30SKoUK1WA1uT7Gtmdh5+H7TbK9oaz3MRMjc3N5aXr2LHCpFTj/w7GGhtCXF/7e13u88/f9oxBsGF8zdymQRBuVB8dXVlcemykGmWJRhDGI7EcUpdv9eLus9efP+2izGBc2fXCcU5H/QH0eLSpdHRcP/PT+ICxiiKojTNj9TGtIL37z5Qt9wYOwbtzprnkTTpT0wevXvvzqmZ41wo3yMWaUCgrHXA2d7+uPXg0d7vv7VqHVqd1SqrSJ4gKM7MnRwZqUQHPYSUEIL63jDhgL3hINv58rXRHM+yHGY710CYPB6emB5f37g+OdGIk35wqIQAlLFBpVYOqm/ebj9+8tSlfqlUhtn2lTKp8Cxpz7du3d6cnGpqI+v1EADihLsuBYe+fPX6/tbDLBeEUJhpLXi41I8OAOn6aE3IJEkGvu9LKWthKLgODteMsbs/9uqNJmMMTrcueiQAwDyLrS2IC8YojLHjOACO4EojoJQqbR3qSslhbn6Bp4qxQGvpgGXM5yJP07TkszTNGatIZay1rkcwRtoUMDU9ZxE12hZK6kISQgAAIcRYRSntEq8oCllwhKxUuUX6P2tC9cYdgzqtAAAAAElFTkSuQmCC"
KNOCKOUT_RU = "iVBORw0KGgoAAAANSUhEUgAAACcAAAALCAIAAABzrwMvAAAEvklEQVQ4EU3Bf0yUZRwA8O/zvO+9d+/73nEch6fdCZ5x2IlMA9OmKWpOZUOTFE1THCtnhOlUBLLMHxXODVNRfiQojsyQnFo5yZZOYaXzSKs1t8QTcCCQ5/3+fe/7Pk9l/tHng/Lzi4AiggCAwv8wCMEzBAADEAIYEEFEgWcwAAaKCAIADAgBAMMwGGOWZf2hMKfSUEolOc5xnJKQGIRVHBOLxQwGAypcUsrxgiTLoXBA1Oki0ZAcT+h0IgKIhSN6vT4cDqk0GklKEArAIAZRqhCO46OReEqKyf3EK4piPBEFkDEDlMroX4wkKzwvRhNxihkAwARUlGBKACgAoOxJBYFgOHV0Ki8KIyPD+mSd0Wjo+fOeXtRyTz1+/NhoNEZiUV6njURCao6NBEMArCHZGAiEOZUGM0ApUbHgD3q0OpFlMSFACAmHIoxaAyoVALAKMJRgIIjCP1DOtMIxz1n+co1Eo1FeUCNEg0G/xWwO+kOgEAAQBEEjCgODgwZjSjwejUaCKQaDKOhcrieJhJykSw4GgyqO0WvFYCQEiGAMiqIghCRJGWUyeXxeggBTAMCIwn/Q1BlLg+GQWq3S8Gqv1z3Omvawr1+tVvu9Adt4WygU8vl8CVnJfCHzvvMBw8LYsSa325WISRqBt4yxOByO7OzJkiT19jptNpvH4+G1fMDnZ1RYr0saHBq2Wq1AkYJYCpggBBRjADRvyZrumzfq6o4IIl9SsvazgzVaQSzfUn6ypTVjvC0SiX7x5ambN241NjVWVFSljjKUbVy/44PK/gfO5pYTaWZLTU3NnDnzHg0OnznTXl1dPTQ0NGGiPcNqFfViwOuprzt288YdAioCjIRZgjABjAFQXkHRvbt3P284qksSyrduqq095PP4Ozo6du7YdejQ4UULC1iW3f3x3s7Oy+XlO/PzF3q8rqqqislTsk6fPtXX19fb2+v1+nNzXqqq+rCh/tj+/fvj8Xhl5fYkvdjYWH/hwsVRyRYF1DJmJYwJMARhTAHlLSp8NND/fmX52jVv/PH77WlTc2oPH7Hb7ZmZdpvNXlr6Xl1dbVHR6vb2ts7Ozvnz5ywuKOq43HGypXncuPTz354tLi5uOtay66O9AwPDAq9bueJNZ29Pw9GjGTbr2+uLNWqtyZRBKCdjUDAoCFEEiGI0e0Gh837PwQP7Frw6e1/1no1lpXe6f3G7vXlz5y8uKJz5St7x5pbly1ccP9HEYiYWi50/d/GT6k+vX7/q9bm6ux1btm1avaokN3d6xfayzZv2nDv3TXp6+ratm3NzJ7+2tMBiTg+GGQUxFBGKKEEEnkKTpuf7/f6mxsO28eYJz6ddu/YjVZTKyh1XrnYOD7u1SSm3bjn27tr9628/r1pZIghCa2vDylVvtbW1/HDlutPZU1a2ofXUmYf9j97ZUDZr1txUg2lkZKSx/kjmhIxlywpTTeaYzEkUUyXGYJlhQVEkQgh6eWGxz+fLSBs91my8/N3Xrxcu9rhdnV0/zZg5b2L2i4qM29vPhsPBd0s3tLd9hRBat26d47YjK8vedLzZ4/EsKyrieVFvSPF7/JcufW+3Zw0NDOXkTDHok7u6upJSUuOKRlIICwkMCUSiDINZTvU3vB8w5Vx0hfQAAAAASUVORK5CYII="
TEAMS_LEFT = "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"

@lru_cache(maxsize=128)
def _scaled(encoded, width, height):
    raw=cv2.imdecode(np.frombuffer(base64.b64decode(encoded),np.uint8),cv2.IMREAD_COLOR)
    return cv2.cvtColor(cv2.resize(raw,(width,height)),cv2.COLOR_BGR2RGB)


def _find(frame, encoded, reference_height, region, threshold=.87):
    h,w=frame.shape[:2]
    x1,y1,x2,y2=region
    left,top=round(w*x1),round(h*y1)
    crop=frame[top:round(h*y2),left:round(w*x2)]
    raw=_scaled(encoded,16,11) if encoded==MENU else (_scaled(encoded,39,11) if encoded==KNOCKOUT_RU else _scaled(encoded,64,14))
    rh,rw=raw.shape[:2]
    # UI glyphs scale with height, even on ultrawide phone displays. Small
    # variations account for integer rasterization and resized preview frames.
    for factor in (1.,.94,1.06,.88,1.12):
        scale=h/reference_height*factor
        tw,th=max(2,round(rw*scale)),max(2,round(rh*scale))
        if crop.shape[0]<th or crop.shape[1]<tw:continue
        template=_scaled(encoded,tw,th)
        _,score,_,loc=cv2.minMaxLoc(cv2.matchTemplate(crop,template,cv2.TM_CCOEFF_NORMED))
        if score<threshold:continue
        x,y=loc;patch=crop[y:y+th,x:x+tw]
        if np.mean(np.all(patch>190,axis=2))<.07:continue
        return left+x+tw/2,top+y+th/2
    return None


def current_showdown_hud(frame):
    return _find(frame,TEAMS_LEFT,270,(0,0,.30,.12),threshold=.83) is not None


def play_button_position(frame):
    """A yellow, bordered PLAY control with white lettering in the lobby footer."""
    h,w=frame.shape[:2]
    left,top=round(w*.70),round(h*.84)
    crop=frame[top:,left:]
    hsv=cv2.cvtColor(crop,cv2.COLOR_RGB2HSV)
    mask=cv2.inRange(hsv,np.array([18,130,160]),np.array([38,255,255]))
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask)
    for x,y,bw,bh,area in sorted(stats[1:],key=lambda s:s[4],reverse=True):
        if bw<w*.12 or bh<h*.055 or area<bw*bh*.40:continue
        if bw>w*.30 or bh>h*.16:continue
        patch=crop[y:y+bh,x:x+bw]
        if np.mean(np.all(patch>180,axis=2))<.015:continue
        return left+float(x)+bw/2,top+float(y)+bh/2
    return None


def current_lobby(frame):
    return (play_button_position(frame) is not None and
            _find(frame,MENU,199,(.82,0,1,.13)) is not None)


def unsupported_lobby_mode(frame):
    # This bot's tactical and result handling currently supports Showdown.
    # A known incompatible mode must produce a useful error, not an AFK game.
    return 'knockout' if _find(frame,KNOCKOUT_RU,199,(.34,.84,.73,1),threshold=.87) else None

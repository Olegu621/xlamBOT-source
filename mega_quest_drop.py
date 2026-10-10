"""Recognize the Mega Quests tap-to-open reward screen."""
import numpy as np
from reward_receipts import _find, _valid

TITLE = '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'
TAP = 'iVBORw0KGgoAAAANSUhEUgAAALUAAAAwCAAAAAByRWQeAAADEElEQVRoBdXBQU7jABAEwOr/P7rXnkkWEyOkIC5UxV8Uf1H8RfEXxS+qFb+sVqxYdRdvqhUf6i7eVCtWrLqLN9WKD3UXb6oVK1bdxbtqxIe6i3fViBWr7uJdNeJD3cW7asSKVXfxrhrxoe7iXTVixaq7eFeN+FB38a4asWLVXbyrRnyou3hXjVhxVSt+pka8qhU/UyNWXNWKD/UQT0Uc6hRPdYqbWvGhHuKpiEOd4qlO8RBXteKpLmLUKeopVp3iplY81UWMOkU9xapTPMRVrXiqqzjUXYw6xU2teKqrONRdjDrFQ1zViqe6ikPdxahT3NSKp7qKQ93FqFM8xFWteKpPgvpCnOoUN7XiqT4J6gtxqlM8xFWt+K9xqBXUF+JUp7ipFf81DrWC+kKc6hQPcVUrXtWIQ30hDnWKm1rxqkYc6gtxqFM8xFWteFUjRq2ohzjUKW5qxasaMWqFWnGoUzzEVa34r65i1Aq14lCnuKkV/9VVjFqhVhzqFA9xVSse6rMYtYIacahT3NSKh/osRq2gRhzqFA9xVStWvYhRK6gRhzrFTa1Y9SJGraBGHOoUD3FVK1a9iFErqBGHOsVNrVj1IkatoEYc6hQPcVUrRq1QI0atoEYc6hQ3tWLUCjVi1ApqxKFO8RBXtWLUCGrEqBXUiO/UilEjqBGjVlAj7uKqVowaQY0YtUKt+E6tGDWCGjFqhVpxF1e1YtQI6iEOtUKNONWIV7Vi1AjqIQ61Qo041YgVV7Vi1BeCehWHWvGqVoz6QlCv4lArVlzVilFfCOpVHGrFq1ox6gtBvYpDrVhxVStW3QX1Ik614lWtWHUX1Is41YoVV7XioW6C+ixGrXhVKx7qJqjPYtSKFVe14qmeUqc41CexasWrWvFUT6lTHOqTWLVixVWt+K9GUIc41EU81YpXteK/GkEd4lAX8VQrVvxEjfhtNeJ78RM14rfViO/FT9SI31Yjvhc/USN+W434XvxEjfhtNeJ78RM14rfViO/FT9SI31Yjvhc/USN+W434XvxF8RfFXxR/UfxF/wBPuwJA3UokDwAAAABJRU5ErkJggg=='


def mega_quest_drop(frame):
    if not _valid(frame):
        return False
    if _find(frame,TITLE,(0,0,.35,.16)) is None:
        return False
    if _find(frame,TAP,(.38,0,.63,.17)) is None:
        return _opening_star(frame)
    h,w=frame.shape[:2]
    background=frame[round(h*.18):round(h*.83),round(w*.12):round(w*.34)].astype(np.float32)
    purple=(background[:,:,2]>background[:,:,1]*1.3) & (background[:,:,0]>background[:,:,1]*1.1)
    return bool(purple.size and purple.mean()>.65)


def _opening_star(frame):
    # Mega Quests opening uses a six-point outlined star across rarity colors.
    # Require its closed alternating tips and recesses, not a background color.
    import cv2
    h,w=frame.shape[:2]
    left,top=round(w*.25),round(h*.18)
    crop=frame[top:round(h*.9),left:round(w*.75)]
    mask=np.all(crop<35,axis=2).astype(np.uint8)*255
    contours=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]
    for contour in contours:
        area=cv2.contourArea(contour)
        if area < h*w*.045 or area > h*w*.22:
            continue
        x,y,bw,bh=cv2.boundingRect(contour)
        if not (.2*w < bw < .45*w and .3*h < bh < .75*h):
            continue
        polygon=cv2.approxPolyDP(contour,.012*cv2.arcLength(contour,True),True)
        if len(polygon)!=12:
            continue
        hull_area=cv2.contourArea(cv2.convexHull(polygon))
        if not hull_area or not .72 < area/hull_area < .92:
            continue
        points=polygon[:,0,:].astype(np.float32)
        center=points.mean(axis=0)
        if not (.44*w < center[0]+left < .56*w and .4*h < center[1]+top < .7*h):
            continue
        radii=np.linalg.norm(points-center,axis=1)
        a,b=radii[::2],radii[1::2]
        tips,recesses=(a,b) if a.mean()>b.mean() else (b,a)
        if tips.min()>recesses.max()*1.15:
            return True
    return False

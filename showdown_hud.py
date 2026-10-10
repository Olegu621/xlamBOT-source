"""Recognize the stable Showdown caption without its animated map background."""
import base64
from functools import lru_cache
import cv2
import numpy as np

# Anonymous lower glyphs of "Teams left:"; FPS overlay and changing count excluded.
CAPTION = 'iVBORw0KGgoAAAANSUhEUgAAAHwAAAAdCAAAAABN3VedAAABy0lEQVRIDcXBQXLjSAADMPD/j+aK7Y2luJLLXALEv6qJn9WXUBOf4l/VxI/qCA018Sn+VU38qCZeauJT/Kua+FFNvNTEp1AENaEm3uqIp5p4qZe41C11C3XEJWpSn+Kl3uJWE0d9CeqWeog64hL1m5i6xa0mpm6hbqmHqCMuUb8K6iFuNXGpp6hb6iHqiEvUr4J6SYmHmqC+ibqlbqGOuET9KqgjPtUEdURNUEccNTF1xCWoCXWEmqBe4kNNUBNqgjriqImpIy5BTVATaoL6Et/UhDpCTVBHHDXxKagJakJNXOpLPNWE+i6oI46a+BTUBDWhJqbe4lYT6rugjjhq4lNQE9SEmjjqS9xqQn0TlzriqIlPQU1QE2rif/W/eKsJ9RRTRxw18SmoCWpCTXypl3irCWrioY44auKoiUtQE9SEmqAEdcRbTVATD3XEURNTR1yCmqAm1IT6Jt5qgjpCEZc64qiJqSMuQU1QE2pCPcWtJi71EJc64qiJqSMuQU1QE2pCPcWtJqYegjriqImpIy5BTVATaoK6xUNNHPUWlzriqImpIy5BTVATamLqJb6piZd6iZeaOGpi6ohL/KH4Q/FnmvgzTfyh+EP/AeZpsh7frbxYAAAAAElFTkSuQmCC'

# Alternate current HUD lettering; only constant caption pixels are retained.
CAPTION_CURRENT = 'iVBORw0KGgoAAAANSUhEUgAAADYAAAAKCAAAAADalvLXAAAAaUlEQVQoFZ3BsQHCMAAEMd3+Qz820EIRKY/kkRwjvy0fy1eu5Y/lbTI5ci1GRuYtIyxDc2XKtUwLizUtk2NZk2Vy5FpGpsWaFhPWEMvkyLVYTNNkLSYsy7FYjlyLkWlZ1jLCYmSxTHnkBVCdQgsiIonvAAAAAElFTkSuQmCC'

# Russian caption without the changing team count or account information.
CAPTION_RUSSIAN = 'iVBORw0KGgoAAAANSUhEUgAAAF0AAAAMCAAAAAAlyO5NAAAAkUlEQVQ4EbXBgU0AMQADMd/+Q4f2BWKC2nkpx/JGTJMXYrG8kIVlwuTPkGWxsHyWZVkslmOZLJYln2W5lmNiWZZlOYYwYplMIyxzxLLksyzXYk0sy7Isx7IwZJmWNU3LNLEsMU0mx2JZFsuyTFgWlmVZjmUty2KZLGFyLb8mls/kmFiu5Zr8G/k1V3ln5aW89ANzdWkNKtE3EwAAAABJRU5ErkJggg=='

CAPTION_SOLO_RUSSIAN = 'iVBORw0KGgoAAAANSUhEUgAAATgAAAAeCAAAAACdll0pAAAENklEQVRoBeXBAQ7bxhUFwHn3P/TL/iVFkbLgFG6CuvBMvNQW/x+K+JkSivjnxaHe4ndXW/xMvcQ/L0Y9xO+sXuKn6hD/gljqQ/y26hI/V1v8G2KpT/Gbqkv8vYp/R1A/iN9THeJ/LagtRm1xKfFTRfxnivhU4u/VFj8q4r9SxEMR34TaYqstDnUK9SGoS1zqKbZ6ibc6BTXiqxrxqV5iqyW2GkGNGDXipV5iq5vYagtCbXGoEVtdoj6EuomXeoqlbuKlLqFGfFVL1IhT3cSoJUZtQY0YNeJQNzHqLkZtQagRp9piqbeoD6Hu4lRPQT3Eod5CjfimnmLUQyy1xFKHoEaMGrHVQyz1EEttQagRp9qCuon6EOouTvUU1FOMugk14pv6EEs9BbUEdQpqxKgRWz0F9RBLbUGoES81Qt2E+hCUoLY41FOoD7HUTVAjvqkPQX0IagnqFNSIUSNGfQhqBLXEUlsQasRLjVBb0DjVFh9qxKFGUCPUFtQW1BY0lrqLu/oUagtqC7WEeglqxKgRo7agtlAjqCWW2oJQI15qhBrxUCN+UEscagQ1Qo1YagtqxKUe4qa2oLZQI5baQi2hXoIaMWrEqBFLbaFGUEsstQWhRrzUCDXioUZc6iYONYIaoUaMGkGNuNRTvNWIpbZQI0aNUEvUJagRo0aMGjFqhHqIp1AjTrWFGvFQI071EFttQY2oLUaNoEZc6kNcasSoEbXFqBFqiboENWLUiKW2GDVC3cWHUCNOtUVt8VAjDvUUW41YakRtMWqE2uJSI6gtLjVi1IjaYtQIdUmNoEaMGrHUFqNGqLv4EGqLQ41QWzzUiEM9xVYjlhpRW4waoba41IilRlxqxKgRtcWoEeqSGkGNGDViqS1GjVBP8RBqi0ONoEY81IittqBGbDViqRFqxKgR1IhLjVhqxKVGjBqhRiy1hXqJGkGNGDVi1IiltlAjqBEPQW0xagtqi7sasdWIUUtsNWKpEWrEUltQW7zUiKVGXGrEUluoEUttoU6hRlAjRo0YNWKpLdQIagS1BUH9IJY6hYqtRmw1YtQSo7ZYaoQ6RG2x1ClUqBFLjbjUFtQW6hC1BXUKNYL6ItQhagtqBDWC2oKgfhBL3cVWI7baghqhXmKpEepDLHUX6kO81VNQH4I6BDWC+iLUh6CegtqCWOpDbHUTW4041FOoU4waQT3EVjehnuKmnmKph1jqENQI6ougHmKpp6C2IEY9xKneYqsRh3oKdYpRI5a6i0O9hXqKu7qLUQ+x1BZLjaC+COohlnqIpbYgtrqJS73FqBGnegh1iK1GjHqLl3qLeoineotTvcWoEaNGUF/EqLcYdRejtiBOdYq7OsWhRlzqJbYacaglDnWKmzoFdRM/qkO81SkONWLUCOqL2OoUp7rEobYg/lw14pfEn6tG/JL4c9WIXxJ/sopf9BfGAqsuPFnrvAAAAABJRU5ErkJggg=='

CAPTION_TRIO_RUSSIAN = 'iVBORw0KGgoAAAANSUhEUgAAATwAAAAfCAAAAABfIS72AAAENklEQVRoBe3BW5IjNxAEMOT9D51msfVoauXYCft3gHiqLX79VFzqLX79SGx1F79+Ikad4tcPxFKf4tffBfWH+PV3QW0xaou3xl9U/FTFnxr/T8XPVfx/oba41IhLXYL6ENRLvNQhLvUUb3WJpUZ8UyOW2mLUU1xqxEONGPUSW40YNeJSh9hqhFBbXGrEVi9RH0LdxFMdYtRNPNVLqBHf1IilRix1E1uNuNQWS93EqBGjRlzqEKO2EGrEQ40Y9Rb1IdRdPNQhRt3Fpd5CjfimRlBbUIcYtcVWWyx1F0uNGDXiUocYtYVQIx5qC+ot1IdQd/FQp6BOMeom1IhvagQ1YqlTLLXFqEssdRdLjRg14lKHGLWFUCOeagT1FupDULHUFpc6BPUhlroJasQ3NUKNWOpDLHWJpS4xSlBbUCNGjdjqFKO2EGrEU41QW9B4qBGfasSlRlBLUFtQI5bagsZSd3FXI2qLpbagRlAPQT3EXY2gRowasdUIasSoLYQa8VQj1IhDjfhDLXGpEdQS1IiltqBGvNQhbuouRo1Yagv1FOohDrUEtQW1xVYjqBGjthBqxFONUCMONeKlbuJSI6glqBGjRlAjXuoUb3UTW40YNUI9hXqIrW6C+hRbjaBGnEKNeKoRasShRjzUIS61xFIj1IhRI6gRL3WKt7qLUSNGjVAvqadY6hDUp9hqBDXiFGrEQ22hRhxqxKVOsdWIpUaoEaNGUCNeagS1xUvdxagRo0aoJbWkSI1Qp6A+xVYjqBGnUCMeagQ14lAjLnWKrUYstQQ1YtQIasRLjVhqxEsdYqkRo0aoJeohagl1CupTbLXEUiNOoba41AhqxKFGbDViqRFbjVhqCWrEqBHUiJcasdSIl7qkRiw1YtQItURdQi1RI5YaQX2KUSOWGnEKaotRW1Bb3NWIrUaMWmKrEUstQY1YasRSWzzViKVGvNQWagQ1YqkR1BJqC7VEjRi1BDVi1IhRI5YasdUIQT2kHmKpS1Cx1YitRoxaYtQWSy1BbaG2WOoSNKgRS414qRHUCGoLtQW1hBpBLVEjRi1BjRg1Qn0T1BZiqU+x1F1sNWKrLagR6imWWoL6EEvdhfoQLzViqRHqQ1BLUEtQS9QW1AhqxKgR6qtQW4ilPsRWN7HViEudQj3EqCWWOsRWN6FO8VYjlhpBHWKpJaglqCXUKagRo0aor0JtIUYd4qHeYqsRlzqFeohRS4y6i0u9hTrFW41YagvqLpZa4qaWUKegRowaob4KtYXY6iZe6i1GjXioQ6hLbLXEVi/xUi+hDnFTI0aNWOoltlrippagDkGNGDVCfRVqC/FUlzjUJS414qWeYqsRl1riobY41CWomzjUiFEjttrioYi7WmLUU2w1YtQI9VWoLcSvr2qJtxpxE7++qiXeasRN/PqqlnirETfx6180To1T/PrP/gEZ464vbu9QbgAAAABJRU5ErkJggg=='

CAPTION_SOLO_ENGLISH = 'iVBORw0KGgoAAAANSUhEUgAAAN8AAAAjCAAAAAAxwoCSAAADbklEQVRYCd3BSXYDVxIEMMT9Dx3+mRyqyNfqjbyxgPjb4m+L/7YS/0ccdRf/hhrxGzXiR/UUP4ijPsS/oEb8Ro34Sb3ED+KoT/F7NeI3asQP6i1+EEd9iV+rEb9RI35QL6GO+BZHfYlfqxG/USN+UCM01IgvcdSKeohfqxG/USN+UEc81IgvcdQIasWv1YjfqBH/W414qBFf4qgRR42gxFHEqId4qBFHHXHUiBrxUiNWiaOIVStuasRLjRh1SV2CGkEcNeKoEeoINUJdYtSIo444akSNeKiXoI5QI6i3eKsRD/US1CV1CWoEcdQIaoUaqRHUJUaNOOoIaoQaseoSaqRGUJd4qxGrLqEuqUtQI4ijRqgV1E0cdYmjRlAjqBFqxKi7qJtQN/FWI0bdRV1Sl6BGEEd9iKNu4qhQK0YdQa1QI9SIoz5E3YRaoeJSI476EHVJXYIaQRx1F6Nu4q1GjDqCWqFGqBFHragRdRNqxZcacdSKGkGtWDVi1QjiqE8xasWHGjFqhFqhRqgRR42gjqBWrHqITzXiqBHUEdSKVSNWjSCO+hJHrXiqS4waUQ+hjqBGHDWCOoJaseol7moEtYI6glqxasSXOGoEteKoFavuYtSIeoo6ghpBrVAjqBUP9RI3NYJaUSuoFatGfImjRhy1glqx6i5GjainqCOoEdSnoFY81Vu81QjqU1ArVo34EkeNOGoFtWLUihqx6oh6ijqCGkF9iKNWvNRLvNUI6kMctWLViC9x1IijVlArRo1QI1YdqSNFagQ1grqJVSsu9RQvNYK6iVUrVo34EkeNoB6CWjFqhBqx6i31EkeNOGrETa24qYd4qRFHjbipFatGrBpBHPUtqBWjRqinoF6iXuKoEUeNuKkVq+KoFS814qgRN7Vi1YhVI4ijvgW1YtS3oF5CPcVRI45aQYmjVqy6i5cacdQKShy1YtWIVSOIo77EUStGfYujnkI9xVEjRt3EUStG3cVbjRh1E0etWDVi1QjiqC9x1IpVX+Kop1BPcdSIVZc4asWou3irEasucdSKVSNWjSCO+hCrVjzUU+qIUQ9BPcSoEQ/1FketWHWJS414qLc4asWqEatGEEdd4qVWPNUIihj1ENRDjBrxUitWrXiqh7irES+14qGOeKgRq0YQf1v8bfG3xd8Wf1v8bf8AEh1YM82lhyAAAAAASUVORK5CYII='

@lru_cache(maxsize=30)
def _caption(height, factor=1., encoded=CAPTION, reference_height=720):
    raw = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), np.uint8), 0)
    return cv2.resize(raw, (max(2, round(raw.shape[1]*height/reference_height*factor)),
                            max(2, round(raw.shape[0]*height/reference_height*factor))),
                      interpolation=cv2.INTER_NEAREST)


def visible_showdown_caption(frame):
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        return False
    height, width = frame.shape[:2]
    crop = frame[:round(height*.12), :round(width*.30)]
    if not crop.size:
        return False
    # Threshold the current pixels, not cached state. Dimmed modal HUDs cannot
    # pass; moving scenery no longer distorts the letters' template score.
    white = (np.all(crop > 205, axis=2).astype(np.uint8)*255)
    for encoded, reference_height in ((CAPTION, 720), (CAPTION_CURRENT, 212), (CAPTION_RUSSIAN, 219), (CAPTION_SOLO_RUSSIAN,720), (CAPTION_TRIO_RUSSIAN,720), (CAPTION_SOLO_ENGLISH,720)):
        candidates = [(white,height)]
        if encoded == CAPTION_RUSSIAN and height > reference_height:
            scale = reference_height/height
            transform = np.array([[scale,0,(scale-1)/2],
                                  [0,scale,(scale-1)/2]],np.float32)
            normalized = cv2.warpAffine(crop,transform,
                                        (round(crop.shape[1]*scale),round(crop.shape[0]*scale)),
                                        flags=cv2.INTER_LINEAR)
            candidates.append((np.all(normalized > 200,axis=2).astype(np.uint8)*255,
                               reference_height))
        for candidate,candidate_height in candidates:
            for factor in (1., .96, 1.04):
                glyph = _caption(candidate_height, factor, encoded, reference_height)
                if any(candidate.shape[i] < glyph.shape[i] for i in (0, 1)):
                    continue
                _, score, _, _ = cv2.minMaxLoc(cv2.matchTemplate(candidate, glyph, cv2.TM_CCOEFF_NORMED))
                if score >= .90:
                    return True
    return False

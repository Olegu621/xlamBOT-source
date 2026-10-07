"""Reads the real per-brawler trophy count off the screen.

The bot's own counter is not read from the game: `trophy_observer` starts from
whatever number is in the queue and keeps adding its own computed deltas. That
number drifts further from reality with every match, and it is what the
"reached the target" check compares against, so a brawler that is 43 trophies
short looks 643 short and the bot plays it forever.

Two figures are read here:

* the selected brawler's own trophy count, in the middle of the lobby, and
* the account's trophy total, in the yellow bar under the crown badge.

The account total is the one that can carry a trophies-per-hour rate, because it
does not restart when the brawler changes.
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import sys

import cv2
import numpy as np

try:
    import pytesseract

    # Сначала ищем переносимую копию, которая едет вместе с программой: у
    # установленного пользователя своего Tesseract может не быть, и раньше
    # читать трофеи было просто нечем. Папка vendor лежит рядом с проектом,
    # а в собранной программе - в _internal.
    TESSERACT_PATH = ""

    def _tesseract_candidates():
        roots = []
        if getattr(sys, "frozen", False):
            roots.append(getattr(sys, "_MEIPASS", ""))
        roots.append(str(pathlib.Path(__file__).resolve().parent))

        for root in roots:
            if not root:
                continue
            yield os.path.join(root, "vendor", "tesseract", "tesseract.exe")

        # Системные установки - последним выбором, чтобы рабочая копия
        # пользователя не перебивала ту, что мы положили рядом.
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                yield os.path.join(base, "Tesseract-OCR", "tesseract.exe")
        yield shutil.which("tesseract") or ""

    for candidate in _tesseract_candidates():
        if not candidate or not os.path.isfile(candidate):
            continue
        try:
            pytesseract.pytesseract.tesseract_cmd = candidate
            # Проверяем не только по existence файла: папка может найтись, а
            # запуститься exe не сможет - не хватит DLL.
            pytesseract.get_tesseract_version()
            TESSERACT_PATH = candidate
            break
        except Exception:  # noqa: BLE001
            continue

    OCR_AVAILABLE = bool(TESSERACT_PATH)
except Exception:  # noqa: BLE001
    OCR_AVAILABLE = False
    TESSERACT_PATH = ""

# The per-brawler trophy count, in the 1920x1080 base the rest of the project
# uses. It sits in the centre of the lobby next to the prestige badge, not in
# the corner: the top-left counter is the account total, and reading that one
# reports a completely different number for the same brawler.
# Measured on the emulator at 1280x720, where the digits span x 620-690,
# y 100-135.
DEFAULT_REGION = (900, 150, 135, 53)
# Neighbouring crops tried in order. The first that yields clean digits wins,
# which absorbs small layout shifts and interpolation differences.
CANDIDATE_REGIONS = (
    DEFAULT_REGION,
    (930, 150, 105, 53),
    (922, 147, 120, 60),
    (900, 143, 150, 67),
)
OCR_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789"

# On the brawler screen every card prints its own name and trophy count, so the
# card the game considers the lowest can simply be read instead of guessed.
# Measured on the emulator at 1280x720 and expressed in the usual 1920x1080 base.
FIRST_CARD_NAME_REGION = (540, 350, 170, 38)
FIRST_CARD_TROPHY_REGION = (380, 388, 85, 34)
# Tesseract reads a space or a dash in the whitelist as a separate argument and
# refuses to start, so the whitelist is letters and digits only; the match
# below strips punctuation from both sides anyway.
NAME_OCR_CONFIG = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# A whitelisted pass fails outright on some card backgrounds, so this
# second pass lets the OCR engine pick its own characters.
NAME_OCR_LOOSE_CONFIG = "--psm 7"

# Account digits only, in 1920x1080 reference coordinates. Manual per-device
# regions take priority. Two separate frames confirm values in the observer.
ACCOUNT_TOTAL_REGION = (416, 26, 122, 52)
ACCOUNT_TOTAL_REGIONS = (
    ACCOUNT_TOTAL_REGION,
    (414, 26, 124, 52),
    (416, 30, 122, 48),
)


def available() -> bool:
    return OCR_AVAILABLE


def _digits(text: str, allow_zero=False):
    if allow_zero and str(text).strip() in {'O', 'o'}:
        return 0
    match = re.fullmatch(r"\d{1,7}", str(text).strip().replace(" ", ""))
    if not match:
        return None
    value = int(match.group())
    return value if value > 0 or (allow_zero and value == 0) else None


def read(frame, region=DEFAULT_REGION) -> int | None:
    """Read the selected brawler, retaining zero and requiring OCR agreement."""
    if not OCR_AVAILABLE or frame is None or frame.size == 0:
        return None
    from brawler_calibration import region_for
    custom = region_for('lobby_trophies')
    candidates = [custom] if custom is not None else [(900, 150, 135, 53), (900, 147, 135, 60), region]
    values = []
    for candidate in candidates:
        value = _read_region_digits(frame, candidate, allow_zero=True, text_color='white')
        if value is not None and 0 <= value <= 100000:
            values.append(value)
            if custom is not None or values.count(value) >= 2:
                return value
    if custom is not None:
        return values[0] if values else None
    from collections import Counter
    counts = Counter(values)
    if counts and counts.most_common(1)[0][1] >= 2:
        return counts.most_common(1)[0][0]
    return None


def read_account_total(frame, expected=None):
    """Read actual digits; an old baseline must never invent missing prefixes.

    The observer confirms readings on separate frames before committing them.
    """
    if not OCR_AVAILABLE or frame is None or frame.size == 0:
        return None
    from brawler_calibration import region_for
    custom = region_for('account_total')
    candidates = []
    for region in ([custom] if custom is not None else ACCOUNT_TOTAL_REGIONS):
        x,y,width,height=region
        # Include complete outlines, then remove border/icon components rather
        # than accepting digits cut by a tightly calibrated rectangle.
        region=(x-6,y-3,width+12,height+6)
        value = _read_region_digits(frame, region, allow_zero=True, text_color='account')
        if value is not None and 0 <= value <= 2000000:
            # A reward particle can hide all but the last account digit.
            if isinstance(expected, int) and expected > 50 and value < 10 and abs(value-expected) > 50:
                continue
            # A trophy icon fragment can become a leading digit. Never turn
            # a suffixed/prefixed OCR reading into a huge account gain/rebase.
            if isinstance(expected, int) and expected > 0 and abs(value-expected) > 400:
                old, new = str(expected), str(value)
                if len(old) != len(new) and (old.endswith(new) or new.endswith(old)):
                    continue
                # Animated/clipped trailing glyphs can add a decimal place:
                # 53291 becomes 532910, even when the last two real digits
                # changed since the preceding match. This is not a gain.
                if len(new) > len(old) and len(old) >= 4 and new.startswith(old[:-2]):
                    continue
            candidates.append(value)
    if custom is not None:
        return candidates[0] if candidates else None
    from collections import Counter
    counts = Counter(candidates)
    if counts:
        value, votes = counts.most_common(1)[0]
        if votes >= 2:
            return value
    return None


def card_offset(card_index):
    """Compatibility for old callers: sorting always selects the first card."""
    return 0, 0


def shifted(region, card_index):
    """Move a region from the first card onto the card at `card_index`."""
    dx, dy = card_offset(card_index)
    x, y, width, height = region
    return (x + dx, y + dy, width, height)


def read_card(frame, card_index=0):
    """Read the brawler name and trophies off the first sorted card.

    Returns ``{"brawler": name, "trophies": count}`` with either value set to
    None when it could not be read. The name is matched against the brawlers the
    project actually knows about, because raw OCR of a card returns things like
    "SIRIUS |" and a name that is not in the list is not worth reporting.

    Legacy card_index arguments are ignored along with the old grid traversal.
    """
    result = {"brawler": None, "trophies": None}
    if not OCR_AVAILABLE or frame is None or frame.size == 0:
        return result
    result["brawler"] = _read_card_name(frame, card_index)
    result["trophies"] = _read_region_digits(
        frame, _calibrated_card_region(FIRST_CARD_TROPHY_REGION, card_index, 'card_trophies'), allow_zero=True)
    return result


# The measured region first, then wider and tighter variants of it. One narrow
# crop with one OCR pass missed often enough that the panel kept naming the
# previous brawler after a switch that had in fact happened.
CARD_NAME_REGIONS = (
    FIRST_CARD_NAME_REGION,
    (536, 344, 180, 44),
    (532, 338, 188, 50),
    (544, 352, 162, 36),
)

# Character-level distance, sized to swallow OCR noise without letting a
# different brawler win: "BROCK" vs "BRDCK" is 2.
NAME_MAX_DISTANCE = 2


def _levenshtein(left, right):
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, lchar in enumerate(left, 1):
        current = [i]
        for j, rchar in enumerate(right, 1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (lchar != rchar),
            ))
        previous = current
    return previous[-1]


def _match_brawler_name(squashed, known):
    """Find the brawler whose name this OCR text is meant to be."""
    if not squashed:
        return None
    normalised = sorted(
        ((re.sub(r"[^A-Z0-9]", "", name.upper()), name) for name in known),
        key=lambda pair: -len(pair[0]),
    )
    # Longest name first so "EL PRIMO" wins over a shorter name it contains.
    for candidate, name in normalised:
        if candidate and (squashed.startswith(candidate) or candidate in squashed):
            return name
    # Nothing matched outright, so allow a near miss, but only when the lengths
    # are close enough that this reads as a misread rather than another name.
    best = None
    for candidate, name in normalised:
        if abs(len(candidate) - len(squashed)) > NAME_MAX_DISTANCE:
            continue
        distance = _levenshtein(candidate, squashed)
        if distance <= NAME_MAX_DISTANCE and (best is None or distance < best[0]):
            best = (distance, name)
    return best[1] if best else None


def _calibrated_card_region(region, card_index, kind):
    from brawler_calibration import card_region
    try:
        return card_region(region, card_index, kind)
    except (KeyError, ValueError, TypeError, OSError):
        return shifted(region, card_index)


def _read_card_name(frame, card_index=0):
    known = _known_brawler_names()
    if not known:
        return None
    seen = []
    tried = set()
    for index, region in enumerate(CARD_NAME_REGIONS):
        moved = _calibrated_card_region(region, card_index, 'card_name')
        if moved in tried:
            continue
        tried.add(moved)
        for config in (NAME_OCR_CONFIG, NAME_OCR_LOOSE_CONFIG):
            text = _read_region_text(frame, moved, config)
            if not text:
                continue
            squashed = re.sub(r"[^A-Z0-9]", "", text.upper())
            seen.append(squashed)
            name = _match_brawler_name(squashed, known)
            if name:
                if index or config != NAME_OCR_CONFIG:
                    print(f"Card name read from region {index} as {name} "
                          f"(OCR saw {squashed!r}).")
                return name
    if seen:
        print(f"No brawler matched the card text {seen!r}.")
    return None


def _known_brawler_names():
    try:
        from utils import load_brawlers_info

        return list(load_brawlers_info().keys())
    except Exception:  # noqa: BLE001
        return []


def _crop(frame, region):
    height, width = frame.shape[:2]
    x, y, w, h = region
    ratio_x, ratio_y = width / 1920, height / 1080
    x1, y1 = max(0, int(x * ratio_x)), max(0, int(y * ratio_y))
    x2, y2 = min(width, int((x + w) * ratio_x)), min(height, int((y + h) * ratio_y))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    return frame[y1:y2, x1:x2]


def _read_region_text(frame, region, config, scale=4):
    crop = _crop(frame, region)
    if crop is None:
        return ""
    grey = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    upscaled = cv2.resize(grey, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    try:
        return pytesseract.image_to_string(upscaled, config=config, timeout=4).strip()
    except Exception as error:  # noqa: BLE001
        print(f"Card OCR failed: {error}")
        return ""


def _read_region_digits(frame, region, allow_zero=False, text_color='auto'):
    crop = _crop(frame, region)
    if crop is None or not OCR_AVAILABLE:
        return None
    grey = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    # Trophy totals are yellow; brawler/card digits are usually white. Separating
    # text from the icon/background avoids turning the bar into extra digits.
    rgb = crop.astype(np.int16)
    yellow = ((rgb[:,:,0] > 165) & (rgb[:,:,1] > 100) & (rgb[:,:,2] < 150)
              & (rgb[:,:,0] > rgb[:,:,2] + 60))
    white = ((rgb.min(axis=2) > 165) & (rgb.max(axis=2)-rgb.min(axis=2) < (45 if text_color == 'white' else 85)))
    mask = white if text_color == 'white' else yellow if np.count_nonzero(yellow) >= 20 else white
    if text_color == 'account':
        count, components, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
        keep=[i for i in range(1,count)
              if stats[i,cv2.CC_STAT_HEIGHT] >= max(7,crop.shape[0]*0.32)
              and stats[i,cv2.CC_STAT_AREA] >= 6
              and stats[i,cv2.CC_STAT_LEFT] > 0
              and stats[i,cv2.CC_STAT_TOP] > 0
              and stats[i,cv2.CC_STAT_LEFT]+stats[i,cv2.CC_STAT_WIDTH] < crop.shape[1]
              and stats[i,cv2.CC_STAT_TOP]+stats[i,cv2.CC_STAT_HEIGHT] < crop.shape[0]]
        if not keep:
            return None
        mask=np.isin(components,keep)
        ys,xs=np.where(mask)
        left,right,top,bottom=max(0,xs.min()-3),min(mask.shape[1],xs.max()+4),max(0,ys.min()-3),min(mask.shape[0],ys.max()+4)
        support=cv2.dilate(mask.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
        grey=np.where(support,255-grey,255).astype(np.uint8)[top:bottom,left:right]
        mask=mask[top:bottom,left:right]
    if text_color == 'white':
        # White highlights on the yellow trophy must not become a leading 1.
        # Keep full-height glyphs, then restrict numeric OCR to their bounds.
        count, components, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
        keep = [i for i in range(1, count) if stats[i, cv2.CC_STAT_HEIGHT] >= max(7, crop.shape[0]*0.38) and stats[i, cv2.CC_STAT_AREA] >= 6]
        # Thin icon outlines have little white ink inside their bounding box.
        # A power-level digit cut by the crop boundary is also not a trophy.
        keep = [i for i in keep if stats[i,cv2.CC_STAT_AREA] / (stats[i,cv2.CC_STAT_WIDTH]*stats[i,cv2.CC_STAT_HEIGHT]) >= 0.28
                and stats[i,cv2.CC_STAT_LEFT] > 0
                and stats[i,cv2.CC_STAT_LEFT]+stats[i,cv2.CC_STAT_WIDTH] < rgb.shape[1]]
        if not keep:
            return None
        if keep:
            # Tesseract merges repeated narrow 1 glyphs into one character.
            # Full-height separate vertical glyphs retain their actual count.
            if len(keep) <= 5 and all(stats[i,cv2.CC_STAT_WIDTH]/stats[i,cv2.CC_STAT_HEIGHT] < 0.55 for i in keep):
                return int('1'*len(keep))
            mask = np.isin(components, keep)
            ys, xs = np.where(mask)
            left,right,top,bottom=max(0,xs.min()-3),min(mask.shape[1],xs.max()+4),max(0,ys.min()-3),min(mask.shape[0],ys.max()+4)
            # Preserve antialiased strokes around the bright glyph cores.
            # A hard white-only mask can open both loops of an 8 into a 3.
            support=cv2.dilate(mask.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
            grey=np.where(support,255-grey,255).astype(np.uint8)[top:bottom,left:right]
            mask=mask[top:bottom,left:right]
    binary = np.where(mask, 0, 255).astype(np.uint8)
    if np.count_nonzero(mask) >= 16:
        ys, xs = np.where(mask)
        isolated = binary[ys.min():ys.max()+1, xs.min():xs.max()+1]
        isolated = cv2.resize(isolated, None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST)
        isolated = cv2.copyMakeBorder(isolated, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
        readings = []
        for psm in (7, 8):
            try:
                value = _digits(pytesseract.image_to_string(isolated, config=f'--psm {psm}', timeout=4), allow_zero)
            except Exception:
                value = None
            readings.append(value)
        # Color masks can omit a thin leading digit. Only use this pass to
        # confirm an isolated zero, which the numeric whitelist often drops.
        if allow_zero and readings == [0, 0]:
            return 0
    variants = [(grey, 8), (grey, 13), (binary, 7), (binary, 8), (grey, 7)]
    votes = []
    for image, psm in variants:
        image = cv2.resize(image, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        image = cv2.copyMakeBorder(image, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
        try:
            text = pytesseract.image_to_string(image, config=f'--psm {psm} -c tessedit_char_whitelist=0123456789', timeout=4)
        except Exception:
            continue
        value = _digits(text, allow_zero=allow_zero)
        if value is not None:
            votes.append(value)
            if votes.count(value) >= 2:
                return value
    from collections import Counter
    counts = Counter(votes)
    if counts:
        value, count = counts.most_common(1)[0]
        if count >= 2:
            return value
    return None


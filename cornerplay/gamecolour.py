"""A colour taken from each game's cover, used to tint the UI around the focused game.

The cover is downloaded once (it is small) and reduced to a hue and saturation, which
are cached in ~/.cache/cornerplay/game_colours.json. The accent is then made light for
dark themes and dark for light ones, so it always reads against the background.
"""
import threading

from .config import CACHE_DIR, read_json, write_json
from .net import requests

FILE = CACHE_DIR / "game_colours.json"
_lock = threading.Lock()
_mem = None


def _cache():
    global _mem
    if _mem is None:
        _mem = read_json(FILE) or {}
    return _mem


def cached(key):
    """[hue, saturation], [] for a game whose cover has no clear colour, or None if not worked out yet."""
    with _lock:
        return _cache().get(key)


def hue_sat(img):
    """The strongest hue in an image: [hue 0-359, saturation 0-255], or [] for a grey image."""
    from PySide6.QtGui import QColor
    img = img.scaled(48, 48)
    buckets = {}
    for y in range(img.height()):
        for x in range(img.width()):
            h, s, v, _ = QColor(img.pixel(x, y)).getHsv()
            if s < 80 or v < 80 or h < 0:
                continue
            w = (s / 255) * (v / 255)
            hs, ws, ss = buckets.get(h // 15, (0.0, 0.0, 0.0))
            buckets[h // 15] = (hs + h * w, ws + w, ss + s * w)
    if not buckets:
        return []
    hs, ws, ss = max(buckets.values(), key=lambda b: b[1])
    if ws < 40:  # only a few coloured pixels: not the game's colour
        return []
    return [int(hs / ws) % 360, int(ss / ws)]


def compute(key, urls):
    """Download the first cover that loads and remember its colour. Blocking (worker thread)."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QImage
    for url in urls:
        img = QImage()
        try:
            if url.startswith("file://"):
                img.load(QUrl(url).toLocalFile())
            else:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    img.loadFromData(r.content)
        except requests.RequestException:
            continue
        if not img.isNull():
            value = hue_sat(img)
            with _lock:
                _cache()[key] = value
                write_json(FILE, _cache())
            return value
    return None  # nothing loaded (offline): try again another time


def accent(value, dark=True):
    """Hex accent for [hue, saturation]; "" when the game has no clear colour."""
    if not value:
        return ""
    from PySide6.QtGui import QColor
    hue, sat = value
    return QColor.fromHsl(hue, max(120, min(sat, 215)), 178 if dark else 92).name()

"""ProtonDB ratings: how well each game runs on Linux through Proton, from players' reports.

One small request per game with a Steam app id, done in the background after a refresh
and cached for a week in ~/.cache/aiolaunch/protondb.json.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .config import CACHE_DIR, read_json, write_json
from .net import requests

FILE = CACHE_DIR / "protondb.json"
TTL = 7 * 86400
MISS_TTL = 2 * 86400  # no reports yet: look again sooner
API = "https://www.protondb.com/api/v1/reports/summaries/{}.json"
TIERS = ("platinum", "gold", "silver", "bronze", "borked")
_lock = threading.Lock()
_mem = None


def _cache():
    global _mem
    if _mem is None:
        _mem = read_json(FILE) or {}
    return _mem


def rating(appid) -> dict:
    """{"tier", "trending", "reports", "confidence"}, or {} when unknown."""
    if not appid:
        return {}
    with _lock:
        entry = _cache().get(str(appid)) or {}
    return entry if entry.get("tier") in TIERS else {}


def _fetch(appid):
    try:
        r = requests.get(API.format(appid), timeout=12)
    except requests.RequestException:
        return appid, None  # offline: keep what the cache has
    if r.status_code == 404:
        return appid, {"t": time.time()}  # no reports
    try:
        d = r.json()
    except ValueError:
        return appid, None
    return appid, {"tier": d.get("tier", ""), "trending": d.get("trendingTier", ""),
                   "reports": int(d.get("total") or 0), "confidence": d.get("confidence", ""), "t": time.time()}


def refresh(appids) -> bool:
    """Fetch ratings that are missing or stale. Blocking (worker thread). True if anything changed."""
    now = time.time()
    with _lock:
        cache = _cache()
        todo = []
        for a in {str(a) for a in appids if a and str(a).isdigit()}:
            e = cache.get(a)
            age = now - (e or {}).get("t", 0)
            if e is None or age > (TTL if e.get("tier") else MISS_TTL):
                todo.append(a)
    if not todo:
        return False
    found = {}
    with ThreadPoolExecutor(6) as pool:
        for appid, entry in pool.map(_fetch, todo):
            if entry is not None:
                found[appid] = entry
    if found:
        with _lock:
            _cache().update(found)
            write_json(FILE, _cache())
    return bool(found)

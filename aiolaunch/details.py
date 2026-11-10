"""A game's description, genres, developer and release year, for the game panel and TV mode.

Sources: GOG's own product page for GOG games, Steam's store page for every game with
a known Steam app id, and the store's own short text (Epic) as a last resort.
Cached for a month in ~/.cache/aiolaunch/game_details.json.
"""
import html
import re
import threading
import time

from .config import CACHE_DIR, read_json, write_json
from .net import requests

FILE = CACHE_DIR / "game_details.json"
TTL = 30 * 86400
MAX_TEXT = 700
_lock = threading.Lock()
_mem = None


def _cache():
    global _mem
    if _mem is None:
        _mem = read_json(FILE) or {}
    return _mem


def cached(key):
    """The details dict, or None if not fetched (or too old)."""
    with _lock:
        d = _cache().get(key)
    return d if d and time.time() - d.get("t", 0) < TTL else None


def clean(text):
    """Plain text from store HTML, cut at a sentence end near MAX_TEXT characters."""
    text = re.sub(r"<br\s*/?>|</p>", "\n", text or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if len(text) > MAX_TEXT:
        cut = text[:MAX_TEXT]
        end = max(cut.rfind(". "), cut.rfind(".\n"), cut.rfind("! "), cut.rfind("? "))
        text = cut[:end + 1] if end > MAX_TEXT // 2 else cut.rstrip() + "…"
    return text


def _steam(appid):
    r = requests.get("https://store.steampowered.com/api/appdetails", timeout=15,
                     params={"appids": appid, "l": "english", "cc": "us",
                             "filters": "basic,genres,release_date,developers"})
    entry = (r.json() or {}).get(str(appid)) or {}
    if not entry.get("success"):
        return None
    d = entry.get("data") or {}
    year = re.search(r"\b(19|20)\d\d\b", (d.get("release_date") or {}).get("date", ""))
    return {"description": clean(d.get("short_description") or d.get("about_the_game")),
            "genres": [g.get("description", "") for g in d.get("genres") or []][:4],
            "developer": ", ".join((d.get("developers") or [])[:2]),
            "year": year.group(0) if year else ""}


def _gog(gid):
    d = requests.get(f"https://api.gog.com/v2/games/{gid}", timeout=15).json()
    e = d.get("_embedded") or {}
    released = (e.get("product") or {}).get("globalReleaseDate") or ""
    return {"description": clean(d.get("overview") or d.get("description")),
            "genres": [t.get("name", "") for t in e.get("tags") or []][:4],
            "developer": ", ".join(x.get("name", "") for x in (e.get("developers") or [])[:2]),
            "year": released[:4]}


def fetch(game, appid):
    """Blocking (worker thread): find the details, cache them, return the dict ({} if none found)."""
    found = None
    try:
        if game.store == "gog":
            found = _gog(game.id)
        if (not found or not found["description"]) and appid:
            found = _steam(appid) or found
    except (requests.RequestException, ValueError, KeyError, AttributeError):
        found = found or None
    if not found or not found.get("description"):
        own = clean(game.extra.get("description", ""))
        if own:
            found = dict(found or {"genres": [], "developer": "", "year": ""}, description=own)
    result = dict(found or {}, t=time.time())
    with _lock:
        _cache()[game.key] = result
        write_json(FILE, _cache())
    return result

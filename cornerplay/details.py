"""A game's description, genres, developer, release year, screenshots and trailer.

Sources: GOG's own product page for GOG games, Steam's store page for every game with
a known Steam app id, and the store's own short text (Epic) as a last resort.
Cached for a month in ~/.cache/cornerplay/game_details.json.
"""
import html
import re
import threading
import time

from . import timetobeat
from .config import CACHE_DIR, read_json, write_json
from .net import requests

FILE = CACHE_DIR / "game_details.json"
TTL = 30 * 86400
VERSION = 3  # bump when the stored fields change, so older entries are fetched again
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
    if not d or d.get("v") != VERSION or time.time() - d.get("t", 0) >= TTL:
        return None
    if "ttb" not in d and timetobeat.configured() and time.time() - d.get("ttb_tried", 0) > 86400:
        return None  # an IGDB key was added since (or IGDB could not be asked a day ago): fetch again
    return d


def clean(text):
    """Plain text from store HTML, cut at a sentence end near MAX_TEXT characters."""
    text = re.sub(r"<br\s*/?>|</p>", "\n", text or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    # Decoding can bring tags back ("&lt;img src=...&gt;"); store text is shown as plain text,
    # but leave no markup in it either way.
    text = re.sub(r"<[^>]*>?", "", text)
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
                             "filters": "basic,genres,release_date,developers,screenshots,movies,categories"})
    entry = (r.json() or {}).get(str(appid)) or {}
    if not entry.get("success"):
        return None
    d = entry.get("data") or {}
    year = re.search(r"\b(19|20)\d\d\b", (d.get("release_date") or {}).get("date", ""))
    movies = d.get("movies") or []
    movie = next((m for m in movies if m.get("highlight")), movies[0] if movies else {})
    return {"description": clean(d.get("short_description") or d.get("about_the_game")),
            "genres": [g.get("description", "") for g in d.get("genres") or []][:4],
            "developer": ", ".join((d.get("developers") or [])[:2]),
            "year": year.group(0) if year else "",
            # "full", "partial", or "" when Steam lists no controller support at all.
            "controller": d.get("controller_support") or ("partial" if any(
                "controller" in (c.get("description") or "").lower() for c in d.get("categories") or []) else ""),
            "screenshots": [{"thumb": s.get("path_thumbnail", ""), "full": s.get("path_full", "")}
                            for s in (d.get("screenshots") or [])[:12]],
            # Steam serves trailers as HLS / DASH streams; Qt's FFmpeg backend plays HLS.
            "trailer": movie.get("hls_h264") or movie.get("dash_h264") or ""}


def _gog(gid):
    d = requests.get(f"https://api.gog.com/v2/games/{gid}", timeout=15).json()
    e = d.get("_embedded") or {}
    released = (e.get("product") or {}).get("globalReleaseDate") or ""
    shots = []
    for s in (e.get("screenshots") or [])[:12]:
        href = ((s.get("_links") or {}).get("self") or {}).get("href", "")
        if href:
            shots.append({"thumb": href.replace("{formatter}", "product_card_screenshot_748"),
                          "full": href.replace("{formatter}", "1600")})
    return {"description": clean(d.get("overview") or d.get("description")),
            "genres": [t.get("name", "") for t in e.get("tags") or []][:4],
            "developer": ", ".join(x.get("name", "") for x in (e.get("developers") or [])[:2]),
            "year": released[:4], "screenshots": shots, "trailer": ""}


def fetch(game, appid):
    """Blocking (worker thread): find the details, cache them, return the dict ({} if none found)."""
    found, steam = None, None
    try:
        if game.store == "gog":
            found = _gog(game.id)
    except (requests.RequestException, ValueError, KeyError, AttributeError):
        pass
    try:
        if appid:
            steam = _steam(appid)
    except (requests.RequestException, ValueError, KeyError, AttributeError):
        pass
    if steam:  # the store's own page first; Steam fills whatever it lacks (and has the trailers)
        found = dict(steam, **{k: v for k, v in (found or {}).items() if v})
    if not found or not found.get("description"):
        own = clean(game.extra.get("description", ""))
        if own:
            found = dict(found or {"genres": [], "developer": "", "year": ""}, description=own)
    result = dict(found or {}, t=time.time(), v=VERSION)
    ttb = timetobeat.fetch(game.title, appid)
    if ttb is not None:
        result["ttb"] = ttb
        result["ttbLabel"] = timetobeat.label(ttb)
    elif timetobeat.configured():
        result["ttb_tried"] = time.time()  # IGDB could not be asked: again in a day, not on every look
    with _lock:
        _cache()[game.key] = result
        write_json(FILE, _cache())
    return result

"""Find vertical cover art by title for games whose store has none.

Sources, in order: SteamGridDB (when an API key is set in Settings), then
Steam's store search matched against Steam's library art. Results, including
misses, are remembered in ~/.cache/aiolaunch/cover_lookup.json.
"""
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

from .config import CACHE_DIR, read_json, settings, write_json

CACHE_FILE = CACHE_DIR / "cover_lookup.json"
SGDB = "https://www.steamgriddb.com/api/v2"
_lock = threading.Lock()
_NOISE = re.compile(r"\b(game of the year|goty|definitive|complete|deluxe|standard|ultimate|remastered|"
                    r"enhanced|gold|edition|the)\b")


def norm(title: str) -> str:
    t = title.lower().replace("™", "").replace("®", "").replace("&", "and")
    t = _NOISE.sub(" ", t)
    return re.sub(r"[^a-z0-9]+", "", t)


def steam_art(appid):
    """Vertical library art for a Steam app: URL, "" if it has none, None if the call failed."""
    query = {"ids": [{"appid": int(appid)}], "context": {"country_code": "US", "language": "english"},
             "data_request": {"include_assets": True}}
    r = requests.get("https://api.steampowered.com/IStoreBrowseService/GetItems/v1",
                     params={"input_json": json.dumps(query)}, timeout=15)
    if r.status_code != 200:
        return None
    items = r.json().get("response", {}).get("store_items") or []
    assets = (items[0].get("assets") or {}) if items else {}
    name, fmt = assets.get("library_capsule"), assets.get("asset_url_format")
    if not name or not fmt:
        return ""
    return "https://shared.akamai.steamstatic.com/store_item_assets/" + fmt.replace("${FILENAME}", name)


def _steam(title: str):
    """Return a URL, "" for a definite miss, or None when the lookup itself failed."""
    r = requests.get("https://store.steampowered.com/api/storesearch/",
                     params={"term": title, "cc": "us", "l": "en"}, timeout=15)
    if r.status_code != 200:
        return None
    want = norm(title)
    items = [i for i in r.json().get("items", []) if i.get("type") == "app"]
    match = next((i for i in items if norm(i.get("name", "")) == want), None)
    if not match:
        return ""
    return steam_art(match["id"])


def _steamgriddb(title: str, key: str):
    h = {"Authorization": "Bearer " + key}
    r = requests.get(f"{SGDB}/search/autocomplete/{quote(title, safe='')}", headers=h, timeout=15)
    if r.status_code in (401, 403):
        raise PermissionError("SteamGridDB rejected the API key")
    if r.status_code != 200:
        return None
    hits = r.json().get("data") or []
    if not hits:
        return ""
    want = norm(title)
    game = next((g for g in hits if norm(g.get("name", "")) == want), hits[0])
    r = requests.get(f"{SGDB}/grids/game/{game['id']}", headers=h, timeout=15,
                     params={"dimensions": "600x900", "types": "static", "nsfw": "false"})
    if r.status_code != 200:
        return None
    grids = r.json().get("data") or []
    return grids[0]["url"] if grids else ""


def _lookup(title: str, key: str, appid=None):
    found = None
    if appid:  # the store told us exactly which Steam app this is
        found = steam_art(appid)
        if found:
            return found
    if key:
        found = _steamgriddb(title, key)
    if not found:
        steam = _steam(title)
        found = steam if steam is not None else found
    return found


def fill(games) -> str:
    """Set .cover on games that only have wide/square/no art. Returns a warning or ""."""
    todo = [g for g in games if g.store != "steam" and g.id != "battlenet-app"
            and (not g.cover or g.cover == g.cover_fallback)]
    if not todo:
        return ""
    key = settings.get("steamgriddb_key").strip()
    with _lock:
        cache = read_json(CACHE_FILE) or {}
    source = "sgdb" if key else "steam"
    warning = []

    hints = {g.title: g.extra.get("steam_appid") for g in todo if g.extra.get("steam_appid")}

    def one(title):
        try:
            return title, _lookup(title, key, hints.get(title))
        except PermissionError as e:
            warning.append(str(e))
        except (requests.RequestException, ValueError, KeyError):
            pass
        return title, None

    def cache_key(title):
        return f"{source}:{norm(title)}"

    missing = sorted({g.title for g in todo if cache_key(g.title) not in cache})
    if missing:
        with ThreadPoolExecutor(4) as pool:
            for title, url in pool.map(one, missing):
                if url is not None:  # None = lookup failed, try again next refresh
                    cache[cache_key(title)] = url
        with _lock:
            merged = read_json(CACHE_FILE) or {}
            merged.update(cache)
            write_json(CACHE_FILE, merged)
    for g in todo:
        url = cache.get(cache_key(g.title))
        if url:
            g.cover = url
    return warning[0] if warning else ""

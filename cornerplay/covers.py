"""Cover and banner art for every game, from as many sources as can be found.

Covers: the store's own art first; for games whose store has none, SteamGridDB
(when an API key is set in Settings), then Steam's store search matched against
Steam's library art, then Lutris's game database (IGDB box art; no key needed), which
covers games Steam does not sell, such as World of Warcraft and the other Blizzard titles. Results, including misses, are remembered in
~/.cache/cornerplay/cover_lookup.json.

Every game also gets backup covers, wide banner ("hero") art and logos, so the UI can
fall through to the next source when one fails to load: Steam's own asset list
for the matching Steam app (looked up by title for other stores' games, cached),
the store's wide art, and SteamGridDB heroes when a key is set.
"""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from .net import requests

from .config import CACHE_DIR, read_json, settings, write_json

CACHE_FILE = CACHE_DIR / "cover_lookup.json"
ASSETS_FILE = CACHE_DIR / "steam_assets.json"
ASSET_TTL = 2 * 86400  # Steam art URLs carry a version stamp: ask again every 2 days to catch new art
LOOKUP_TTL = 14 * 86400  # covers found by title are looked up again after two weeks...
MISS_TTL = 3 * 86400     # ...and misses after three days
STEAM_ASSETS = "https://shared.akamai.steamstatic.com/store_item_assets/"
STEAM_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps"
SGDB = "https://www.steamgriddb.com/api/v2"
LUTRIS = "https://lutris.net/api/games"
IGDB_IMG = "https://images.igdb.com/igdb/image/upload/t_720p/"  # 540x720 box art
_lock = threading.Lock()
_NOISE = re.compile(r"\b(game of the year|goty|definitive|complete|deluxe|standard|ultimate|remastered|"
                    r"enhanced|gold|edition|the)\b")


def hi_res() -> bool:
    """A sharp screen (1440p and up, or any desktop scaling of 125 % and more): Steam's double-size
    art is worth its download there. Steam's "library_600x900.jpg" is really 300x450 (the 600x900
    one is the _2x file), and its banner is 1920 wide (3840 in _2x, for most games)."""
    size = settings.get("screen_size") or []
    dpr = float(settings.get("screen_dpr") or 1.0)
    return (len(size) == 2 and size[0] >= 2400) or dpr >= 1.25


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


def _lutris(title: str):
    """IGDB box art via Lutris's game list: URL, "" for a definite miss, None when the call failed."""
    r = requests.get(LUTRIS, params={"search": title}, timeout=15)
    if r.status_code != 200:
        return None
    want = norm(title)
    hit = next((g for g in r.json().get("results") or []
                if norm(g.get("name", "")) == want and g.get("coverart")), None)
    if not hit:
        return ""
    # ".../media/igdb/cover_big/co2l7z.jpg": the same picture from IGDB, larger.
    m = re.search(r"/igdb/[^/]+/([A-Za-z0-9_]+)\.(?:jpg|png)$", hit["coverart"])
    return IGDB_IMG + m.group(1) + ".jpg" if m else hit["coverart"]


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
    if not found:
        lutris = _lutris(title)
        found = lutris if lutris is not None else found
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

    def art_title(g):  # a Minecraft instance is named by you; its art is Minecraft's
        return g.extra.get("art_title") or g.title

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

    now = time.time()

    def fresh(k):
        stamp = cache.get(k + "#t", 0)
        if k in cache and not cache[k] and not cache.get(k + "#lutris"):
            return False  # a miss from before Lutris was asked
        return k in cache and now - stamp < (LOOKUP_TTL if cache[k] else MISS_TTL)

    missing = sorted({art_title(g) for g in todo if not fresh(cache_key(art_title(g)))})
    if missing:
        with ThreadPoolExecutor(4) as pool:
            for title, url in pool.map(one, missing):
                if url is not None:  # None = lookup failed, try again next refresh
                    cache[cache_key(title)] = url
                    cache[cache_key(title) + "#t"] = now
                    cache[cache_key(title) + "#lutris"] = 1
        with _lock:
            merged = read_json(CACHE_FILE) or {}
            merged.update(cache)
            write_json(CACHE_FILE, merged)
    for g in todo:
        url = cache.get(cache_key(art_title(g)))
        if url:
            g.cover = url
    return warning[0] if warning else ""


def fill_all(games) -> str:
    """Covers for games without one, then backup covers and banners for every game."""
    warning = fill(games)
    try:
        add_backup_art(games)
    except Exception as e:  # art is never worth failing a refresh
        warning = warning or f"Artwork: {type(e).__name__}: {e}"
    return warning



# --- backup covers and banners --------------------------------------------

def steam_assets(appids) -> dict:
    """{appid: {"cover", "cover2x", "hero", "header"}} from Steam's store API.

    Up to 50 apps per request; cached for ASSET_TTL. These are the exact file names,
    so they work for newer games whose art is not at the old fixed CDN paths.
    """
    appids = sorted({str(a) for a in appids if str(a).isdigit()})
    with _lock:
        cache = read_json(ASSETS_FILE) or {}
    now = time.time()
    stale = [a for a in appids if now - (cache.get(a) or {}).get("t", 0) > ASSET_TTL]
    fresh = {}
    for i in range(0, len(stale), 50):
        chunk = stale[i:i + 50]
        query = {"ids": [{"appid": int(a)} for a in chunk],
                 "context": {"country_code": "US", "language": "english"},
                 "data_request": {"include_assets": True}}
        try:
            r = requests.get("https://api.steampowered.com/IStoreBrowseService/GetItems/v1",
                             params={"input_json": json.dumps(query)}, timeout=20)
            r.raise_for_status()
            items = r.json().get("response", {}).get("store_items") or []
        except (requests.RequestException, ValueError):
            break  # offline: keep what the cache has
        got = {}
        for it in items:
            assets = it.get("assets") or {}
            fmt = assets.get("asset_url_format")

            def url(name, assets=assets, fmt=fmt):
                return STEAM_ASSETS + fmt.replace("${FILENAME}", assets[name]) if fmt and assets.get(name) else ""
            got[str(it.get("appid") or it.get("id"))] = {
                "cover": url("library_capsule"), "cover2x": url("library_capsule_2x"),
                "hero": url("library_hero"), "header": url("header"), "t": now}
        for a in chunk:
            fresh[a] = got.get(a, {"t": now})
    if fresh:
        with _lock:
            merged = read_json(ASSETS_FILE) or {}
            merged.update(fresh)
            write_json(ASSETS_FILE, merged)
        cache.update(fresh)
    return {a: cache.get(a) or {} for a in appids}


def _steam_id(title):
    """Steam app id for a title: int, 0 for a definite miss, None when the lookup failed."""
    r = requests.get("https://store.steampowered.com/api/storesearch/",
                     params={"term": title, "cc": "us", "l": "en"}, timeout=15)
    if r.status_code != 200:
        return None
    want = norm(title)
    items = [i for i in r.json().get("items", []) if i.get("type") == "app"]
    hit = next((i for i in items if norm(i.get("name", "")) == want), None)
    return int(hit["id"]) if hit else 0


def _sgdb_hero(title, key):
    h = {"Authorization": "Bearer " + key}
    r = requests.get(f"{SGDB}/search/autocomplete/{quote(title, safe='')}", headers=h, timeout=15)
    if r.status_code != 200:
        return None
    hits = r.json().get("data") or []
    if not hits:
        return ""
    want = norm(title)
    game = next((g for g in hits if norm(g.get("name", "")) == want), hits[0])
    r = requests.get(f"{SGDB}/heroes/game/{game['id']}", headers=h, timeout=15,
                     params={"types": "static", "nsfw": "false"})
    if r.status_code != 200:
        return None
    heroes = r.json().get("data") or []
    return heroes[0]["url"] if heroes else ""


def _cached_lookups(kind, titles, fn):
    """Run fn(title) for titles not yet in the lookup cache (misses are cached too)."""
    with _lock:
        cache = read_json(CACHE_FILE) or {}
    todo = sorted({t for t in titles if f"{kind}:{norm(t)}" not in cache})
    if todo:
        def one(t):
            try:
                return t, fn(t)
            except (requests.RequestException, ValueError, KeyError):
                return t, None
        found = {}
        with ThreadPoolExecutor(4) as pool:
            for t, v in pool.map(one, todo):
                if v is not None:  # None = the lookup failed; try again next refresh
                    found[f"{kind}:{norm(t)}"] = v
        if found:
            with _lock:
                merged = read_json(CACHE_FILE) or {}
                merged.update(found)
                write_json(CACHE_FILE, merged)
            cache.update(found)
    return {t: cache.get(f"{kind}:{norm(t)}") for t in titles}


def _unique_list(urls):
    out = []
    for u in urls:
        if u and u not in out:
            out.append(u)
    return out


def _add(lst, *urls):
    for u in urls:
        if u and u not in lst:
            lst.append(u)


def add_backup_art(games):
    """Fill g.extra["covers"] (backup portrait covers) and g.extra["heroes"] (wide banners), best first."""
    games = [g for g in games if g.id != "battlenet-app"]
    others = [g for g in games if g.store != "steam" and not g.extra.get("steam_appid")]
    ids = _cached_lookups("appid", [g.title for g in others], _steam_id)
    for g in others:
        if ids.get(g.title):
            g.extra["steam_appid"] = ids[g.title]

    def appid(g):
        return g.id if g.store == "steam" else str(g.extra.get("steam_appid") or "")

    assets = steam_assets(appid(g) for g in games if appid(g))
    key = settings.get("steamgriddb_key").strip()
    sgdb = _cached_lookups("sgdbhero", [g.title for g in games], lambda t: _sgdb_hero(t, key)) if key else {}

    for g in games:
        a = assets.get(appid(g)) or {}
        covers, heroes = [], list(g.extra.get("store_heroes") or [])
        # Steam's current capsule (its URL changes whenever the art does) goes first; the
        # store's own art, which can be an old copy, becomes a backup.
        # Steam's own "portrait.png" is a stand-in it generates when a publisher uploaded no cover
        # (the wide banner on a blurred background): never above real art, only as a last resort.
        generated = "portrait.png" in (a.get("cover") or "")
        sharp = hi_res()
        g.extra["current_cover"] = "" if generated else (sharp and a.get("cover2x")) or a.get("cover", "")
        if g.extra["current_cover"] and g.cover:
            _add(covers, g.cover)
        if not generated:
            _add(covers, a.get("cover2x"), a.get("cover"))
        if appid(g):
            if sharp:
                _add(covers, f"{STEAM_CDN}/{appid(g)}/library_600x900_2x.jpg")
            _add(covers, f"{STEAM_CDN}/{appid(g)}/library_600x900.jpg")
        if sharp and appid(g):  # not every game has it: the next one is tried when it fails
            _add(heroes, f"{STEAM_CDN}/{appid(g)}/library_hero_2x.jpg")
        _add(heroes, a.get("hero"), sgdb.get(g.title))
        if appid(g):
            _add(heroes, f"{STEAM_CDN}/{appid(g)}/library_hero.jpg")
        _add(heroes, g.cover_fallback, a.get("header"))  # wide store art: better than nothing
        logos = list(g.extra.get("store_logos") or [])
        if appid(g):
            _add(logos, f"{STEAM_ASSETS}steam/apps/{appid(g)}/logo.png")
        if generated:
            covers = [u for u in covers if "portrait" not in u] + [a.get("cover"), a.get("cover2x")]
        primary = g.extra["current_cover"] or g.cover
        g.extra["covers"] = [u for u in _unique_list(covers) if u and u != primary]
        g.extra["heroes"] = heroes
        g.extra["logos"] = logos


# --- animated art (TV mode) ------------------------------------------------------------
ANIMATED_FILE = CACHE_DIR / "animated_art.json"
ANIMATED_TTL = 14 * 86400
ANIMATED_MIMES = "image/webp,image/gif"  # what Qt can play (APNG and WebM it cannot)


def _sgdb_game_id(title, appid, h):
    if appid:
        r = requests.get(f"{SGDB}/games/steam/{appid}", headers=h, timeout=15)
        if r.status_code == 200 and (r.json().get("data") or {}).get("id"):
            return r.json()["data"]["id"]
    r = requests.get(f"{SGDB}/search/autocomplete/{quote(title, safe='')}", headers=h, timeout=15)
    if r.status_code in (401, 403):
        raise PermissionError("SteamGridDB rejected the API key")
    hits = (r.json().get("data") or []) if r.status_code == 200 else []
    want = norm(title)
    game = next((g for g in hits if norm(g.get("name", "")) == want), None)
    return game["id"] if game else None


def animated_cached(key):
    hit = (read_json(ANIMATED_FILE) or {}).get(key)
    return hit if hit and time.time() - hit.get("t", 0) < ANIMATED_TTL else None


def animated(key, title, appid, sgdb_key):
    """Animated cover and banner for a game from SteamGridDB: {"grid", "hero"} ("" when there
    is none); None when the lookup failed (tried again next time)."""
    h = {"Authorization": "Bearer " + sgdb_key}
    try:
        gid = _sgdb_game_id(title, appid, h)
        out = {"grid": "", "hero": ""}
        if gid:
            for kind, path, extra in (("grid", "grids", {"dimensions": "600x900,342x482,660x930"}),
                                      ("hero", "heroes", {})):
                r = requests.get(f"{SGDB}/{path}/game/{gid}", headers=h, timeout=15,
                                 params=dict(extra, types="animated", mimes=ANIMATED_MIMES, nsfw="false"))
                if r.status_code == 200:
                    items = r.json().get("data") or []
                    out[kind] = items[0]["url"] if items else ""
    except (requests.RequestException, ValueError, KeyError, PermissionError):
        return None
    with _lock:
        data = read_json(ANIMATED_FILE) or {}
        data[key] = dict(out, t=time.time())
        write_json(ANIMATED_FILE, data)
    return out

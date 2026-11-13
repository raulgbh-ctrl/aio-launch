"""Steam Workshop items a game has (the ones you subscribed to), for its Mods page.

Steam keeps them in <library>/steamapps/workshop/appworkshop_<appid>.acf (what is installed,
its size and when it was updated) and their files in workshop/content/<appid>/<item>/. Titles
and pictures come from Steam's public GetPublishedFileDetails (no key), cached for a day.
Only Steam can subscribe or unsubscribe: "Open in Steam" shows the item's page there.
"""
import os
import time

from . import vdf
from .config import CACHE_DIR, read_json, write_json
from .net import requests
from .storage import nice

DETAILS = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
FILE = CACHE_DIR / "workshop_items.json"
TTL = 86400


def _libraries():
    try:
        from .stores.steam import Steam
        return [lib for lib in Steam().library_dirs() if os.path.isdir(lib)]
    except Exception:
        return []


def installed(appid, libraries=None):
    """{item id: {size, updated, path}} from Steam's own workshop records."""
    out = {}
    for lib in _libraries() if libraries is None else libraries:
        acf = os.path.join(lib, "steamapps", "workshop", f"appworkshop_{appid}.acf")
        if not os.path.isfile(acf):
            continue
        try:
            data = vdf.load(acf)
        except Exception:
            continue
        state = data.get("AppWorkshop") or {}
        for wid, info in (state.get("WorkshopItemsInstalled") or {}).items():
            if not str(wid).isdigit() or not isinstance(info, dict):
                continue
            path = os.path.join(lib, "steamapps", "workshop", "content", str(appid), str(wid))
            out[str(wid)] = {"size": int(info.get("size") or 0), "updated": int(info.get("timeupdated") or 0),
                             "path": path if os.path.isdir(path) else ""}
    return out


def details(ids):
    """{id: {title, preview}} from Steam (cached a day; what is known when offline)."""
    cache = read_json(FILE) or {}
    now = time.time()
    want = [i for i in ids if now - (cache.get(i) or {}).get("t", 0) > TTL]
    for start in range(0, len(want), 100):
        chunk = want[start:start + 100]
        form = {"itemcount": len(chunk), **{f"publishedfileids[{n}]": i for n, i in enumerate(chunk)}}
        try:
            r = requests.post(DETAILS, data=form, timeout=30)
            r.raise_for_status()
            rows = (r.json().get("response") or {}).get("publishedfiledetails") or []
        except Exception:
            break
        for d in rows:
            if str(d.get("publishedfileid")) and d.get("result") == 1:
                cache[str(d["publishedfileid"])] = {"t": now, "title": d.get("title") or "",
                                                    "preview": d.get("preview_url") or ""}
    if want:
        write_json(FILE, cache)
    return {i: cache.get(i) or {} for i in ids}


def items(appid):
    """[{id, title, preview, size, updated, url, steam}] for a game, newest update first."""
    have = installed(appid)
    info = details(list(have))
    out = []
    for wid, h in have.items():
        d = info.get(wid) or {}
        out.append({"id": wid, "title": d.get("title") or f"Workshop item {wid}", "preview": d.get("preview") or "",
                    "size": nice(h["size"]) if h["size"] else "", "updated": h["updated"],
                    "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={wid}",
                    "steam": f"steam://url/CommunityFilePage/{wid}"})
    out.sort(key=lambda r: -r["updated"])
    return out

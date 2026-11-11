"""Steam achievement progress, from Steam's Web API (needs the Web API key from Settings).

Epic and GOG keep achievements to their own clients, so only Steam games show them.
"""
import time

from .net import requests

from .config import CACHE_DIR, read_json, write_json

API = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
FILE = CACHE_DIR / "steam_achievements.json"
TTL = 6 * 3600


_all = {"t": 0, "data": {}}


def progress(appid):
    """0..1 of achievements earned, from what is already stored (no network; any age), or -1."""
    now = time.time()
    if now - _all["t"] > 60:  # re-read the file at most once a minute, not once per cover
        _all["data"], _all["t"] = read_json(FILE) or {}, now
    d = _all["data"].get(str(appid)) or {}
    return d["done"] / d["total"] if d.get("total") else -1.0


def cached(appid):
    d = (read_json(FILE) or {}).get(str(appid))
    return d if d and time.time() - d.get("t", 0) < TTL else None


def fetch(appid, key, steamid):
    """{"done": n, "total": m} ({} when the game has none); None when the call failed."""
    try:
        r = requests.get(API, params={"appid": appid, "key": key, "steamid": steamid}, timeout=15)
    except requests.RequestException:
        return None
    try:
        stats = r.json().get("playerstats") or {}
    except ValueError:
        return None
    if r.status_code == 400 or stats.get("success") is False:
        result = {}  # "Requested app has no stats", or a private profile
    elif r.status_code != 200:
        return None
    else:
        items = stats.get("achievements") or []
        result = {"done": sum(1 for a in items if a.get("achieved")), "total": len(items)} if items else {}
    data = read_json(FILE) or {}
    data[str(appid)] = dict(result, t=time.time())
    write_json(FILE, data)
    return result

"""Achievement progress: Steam's from its Web API (needs the Web API key from Settings), GOG's
from GOG Galaxy's gameplay API with your GOG sign-in. Epic keeps achievements to its own client.

GOG: each game has its own Galaxy client id and secret (in its build manifest). A token for
that client is made from your GOG sign-in (the way GOG Galaxy and gogdl do for cloud saves,
without starting a new session), then gameplay.gog.com lists the game's achievements.
Stored together, GOG games under "gog:<id>".
"""
import time

from .net import requests

from .config import CACHE_DIR, read_json, write_json

API = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
FILE = CACHE_DIR / "steam_achievements.json"
GOG_CLIENTS = CACHE_DIR / "gog_clients.json"  # per game: its Galaxy client id and secret (from the build manifest)
TTL = 6 * 3600


_all = {"t": 0, "data": {}}


def gog_fetch(store, game_id):
    """{"done", "total"} for a GOG game ({} when it has none); None when it could not be asked."""
    import json
    import zlib
    from .config import CACHE_DIR as _C
    user = (read_json(_C / "gog_user.json") or {}).get("galaxyUserId")
    creds = store._creds() if store.logged_in() else None
    if not user or not creds:
        return None
    clients = read_json(GOG_CLIENTS) or {}
    try:
        client = clients.get(game_id)
        if client is None:
            builds = requests.get(f"https://content-system.gog.com/products/{game_id}/os/windows/builds",
                                  params={"generation": 2}, timeout=20).json()
            items = builds.get("items") or []
            client = {}
            if items:
                raw = requests.get(items[0]["link"], timeout=30).content
                try:
                    meta = json.loads(zlib.decompress(raw))
                except zlib.error:
                    meta = json.loads(raw)
                if meta.get("clientId") and meta.get("clientSecret"):
                    client = {"id": meta["clientId"], "secret": meta["clientSecret"]}
            clients[game_id] = client
            write_json(GOG_CLIENTS, clients)
        if not client:
            result = {}
        else:
            r = requests.get("https://auth.gog.com/token", timeout=20, params={
                "client_id": client["id"], "client_secret": client["secret"], "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"], "without_new_session": "1"})
            if not r.ok:
                return None
            token = r.json()["access_token"]
            r = requests.get(f"https://gameplay.gog.com/clients/{client['id']}/users/{user}/achievements",
                             headers={"Authorization": f"Bearer {token}"}, timeout=20)
            if r.status_code == 404:
                result = {}
            else:
                r.raise_for_status()
                items = r.json().get("items") or []
                result = {"done": sum(1 for a in items if a.get("date_unlocked")), "total": len(items)} if items else {}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None
    data = read_json(FILE) or {}
    data["gog:" + game_id] = dict(result, t=time.time())
    write_json(FILE, data)
    _all["t"] = 0
    return result


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

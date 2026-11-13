"""Play with friends: your Steam friends, who is online, and the multiplayer games you share.

Needs the Steam Web API key (Settings > Library) and a public friends list. Friends whose
game details are private show up, but without their games. Numbers come from Steam's Web API
(ISteamUser/GetFriendList, GetPlayerSummaries, IPlayerService/GetOwnedGames); a friend's games
are cached for a day, their status for a minute.
"""
import time

from .config import CACHE_DIR, read_json, settings, write_json
from .net import redact, requests

API = "https://api.steampowered.com"
CACHE = CACHE_DIR / "friends.json"
STATES = {0: "offline", 1: "online", 2: "busy", 3: "away", 4: "snooze", 5: "looking to trade", 6: "looking to play"}


class FriendsError(Exception):
    pass


def _get(path, **params):
    key = (settings.get("steam_api_key") or "").strip()
    if not key:
        raise FriendsError("Add a Steam Web API key in Settings > Library to see your friends")
    try:
        r = requests.get(API + path, params=dict(params, key=key, format="json"), timeout=20)
    except requests.RequestException as e:
        raise FriendsError(f"Could not reach Steam ({redact(e)})") from None
    if r.status_code in (401, 403):
        raise FriendsError("Steam did not accept the Web API key, or your friends list is private")
    if not r.ok:
        raise FriendsError(f"Steam: {r.status_code}")
    return r.json()


def friends(steamid):
    """[{"id", "name", "avatar", "state", "playing"}], online first."""
    ids = [f["steamid"] for f in (_get("/ISteamUser/GetFriendList/v1/", steamid=steamid, relationship="friend")
                                  .get("friendslist") or {}).get("friends") or []]
    out = []
    for i in range(0, len(ids), 100):
        players = (_get("/ISteamUser/GetPlayerSummaries/v2/", steamids=",".join(ids[i:i + 100]))
                   .get("response") or {}).get("players") or []
        for p in players:
            out.append({"id": p.get("steamid", ""), "name": p.get("personaname", "")[:40],
                        "avatar": p.get("avatarfull") or p.get("avatarmedium") or "",
                        "state": STATES.get(int(p.get("personastate") or 0), "online"),
                        "playing": p.get("gameextrainfo", ""), "playingId": str(p.get("gameid", ""))})
    out.sort(key=lambda f: (f["state"] == "offline", not f["playing"], f["name"].lower()))
    return out


def owned(steamid, max_age=86400):
    """{appid: hours} for one friend ({} when their game details are private)."""
    cache = read_json(CACHE, {}) or {}
    hit = (cache.get("owned") or {}).get(steamid)
    if hit and time.time() - hit.get("t", 0) < max_age:
        return hit.get("games") or {}
    try:
        data = _get("/IPlayerService/GetOwnedGames/v1/", steamid=steamid, include_played_free_games=1)
        games = {str(g["appid"]): round(g.get("playtime_forever", 0) / 60, 1)
                 for g in (data.get("response") or {}).get("games") or []}
    except FriendsError:
        games = {}
    cache.setdefault("owned", {})[steamid] = {"t": time.time(), "games": games}
    write_json(CACHE, cache)
    return games


def shared(mine, chosen, is_multiplayer):
    """The multiplayer games everyone chosen owns, from your games ({appid: title}), best first:
    the most of the chosen friends owning it, then the most hours between them.
    chosen: {friend id: {appid: hours}}."""
    rows = []
    for appid, title in mine.items():
        if not is_multiplayer(appid):
            continue
        have = [fid for fid, games in chosen.items() if appid in games]
        if not have:
            continue
        rows.append({"appid": appid, "title": title, "owners": have, "all": len(have) == len(chosen),
                     "hours": round(sum(chosen[f][appid] for f in have), 1)})
    rows.sort(key=lambda r: (-len(r["owners"]), -r["hours"], r["title"].lower()))
    return rows

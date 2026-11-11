"""How long a game takes to finish, from IGDB's official API (game_time_to_beats: players'
reports of a quick run, the main story plus extras, and 100%).

IGDB needs a free Twitch developer app (client id + secret, Settings > Library); without one
nothing is fetched. The access token is kept in ~/.cache/cornerplay/igdb_token.json until it
expires. Results ride along with a game's details (details.py), so they are cached with them.
"""
import json
import time

from .config import CACHE_DIR, read_json, settings, write_private
from .covers import norm
from .net import requests

API = "https://api.igdb.com/v4"
TOKEN_FILE = CACHE_DIR / "igdb_token.json"
STEAM_SOURCE = 1  # IGDB's external game source id for Steam


def configured() -> bool:
    return bool((settings.get("igdb_client_id") or "").strip() and (settings.get("igdb_client_secret") or "").strip())


def _token(cid, secret):
    saved = read_json(TOKEN_FILE) or {}
    if saved.get("id") == cid and saved.get("expires", 0) > time.time() + 60:
        return saved["token"]
    r = requests.post("https://id.twitch.tv/oauth2/token", timeout=15,
                      params={"client_id": cid, "client_secret": secret, "grant_type": "client_credentials"})
    r.raise_for_status()
    d = r.json()
    write_private(TOKEN_FILE, json.dumps({"id": cid, "token": d["access_token"],
                                          "expires": time.time() + int(d.get("expires_in", 0))}))
    return d["access_token"]


def _query(endpoint, body):
    cid = settings.get("igdb_client_id").strip()
    token = _token(cid, settings.get("igdb_client_secret").strip())
    r = requests.post(f"{API}/{endpoint}", data=body, timeout=15,
                      headers={"Client-ID": cid, "Authorization": f"Bearer {token}"})
    if r.status_code == 401:  # token revoked early: start over once
        TOKEN_FILE.unlink(missing_ok=True)
        token = _token(cid, settings.get("igdb_client_secret").strip())
        r = requests.post(f"{API}/{endpoint}", data=body, timeout=15,
                          headers={"Client-ID": cid, "Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def _quote(s):
    return '"' + str(s).replace("\\", "").replace('"', "") + '"'


def _game_id(title, appid):
    if appid:
        hits = _query("external_games", f"fields game; where uid = {_quote(appid)} & external_game_source = {STEAM_SOURCE}; limit 1;")
        if hits and hits[0].get("game"):
            return hits[0]["game"]
    hits = _query("games", f"search {_quote(title)}; fields id,name; where game_type = (0,8,9,10); limit 10;")
    want = norm(title)
    exact = next((h["id"] for h in hits if norm(h.get("name", "")) == want), None)
    return exact  # a near miss is worse than nothing: a sequel's hours would be shown


def hours(seconds):
    """IGDB gives seconds; rounded to whole hours (half hours under 10)."""
    if not seconds:
        return 0
    h = seconds / 3600
    return round(h * 2) / 2 if h < 10 else round(h)


def fetch(title, appid=None) -> dict | None:
    """{"main", "extra", "full"} in hours (0 when IGDB has no reports for that one), {} when
    IGDB does not know the game, None when it could not be asked (no key, no network)."""
    if not configured():
        return None
    try:
        gid = _game_id(title, appid)
        if not gid:
            return {}
        rows = _query("game_time_to_beats", f"fields hastily,normally,completely,count; where game_id = {int(gid)};")
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None
    if not rows:
        return {}
    t = rows[0]
    return {"main": hours(t.get("hastily")), "extra": hours(t.get("normally")), "full": hours(t.get("completely"))}


def label(ttb: dict) -> str:
    """ "Main 12 h · Main + extras 20 h · 100% 45 h", or "" when nothing is known."""
    parts = [(name, ttb.get(k)) for name, k in (("Main", "main"), ("Main + extras", "extra"), ("100%", "full"))]
    return "  ·  ".join(f"{n} {v:g} h" for n, v in parts if v)

"""Games to play together on one screen: local and split-screen multiplayer, from Steam's own
app cache (appinfo.vdf, read by steamappinfo.py), for Steam games and for games from other
stores that match a Steam game. The "Play together" shelf in TV mode and the filter chip."""
LOCAL = {24, 37, 39}   # Shared/Split Screen, ... PvP, ... Co-op
REMOTE = {44}          # Remote Play Together: friends join over the internet

_apps = {}


def load(steam_root):
    """Read the categories once per library refresh (the parse is cached on disk)."""
    global _apps
    if steam_root:
        from . import steamappinfo
        _apps = steamappinfo.apps(steam_root) or {}


def local(appid: str) -> bool:
    return bool(appid) and bool(LOCAL & set((_apps.get(str(appid)) or {}).get("cat") or ()))


# Steam's categories for playing with other people online (or on a LAN): multi-player, co-op,
# online co-op and PvP, cross-platform multiplayer, MMO, LAN.
ONLINE = {1, 9, 20, 27, 36, 38, 47, 48, 49}


def online(appid: str) -> bool:
    return bool(appid) and bool((ONLINE | LOCAL) & set((_apps.get(str(appid)) or {}).get("cat") or ()))


def known(appid: str) -> bool:
    """Steam's app cache describes this app (so a missing category means it really has none)."""
    return str(appid) in _apps

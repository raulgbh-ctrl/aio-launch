"""How long, and how recently, each game was played.

Epic, GOG and Amazon games are timed by the play session (cornerplay.session), which
waits for the game to close. Steam keeps its own record, which the Steam store reads.
Battle.net is not timed: its app stays open after the game closes.
"""
import fcntl
import time

from . import personal
from .config import read_json, write_json

# Per profile and per PC (personal.py): this PC writes its own files; synced PCs' files are added in.
TIMED = ("epic", "gog", "amazon", "custom", "itch", "retro")  # games Cornerplay starts itself and waits for
MIN_SECONDS = 10  # a shorter run is a failed start, not play


def load() -> dict:
    """{"store:id": {"seconds": total, "last": unix time}}, this PC's and the synced PCs' together."""
    own, others = personal.playtime_files("playtime")
    total = {}
    for path in [own] + others:
        data = read_json(path)
        for key, e in (data.items() if isinstance(data, dict) else ()):
            try:  # other PCs' files arrive through the sync folder: skip anything malformed
                seconds, last = int(e.get("seconds", 0)), int(e.get("last", 0))
            except (AttributeError, TypeError, ValueError):
                continue
            t = total.setdefault(key, {"seconds": 0, "last": 0})
            t["seconds"] += max(0, seconds)
            t["last"] = max(t["last"], last)
    return total


def record(key: str, started: float, ended: float | None = None):
    """Add one play session. Safe when two sessions end at once (separate processes)."""
    ended = ended or time.time()
    seconds = int(ended - started)
    if seconds < MIN_SECONDS:
        return
    own, _others = personal.playtime_files("playtime")
    log_path, _ = personal.playtime_files("sessions")
    own.parent.mkdir(parents=True, exist_ok=True)
    with open(own.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = read_json(own) or {}
        entry = data.get(key) or {}
        data[key] = {"seconds": int(entry.get("seconds", 0)) + seconds, "last": int(ended)}
        write_json(own, data)
        log = read_json(log_path) or []
        log.append([key, int(started), int(ended)])
        write_json(log_path, log[-5000:])


def of(game, data: dict) -> tuple[int, int]:
    """(seconds played, last played) for a Game, from Cornerplay's record and Steam's."""
    own = data.get(game.key) or {}
    return (max(int(own.get("seconds", 0)), int(game.extra.get("steam_playtime", 0))),
            max(int(own.get("last", 0)), int(game.extra.get("steam_last_played", 0))))


def sessions() -> list:
    own, others = personal.playtime_files("sessions")
    out = []
    for path in [own] + others:
        data = read_json(path)
        out += [s for s in (data if isinstance(data, list) else [])
                if isinstance(s, list) and len(s) == 3 and isinstance(s[0], str)
                and all(isinstance(x, (int, float)) for x in s[1:])]
    return out

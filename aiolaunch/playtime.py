"""How long, and how recently, each game was played.

Epic, GOG and Amazon games are timed by the play session (aiolaunch.session), which
waits for the game to close. Steam keeps its own record, which the Steam store reads.
Battle.net is not timed: its app stays open after the game closes.
"""
import fcntl
import time

from .config import DATA_DIR, read_json, write_json

FILE = DATA_DIR / "playtime.json"
TIMED = ("epic", "gog", "amazon")
MIN_SECONDS = 10  # a shorter run is a failed start, not play


def load() -> dict:
    """{"store:id": {"seconds": total, "last": unix time}}"""
    return read_json(FILE) or {}


def record(key: str, started: float, ended: float | None = None):
    """Add one play session. Safe when two sessions end at once (separate processes)."""
    ended = ended or time.time()
    seconds = int(ended - started)
    if seconds < MIN_SECONDS:
        return
    FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FILE.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load()
        entry = data.get(key) or {}
        data[key] = {"seconds": int(entry.get("seconds", 0)) + seconds, "last": int(ended)}
        write_json(FILE, data)


def of(game, data: dict) -> tuple[int, int]:
    """(seconds played, last played) for a Game, from AIO Launch's record and Steam's."""
    own = data.get(game.key) or {}
    return (max(int(own.get("seconds", 0)), int(game.extra.get("steam_playtime", 0))),
            max(int(own.get("last", 0)), int(game.extra.get("steam_last_played", 0))))

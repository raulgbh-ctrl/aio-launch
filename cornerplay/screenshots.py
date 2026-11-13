"""Your own screenshots of a game, for its page.

Two places, nothing to set up:
- Steam's screenshots (F12 in a Steam game): userdata/<account>/760/remote/<appid>/screenshots.
- Any screenshot taken while the game was running, with whatever tool you use (the desktop's
  screenshot key, Spectacle, grim, Flameshot, ...): pictures in your screenshot folders whose
  time falls inside one of the game's play sessions (playtime.sessions(): the games Cornerplay
  starts, and Steam games while Cornerplay runs).
Folders looked in: ~/Pictures/Screenshots and ~/Pictures (your XDG pictures folder), plus any in
Settings (screenshot_dirs). Only the folders themselves are read, not everything under them.
"""
import os
import re
from pathlib import Path

from .config import HOME, settings

IMAGE = (".png", ".jpg", ".jpeg", ".webp")
SLACK_BEFORE = 5      # seconds: a session's start is known to within a few seconds
SLACK_AFTER = 30      # Steam sessions are noticed up to 15 s late
LIMIT = 120


def pictures_dir() -> Path:
    """The XDG pictures folder (~/.config/user-dirs.dirs), else ~/Pictures."""
    try:
        text = (HOME / ".config" / "user-dirs.dirs").read_text()
        m = re.search(r'^XDG_PICTURES_DIR="([^"]+)"', text, re.M)
        if m:
            return Path(m.group(1).replace("$HOME", str(HOME)))
    except OSError:
        pass
    return HOME / "Pictures"


def folders() -> list:
    pics = pictures_dir()
    out = [pics / "Screenshots", pics / "screenshots", pics]
    for extra in settings.get("screenshot_dirs") or []:
        if isinstance(extra, str) and extra.strip():
            out.append(Path(os.path.expanduser(extra.strip())))
    seen, uniq = set(), []
    for d in out:
        if d.is_dir() and d.resolve() not in seen:
            seen.add(d.resolve())
            uniq.append(d)
    return uniq


def _images(folder):
    try:
        with os.scandir(folder) as it:
            for e in it:
                if e.is_file() and e.name.lower().endswith(IMAGE):
                    try:
                        yield e.path, e.stat().st_mtime
                    except OSError:
                        pass
    except OSError:
        return


def steam_folder(steam_root, account, appid) -> Path | None:
    if not steam_root or not account or not str(appid).isdigit():
        return None
    d = Path(steam_root) / "userdata" / str(account) / "760" / "remote" / str(appid) / "screenshots"
    return d if d.is_dir() else None


def for_game(keys, sessions, steam_dir=None) -> list:
    """[{"path", "time", "source": "steam"|"session"}], newest first. keys: the game's copies
    ("store:id"); sessions: [[key, start, end], ...]."""
    found = {}
    if steam_dir:
        for path, t in _images(steam_dir):
            found[path] = {"path": path, "time": t, "source": "steam"}
    windows = sorted((s - SLACK_BEFORE, e + SLACK_AFTER) for k, s, e in sessions if k in keys)
    if windows:
        lo, hi = windows[0][0], windows[-1][1]
        for folder in folders():
            for path, t in _images(folder):
                if lo <= t <= hi and path not in found and any(a <= t <= b for a, b in windows):
                    found[path] = {"path": path, "time": t, "source": "session"}
    return sorted(found.values(), key=lambda r: -r["time"])[:LIMIT]


def library(sessions, steam_remote=None, title_of=None, per_game=60, total=1500) -> list:
    """Every screenshot of every game, for the Screenshots page, grouped by game, the game with
    the newest shot first: [{"key", "title", "count", "latest", "shots": [{"path", "time", "source"}]}].
    Folder pictures go to the game whose session they were taken in (one pass over the folders);
    steam_remote (userdata/<account>/760/remote) adds Steam's own F12 screenshots for every app.
    title_of(key) -> title, or "" for a game no longer in the library (left out)."""
    title_of = title_of or (lambda k: k)
    by_key = {}

    def put(key, path, t, source):
        by_key.setdefault(key, {})[path] = {"path": path, "time": t, "source": source}

    if steam_remote and Path(steam_remote).is_dir():
        try:
            apps = [e for e in os.scandir(steam_remote) if e.is_dir() and e.name.isdigit()]
        except OSError:
            apps = []
        for e in apps:
            for path, t in _images(Path(e.path) / "screenshots"):
                put("steam:" + e.name, path, t, "steam")
    windows = sorted((s - SLACK_BEFORE, e + SLACK_AFTER, k) for k, s, e in sessions)
    if windows:
        starts = [w[0] for w in windows]
        import bisect
        for folder in folders():
            for path, t in _images(folder):
                i = bisect.bisect_right(starts, t) - 1
                # the latest session that started before the picture; earlier ones may overlap it
                while i >= 0 and windows[i][0] > t - 86400:
                    a, b, k = windows[i]
                    if a <= t <= b:
                        put(k, path, t, "session")
                        break
                    i -= 1
    games = {}
    for key, shots in by_key.items():
        title = title_of(key)
        if not title:
            continue
        g = games.setdefault(title, {"key": key, "title": title, "shots": {}})
        g["shots"].update(shots)
    out = []
    for g in games.values():
        shots = sorted(g["shots"].values(), key=lambda r: -r["time"])
        out.append({"key": g["key"], "title": g["title"], "count": len(shots),
                    "latest": shots[0]["time"], "shots": shots[:per_game]})
    out.sort(key=lambda g: -g["latest"])
    kept, n = [], 0
    for g in out:
        if n >= total:
            break
        kept.append(g)
        n += len(g["shots"])
    return kept

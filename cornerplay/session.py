"""Runs one game and uploads its cloud saves when it closes.

Cornerplay starts this as a detached process (python3 -m cornerplay.session <file>), so the
upload still happens if Cornerplay itself was closed while you played. The file holds
the game, its command, environment and working folder as JSON. Progress goes to
~/.cache/cornerplay/sessions/<key>.json, which Cornerplay watches to show what happened.
"""
import json
import os
import shutil
import subprocess
import sys
import time

from . import playtime
from .config import CACHE_DIR, write_json
from .stores.base import Game

SESSIONS = CACHE_DIR / "sessions"


def status_file(key):
    return SESSIONS / (key.replace(":", "_").replace("/", "_") + ".json")


def notify(title, body):
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "Cornerplay", "-i", "cornerplay", title, body], check=False)


def run(game, argv, env_extra, cwd, log_path, sync):
    """Run the game, wait for it, then upload saves. Returns the game's exit code."""
    out = status_file(game.key)
    write_json(out, {"key": game.key, "state": "playing", "since": time.time(), "title": game.title})
    env = dict(os.environ)
    env.update(env_extra or {})
    if cwd and not os.path.isdir(cwd):
        cwd = None
    started = time.time()
    presence = None
    try:
        from . import discord
        presence = discord.start(game, started)
    except Exception:
        presence = None  # Discord is a nicety; never in the way of playing
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            # Its own process group, so Quit / Force close in Cornerplay reach Wine's helpers too.
            proc = subprocess.Popen(argv, env=env, cwd=cwd or None, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            write_json(out, {"key": game.key, "state": "playing", "since": started, "title": game.title,
                             "pid": proc.pid})
            code = proc.wait()
        except OSError as e:
            log.write(f"Could not start: {e}\n")
            code = -1
    if presence:
        presence.clear()
    if game.store in playtime.TIMED:
        try:
            playtime.record(game.key, started)
        except OSError:
            pass  # never lose the save upload over a playtime file
    result = {"status": "skipped", "message": ""}
    if sync:
        write_json(out, {"key": game.key, "state": "uploading", "since": time.time(), "title": game.title})
        from . import saves
        result = saves.sync(game, "upload")
        if result["status"] == "conflict":
            notify(f"{game.title}: saves not uploaded",
                   "The cloud has newer saves from another PC. Open Cornerplay to choose which to keep.")
        elif result["status"] == "error":
            notify(f"{game.title}: cloud save upload failed", result["message"])
    write_json(out, {"key": game.key, "state": "done", "exit": code, "sync": result,
                     "title": game.title, "since": time.time(), "started": started, "log": log_path})
    return code


def main(path):
    with open(path, encoding="utf-8") as f:
        job = json.load(f)
    os.remove(path)
    game = Game.from_dict(job["game"])
    run(game, job["argv"], job.get("env"), job.get("cwd"), job["log"], job.get("sync"))


if __name__ == "__main__":
    main(sys.argv[1])

"""Cloud saves for Epic (through legendary) and GOG (through gogdl).

Steam and Battle.net sync saves inside their own clients; Amazon has no cloud
saves. Every function here blocks, so call it from a worker thread or from the
session helper (aiolaunch/session.py), never from the UI thread.

sync() returns a dict:
    status   "ok" | "none" | "conflict" | "error" | "unsupported"
    message  one line for the user
    local / cloud   save dates as text, filled in for a conflict
"""
import json
import os
import re
import subprocess
import zlib

from .net import requests

from .config import CONFIG_DIR, find_tool, read_json, settings, write_json
from .runner import prefix_path

GOG_TIMESTAMPS = CONFIG_DIR / "gog_saves.json"
GOG_LOCATIONS = CONFIG_DIR / "gog_save_locations.json"
SUPPORTED = ("epic", "gog")


def enabled_for(game) -> bool:
    if game.store not in SUPPORTED:
        return False
    from .config import game_options
    override = game_options.get(game.key).get("cloud_saves")
    return bool(settings.get("cloud_saves") if override is None else override)


def _run(argv, env=None, timeout=600):
    full = dict(os.environ)
    full.update(env or {})
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=full)
    except subprocess.TimeoutExpired:
        return None
    return r


def _result(status, message, **extra):
    return {"status": status, "message": message, "local": "", "cloud": "", **extra}


# ---------------------------------------------------------------- prefix
def ensure_prefix(store, game_id):
    """Save paths live inside the Proton prefix, so it must exist before a first sync."""
    pfx = prefix_path(store, game_id, create=True)
    if os.path.isfile(os.path.join(pfx, "user.reg")):
        return pfx
    umu = find_tool("umu-run")
    if umu:
        from .runner import using, wine_env
        with using({}):
            env = wine_env(store, game_id)
        _run([umu, ""], env=env, timeout=900)  # an empty command just creates the prefix
    return pfx


def user_dir(pfx):
    users = os.path.join(pfx, "drive_c", "users")
    for name in ("steamuser", os.environ.get("USER", "")):
        if name and os.path.isdir(os.path.join(users, name)):
            return os.path.join(users, name)
    return os.path.join(users, "steamuser")


# ---------------------------------------------------------------- Epic
_DATE = re.compile(r"(Cloud|Local) save date: (.+)$")


def _epic(game, mode):
    tool = find_tool("legendary")
    if not tool:
        return _result("error", "legendary is missing")
    pfx = ensure_prefix("epic", game.id)
    argv = [tool, "-y", "sync-saves", game.id, "--accept-path"]
    argv += {"download": ["--skip-upload"], "upload": ["--skip-download"],
             "force-download": ["--force-download"], "force-upload": ["--force-upload"]}.get(mode, [])
    r = _run(argv, env={"WINEPREFIX": pfx})
    if r is None:
        return _result("error", "Epic save sync timed out")
    text = (r.stderr or "") + (r.stdout or "")
    if r.returncode != 0:
        lines = [l for l in text.splitlines() if l.strip()]
        errors = [l for l in lines if "ERROR" in l or "CRITICAL" in l]
        line = (errors or lines or ["Epic save sync failed"])[-1]
        return _result("error", line.split("] ", 1)[-1][-200:])
    dates = {m.group(1).lower(): m.group(2).strip() for m in map(_DATE.search, text.splitlines()) if m}
    if "is in conflict" in text:
        return _result("conflict", "Cloud and local saves both changed", **dates)
    if "Downloading remote savegame" in text:
        return _result("ok", "Downloaded cloud save")
    if "Uploading local savegame" in text:
        return _result("ok", "Uploaded save to the cloud")
    if "has not been set" in text or "unprocessed variables" in text:
        return _result("error", "Could not work out where this game keeps its saves")
    if "Checking" not in text:
        return _result("unsupported", "This game has no cloud saves")
    return _result("none", "Saves already up to date")


# ---------------------------------------------------------------- GOG
_GOG_VARS = {
    "<?DOCUMENTS?>": "Documents",
    "<?APPLICATION_DATA_LOCAL?>": "AppData/Local",
    "<?APPLICATION_DATA_LOCAL_LOW?>": "AppData/LocalLow",
    "<?APPLICATION_DATA_ROAMING?>": "AppData/Roaming",
    "<?SAVED_GAMES?>": "Saved Games",
}


def gog_locations(game_id):
    """[{name, location}] from GOG's per-game Galaxy config; cached once fetched."""
    cache = read_json(GOG_LOCATIONS) or {}
    if game_id in cache:
        return cache[game_id]
    builds = requests.get(f"https://content-system.gog.com/products/{game_id}/os/windows/builds",
                          params={"generation": 2}, timeout=20).json()
    items = builds.get("items") or []
    locations = []
    if items:
        raw = requests.get(items[0]["link"], timeout=30).content
        try:
            meta = json.loads(zlib.decompress(raw))
        except zlib.error:
            meta = json.loads(raw)
        client_id = meta.get("clientId")
        if client_id:
            rc = requests.get(f"https://remote-config.gog.com/components/galaxy_client/clients/{client_id}",
                              params={"component_version": "2.0.45"}, timeout=20).json()
            storage = (rc.get("content") or {}).get("Windows", {}).get("cloudStorage") or {}
            if storage.get("enabled"):
                locations = storage.get("locations") or [{
                    "name": "__default",
                    "location": f"<?APPLICATION_DATA_LOCAL?>/GOG.com/Galaxy/Applications/{client_id}/Storage/Shared/Files"}]
    cache[game_id] = locations
    write_json(GOG_LOCATIONS, cache)
    return locations


def _gog_path(location, pfx, install_path):
    path = location.replace("\\\\", "/").replace("\\", "/")
    home = user_dir(pfx)
    for var, rel in _GOG_VARS.items():
        path = path.replace(var, os.path.join(home, rel))
    path = path.replace("<?INSTALL?>", install_path or "")
    return None if "<?" in path else os.path.normpath(path)


def _gog(game, mode):
    tool = find_tool("gogdl")
    if not tool:
        return _result("error", "gogdl is missing")
    from .stores.gog import AUTH_FILE, Gog
    try:
        Gog()._token()  # refresh the token file gogdl reads
        locations = gog_locations(game.id)
    except Exception as e:  # network or not signed in
        return _result("error", f"GOG: {e}")
    if not locations:
        return _result("unsupported", "This game has no cloud saves")
    pfx = ensure_prefix("gog", game.id)
    stamps = read_json(GOG_TIMESTAMPS) or {}
    mine = stamps.setdefault(game.id, {})
    flag = {"download": "--skip-upload", "upload": "--skip-download",
            "force-download": "--force-download", "force-upload": "--force-upload"}.get(mode)
    outcome = []
    for loc in locations:
        path = _gog_path(loc.get("location", ""), pfx, game.install_path)
        if not path:
            continue
        name = loc.get("name") or "__default"
        argv = [tool, "--auth-config-path", str(AUTH_FILE), "save-sync", path, game.id,
                "--os", "windows", "--ts", str(mine.get(name, 0)), "--name", name]
        if flag:
            argv.append(flag)
        r = _run(argv)
        if r is None or r.returncode != 0:
            return _result("error", "GOG save sync failed" + (f": {r.stderr.strip().splitlines()[-1][-160:]}"
                                                           if r and r.stderr.strip() else ""))
        log = r.stderr or ""
        if "in conflict" in log:
            return _result("conflict", "Cloud and local saves both changed",
                           local="newer files on this PC", cloud="newer files in the cloud")
        out = (r.stdout or "").strip().split()
        try:
            mine[name] = float(out[-1])
        except (IndexError, ValueError):
            pass
        if "Uploading files" in log or "No files in cloud, uploading" in log:
            outcome.append("uploaded")
        elif "Downloading files" in log or "No files locally, downloading" in log:
            outcome.append("downloaded")
        elif "Refused" in log:
            outcome.append("refused")
    write_json(GOG_TIMESTAMPS, stamps)
    if "downloaded" in outcome:
        return _result("ok", "Downloaded cloud save")
    if "uploaded" in outcome:
        return _result("ok", "Uploaded save to the cloud")
    if "refused" in outcome:
        return _result("conflict", "Cloud and local saves both changed",
                       local="this PC", cloud="the cloud")
    return _result("none", "Saves already up to date")


def sync(game, mode="both"):
    """mode: download | upload | both | force-download | force-upload"""
    if game.store == "epic":
        return _epic(game, mode)
    if game.store == "gog":
        return _gog(game, mode)
    return _result("unsupported", "Saves for this store are synced by its own app")

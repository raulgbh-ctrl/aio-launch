"""Shaders ready again after a graphics driver update (Settings > Compatibility).

A game's shaders are compiled the first time it needs them, which is the stutter of a first run;
the driver keeps them (the shader cache, runner.py) until the driver changes, when every game
stutters again. Steam avoids that for its own games with Fossilize: a Vulkan layer records which
pipelines a game builds, and after a driver update `fossilize_replay` builds them again in the
background, so they are in the driver's cache before the game asks.

Cornerplay uses Steam's own Fossilize (the layer Steam installs in
~/.local/share/vulkan/implicit_layer.d and its fossilize_replay) for the games it starts from
other stores: while one runs, its pipelines are recorded into ~/.cache/cornerplay/shaders/fossilize/
<game>/; when the graphics driver has changed since, they are replayed one game at a time at the
lowest priority, only on mains power and while no game runs. Steam games are left to Steam.
"""
import glob
import json
import os
import re
import subprocess
from pathlib import Path

from .config import CACHE_DIR, read_json, write_json

ROOT = CACHE_DIR / "shaders" / "fossilize"
STATE = ROOT / "warmed.json"
ENABLE = "ENABLE_VK_LAYER_VALVE_steam_fossilize_1"
LAYER_DIRS = [Path.home() / ".local/share/vulkan/implicit_layer.d", Path("/usr/share/vulkan/implicit_layer.d"),
              Path("/etc/vulkan/implicit_layer.d")]
ICD_DIRS = ["/usr/share/vulkan/icd.d", "/etc/vulkan/icd.d", str(Path.home() / ".local/share/vulkan/icd.d")]
REPLAY_TIMEOUT = 45 * 60


def _layer():
    """Steam's 64-bit Fossilize layer manifest, when Steam has installed it."""
    for d in LAYER_DIRS:
        for f in sorted(d.glob("*fossilize*64*.json")) if d.is_dir() else []:
            try:
                lib = json.loads(f.read_text())["layer"]["library_path"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if os.path.isfile(lib):
                return lib
    return ""


def replayer():
    """Steam's fossilize_replay next to its layer, or one on PATH; "" when there is none."""
    lib = _layer()
    if lib:
        exe = os.path.join(os.path.dirname(lib), "fossilize_replay")
        if os.access(exe, os.X_OK):
            return exe
    from shutil import which
    return which("fossilize-replay") or which("fossilize_replay") or ""


def available():
    return bool(_layer() and replayer())


def folder(store, game_id):
    return ROOT / re.sub(r"[^A-Za-z0-9_.-]", "_", f"{store}_{game_id}")


def record_env(store, game_id):
    """Environment that makes the game's pipelines recorded (nothing for Steam games, which
    Steam records itself, or when Steam's layer is missing)."""
    if store == "steam" or not _layer():
        return {}
    d = folder(store, game_id)
    d.mkdir(parents=True, exist_ok=True)
    return {ENABLE: "1", "STEAM_FOSSILIZE_DUMP_PATH": str(d / "game")}


def driver_id():
    """Changes whenever a Vulkan driver is updated: each ICD library's size and modification time."""
    parts = []
    for d in ICD_DIRS:
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            try:
                lib = json.loads(Path(f).read_text())["ICD"]["library_path"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if not os.path.isabs(lib):
                lib = next((os.path.join(p, lib) for p in ("/usr/lib", "/usr/lib64", "/usr/lib/x86_64-linux-gnu")
                            if os.path.exists(os.path.join(p, lib))), lib)
            try:
                st = os.stat(lib)
                parts.append(f"{os.path.basename(lib)}:{st.st_size}:{int(st.st_mtime)}")
            except OSError:
                pass
    return "|".join(parts)


def _databases(d):
    return sorted(str(p) for p in Path(d).glob("*.foz"))


def mark_warm(store, game_id, driver=None):
    """After a session the game compiled its own shaders with this driver: nothing to replay."""
    state = read_json(STATE, {}) or {}
    state[folder(store, game_id).name] = driver or driver_id()
    write_json(STATE, state)


def pending(driver=None):
    """Recorded games whose shaders were last built with another driver: [folder, ...]."""
    driver = driver or driver_id()
    state = read_json(STATE, {}) or {}
    if not ROOT.is_dir():
        return []
    return [str(d) for d in sorted(ROOT.iterdir())
            if d.is_dir() and _databases(d) and state.get(d.name) != driver]


def replay(d, driver=None):
    """Build one game's recorded pipelines again (blocking: a worker thread). True when done."""
    exe = replayer()
    dbs = _databases(d)
    if not exe or not dbs:
        return False
    threads = max(1, (os.cpu_count() or 2) // 2)
    env = dict(os.environ, MESA_SHADER_CACHE_MAX_SIZE="10G", __GL_SHADER_DISK_CACHE_SIZE="10737418240",
               __GL_SHADER_DISK_CACHE_SKIP_CLEANUP="1")
    env.pop(ENABLE, None)
    ok = True
    for db in dbs:
        try:
            r = subprocess.run(["nice", "-n", "19", exe, db, "--num-threads", str(threads)], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=REPLAY_TIMEOUT)
            ok = ok and r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
    if ok:
        state = read_json(STATE, {}) or {}
        state[Path(d).name] = driver or driver_id()
        write_json(STATE, state)
    return ok

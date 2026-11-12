"""Moving from the regular install to the Flatpak: bring the library over.

The Flatpak keeps its own folders (~/.var/app/<id>/...) and cannot see the regular install's
~/.config/cornerplay, so on its first start it would show a library with nothing signed in.
When the regular install has been used on this PC, the Flatpak offers once to copy over:

- Cornerplay's settings, per-game options, people (favourites, collections, notes, playtime)
  and its GOG and Battle.net sign-ins;
- the Epic (legendary) and Amazon (nile) sign-ins and installed-game lists, and gogdl's
  manifests for installed GOG games;
- the caches that make the first start quick (covers, game details, the library list).

The host's files are read through `flatpak-spawn --host tar` (the sandbox has no access to
them) and only ever written inside the sandbox's own folders. What the Flatpak had before is
kept beside it (<folder>.before-import-<time>), and the regular install is left untouched.
"""
import subprocess
import tarfile
import time

from . import host
from .config import CACHE_DIR, DATA_DIR, XDG_CONFIG, read_json, write_json

ASKED = DATA_DIR / "host_import.json"  # {"asked": time, "imported": time}

# What is copied, per XDG folder: (folder name, parts left out). Paths are relative to the
# host's XDG config / data / cache folder.
CONFIG = ("cornerplay", "legendary", "nile", "heroic_gogdl")
DATA = ("cornerplay",)
CACHE = ("cornerplay",)
SKIP = {
    "data": ("cornerplay/bin",),  # the host's own copies of legendary / gogdl / nile: the Flatpak ships its own
    "cache": ("cornerplay/logs", "cornerplay/update_check.json", "cornerplay/qmlcache", "cornerplay/QtWebEngine",
              "cornerplay/mesa_shader_cache", "cornerplay/shaders", "cornerplay/sessions",
              "cornerplay/qtpipelinecache-x86_64-little_endian-lp64",
              "cornerplay/qtshadercache-x86_64-little_endian-lp64", "cornerplay/Battle.net-Setup.exe"),
    "config": ("legendary/tmp",),
}
TIMEOUT = 600

_SHELL_DIRS = 'printf "%s\\n%s\\n%s" "${XDG_CONFIG_HOME:-$HOME/.config}" "${XDG_DATA_HOME:-$HOME/.local/share}" ' \
              '"${XDG_CACHE_HOME:-$HOME/.cache}"'


def _host(cmd, **kw):
    return subprocess.run(host.argv(cmd), capture_output=True, timeout=kw.pop("timeout", 20), **kw)


def _host_dirs():
    """The host's XDG config, data and cache folders (the sandbox's own variables point elsewhere)."""
    r = _host(["sh", "-c", _SHELL_DIRS], text=True)
    parts = r.stdout.split("\n")
    if r.returncode != 0 or len(parts) != 3 or not all(p.startswith("/") for p in parts):
        raise RuntimeError("could not read the host's folders")
    return dict(zip(("config", "data", "cache"), parts))


def available():
    """True when this is the Flatpak, it has not asked before, and the regular install has a
    library on this PC. Asks the host, so call it off the main thread."""
    if not host.IN_FLATPAK or (read_json(ASKED) or {}).get("asked"):
        return False
    try:
        dirs = _host_dirs()
        r = _host(["sh", "-c", 'test -f "$1/cornerplay/settings.json" || test -f "$1/cornerplay/games.json"',
                   "sh", dirs["config"]])
    except (OSError, subprocess.TimeoutExpired, RuntimeError):
        return False
    return r.returncode == 0


def dismiss():
    """Not now: the offer stays in Settings > Advanced, but no longer opens by itself."""
    data = read_json(ASKED) or {}
    data["asked"] = time.time()
    write_json(ASKED, data)


def _local(kind):
    return {"config": XDG_CONFIG, "data": DATA_DIR.parent, "cache": CACHE_DIR.parent}[kind]


def _safe_members(tar, names, skip):
    """Only regular files, folders and in-tree links under the expected folders; nothing that
    could write outside them (absolute paths, "..", devices) and nothing on the skip list."""
    for m in tar:
        name = m.name[2:] if m.name.startswith("./") else m.name
        parts = name.split("/")
        if not name or name.startswith("/") or ".." in parts or parts[0] not in names:
            continue
        if any(name == s or name.startswith(s + "/") for s in skip):
            continue
        if not (m.isfile() or m.isdir()):
            continue  # links and devices are left out: nothing in these folders needs them
        m.name = name
        yield m


def _copy(kind, host_dir, names):
    """Stream the host's folders into the sandbox's matching folder. Returns the names copied."""
    present = _host(["sh", "-c", 'cd "$1" 2>/dev/null || exit 0; shift; for n; do [ -d "$n" ] && echo "$n"; done',
                     "sh", host_dir, *names], text=True).stdout.split()
    present = [n for n in present if n in names]
    if not present:
        return []
    target = _local(kind)
    target.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for n in present:
        # The sandbox's own settings and sign-ins are kept aside, so nothing it had is lost.
        # Data and caches are merged instead (the host's files win; the Flatpak's own
        # downloads, such as Proton builds, stay).
        here = target / n
        if kind == "config" and here.exists():
            here.rename(target / f"{n}.before-import-{stamp}")
    proc = subprocess.Popen(host.argv(["tar", "-C", host_dir, "-cf", "-", *present]),
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for m in _safe_members(tar, set(present), SKIP.get(kind, ())):
                tar.extract(m, target, filter="data")
    finally:
        proc.stdout.close()
        try:
            proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
    if proc.returncode not in (0, None):
        raise RuntimeError(f"reading the regular install's {kind} folder failed")
    return present


def run():
    """Copy the regular install's library, sign-ins and settings into the Flatpak.
    Returns the config folders copied. Raises RuntimeError when the host cannot be read."""
    if not host.IN_FLATPAK:
        raise RuntimeError("only the Flatpak imports from the regular install")
    try:
        dirs = _host_dirs()
        copied = _copy("config", dirs["config"], CONFIG)
        if "cornerplay" not in copied:
            raise RuntimeError("the regular install has no Cornerplay settings on this PC")
        _copy("data", dirs["data"], DATA)
        _copy("cache", dirs["cache"], CACHE)
    except (OSError, subprocess.TimeoutExpired, tarfile.TarError) as e:
        raise RuntimeError(str(e) or e.__class__.__name__) from e
    data = read_json(ASKED) or {}
    data.update(asked=time.time(), imported=time.time())
    write_json(ASKED, data)
    return copied

"""Disk space: how big each installed game is, and how full each drive is.

Sizes come from the store when it knows them (Steam's SizeOnDisk, legendary's install_size),
otherwise from walking the folder once (cached; a folder is measured again when its
modification time changes, or after a week).
"""
import os
import shutil
import time

from .config import CACHE_DIR, read_json, write_json

FILE = CACHE_DIR / "disk_sizes.json"
TTL = 7 * 86400


def _walk(path):
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                st = os.lstat(os.path.join(root, f))
            except OSError:
                continue
            total += st.st_blocks * 512 if hasattr(st, "st_blocks") else st.st_size
    return total


def size_of(path, known=0):
    """Bytes a game takes (known: what its store reports, used when given)."""
    if known:
        return int(known)
    if not path or not os.path.isdir(path):
        return 0
    cache = read_json(FILE) or {}
    try:
        stamp = int(os.stat(path).st_mtime)
    except OSError:
        return 0
    hit = cache.get(path)
    if hit and hit.get("m") == stamp and time.time() - hit.get("t", 0) < TTL:
        return hit["b"]
    b = _walk(path)
    cache = read_json(FILE) or {}
    cache[path] = {"b": b, "m": stamp, "t": time.time()}
    write_json(FILE, cache)
    return b


def mount_of(path):
    """The mount point a path lives on."""
    path = os.path.realpath(path)
    while not os.path.ismount(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def drive(path):
    mount = mount_of(path)
    try:
        u = shutil.disk_usage(mount)
    except OSError:
        return None
    label = "Home" if mount == mount_of(os.path.expanduser("~")) else os.path.basename(mount) or mount
    return {"mount": mount, "label": label, "total": u.total, "used": u.used, "free": u.free}


def nice(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB", "MB") else f"{n:.1f} {unit}"
        n /= 1024


def leftover_prefixes(prefix_root, wanted):
    """Proton prefixes no installed game uses any more (and prefixes put aside by Reset).
    wanted: the prefix folder names in use. Returns [{"path", "name", "bytes", "size", "reset"}]."""
    out = []
    if not os.path.isdir(prefix_root):
        return out
    for name in sorted(os.listdir(prefix_root)):
        path = os.path.join(prefix_root, name)
        if not os.path.isdir(path) or os.path.islink(path):
            continue
        reset = ".old-" in name
        if name in wanted and not reset:
            continue
        b = _walk(path)
        out.append({"path": path, "name": name, "bytes": b, "size": nice(b), "reset": reset})
    out.sort(key=lambda p: -p["bytes"])
    return out

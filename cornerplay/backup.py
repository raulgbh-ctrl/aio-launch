"""Back up and restore Cornerplay's own settings in one file (for a new PC, or before trying things).

In the backup: settings, per-game options, people (favourites, collections, statuses, notes,
playtime), Blizzard owned list, GOG save locations, first-seen dates.
Left out: store sign-in tokens (sign in again on the new PC; tokens should not travel in a
file), this PC's machine id, caches.
"""
import json
import time
import zipfile
from pathlib import Path

from .config import CONFIG_DIR, DATA_DIR

SKIP = {"gog_auth.json"}           # tokens
SKIP_SETTINGS = {"machine_id"}     # this PC only
VERSION = 1


def _files():
    out = []
    for base, tag in ((CONFIG_DIR, "config"), (DATA_DIR / "people", "data/people")):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.name in SKIP or p.suffix in (".lock", ".tmp"):
                continue
            if tag == "config" and p.relative_to(base).parts[0] == "people" and p.name.endswith(".lock"):
                continue
            out.append((p, f"{tag}/{p.relative_to(base)}"))
    return out


def make(folder=None, label=""):
    """Write Cornerplay-backup-<date><label>.zip into folder (default: home). Returns its path."""
    folder = Path(folder or Path.home())
    stamp = time.strftime("%Y-%m-%d-%H%M")
    path = folder / f"Cornerplay-backup-{stamp}{label}.zip"
    n = 2
    while path.exists():  # never overwrite an earlier backup (two in the same minute)
        path = folder / f"Cornerplay-backup-{stamp}{label}-{n}.zip"
        n += 1
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("cornerplay-backup.json", json.dumps({"version": VERSION, "made": time.time()}))
        for p, name in _files():
            if name == "config/settings.json":
                data = json.loads(p.read_text() or "{}")
                for k in SKIP_SETTINGS:
                    data.pop(k, None)
                z.writestr(name, json.dumps(data, indent=2))
            else:
                z.write(p, name)
    return str(path)


def restore(path):
    """Put a backup's files back. What is there now is saved beside it first (…-before-restore.zip)."""
    path = Path(path)
    with zipfile.ZipFile(path) as z:  # read it all first: nothing below may touch this file
        contents = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
    if "cornerplay-backup.json" not in contents:
        raise ValueError("This is not a Cornerplay backup")
    make(path.parent if path.parent.exists() else None, "-before-restore")
    names = list(contents)
    keep_machine = json.loads((CONFIG_DIR / "settings.json").read_text() or "{}").get("machine_id") \
        if (CONFIG_DIR / "settings.json").exists() else ""
    for name in names:
        if name.endswith("/") or name == "cornerplay-backup.json" or ".." in name:
            continue
        if name.startswith("config/"):
            target = CONFIG_DIR / name[len("config/"):]
        elif name.startswith("data/people/"):
            target = DATA_DIR / "people" / name[len("data/people/"):]
        else:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents[name])
    if keep_machine:
        s = json.loads((CONFIG_DIR / "settings.json").read_text() or "{}")
        s["machine_id"] = keep_machine
        (CONFIG_DIR / "settings.json").write_text(json.dumps(s, indent=2))
    return True

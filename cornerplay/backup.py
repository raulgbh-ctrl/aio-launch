"""Back up and restore Cornerplay's own settings in one file (for a new PC, or before trying things).

In the backup: settings, per-game options, people (favourites, collections, statuses, notes,
playtime), Blizzard owned list, GOG save locations, first-seen dates.
Left out: store sign-in tokens and API keys (sign in and paste the keys again on the new PC;
secrets should not travel in a file), this PC's machine id, caches. Restoring keeps the keys
this PC already has, and only ever writes inside Cornerplay's own folders.
"""
import json
import os
import time
import zipfile
from pathlib import Path

from .config import CONFIG_DIR, DATA_DIR, write_private

SKIP = {"gog_auth.json"}           # tokens
SKIP_SETTINGS = {"machine_id"}     # this PC only
SECRETS = ("steam_api_key", "steamgriddb_key", "igdb_client_id", "igdb_client_secret", "itad_key")  # kept out, kept on restore
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
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # personal notes and stats: this user only
    with os.fdopen(fd, "wb") as raw, zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("cornerplay-backup.json", json.dumps({"version": VERSION, "made": time.time()}))
        for p, name in _files():
            if name == "config/settings.json":
                data = json.loads(p.read_text() or "{}")
                for k in (*SKIP_SETTINGS, *SECRETS):
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
    current = json.loads((CONFIG_DIR / "settings.json").read_text() or "{}") \
        if (CONFIG_DIR / "settings.json").exists() else {}
    keep = {k: current[k] for k in ("machine_id", *SECRETS) if current.get(k)}
    for name in names:
        target = _target(name)
        if target is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.name == "settings.json" or target.parent == CONFIG_DIR:
            write_private(target, contents[name].decode("utf-8", "replace"))
        else:
            target.write_bytes(contents[name])
    if keep:
        s = json.loads((CONFIG_DIR / "settings.json").read_text() or "{}")
        s.update(keep)
        write_private(CONFIG_DIR / "settings.json", json.dumps(s, indent=2))
    return True


def _target(name):
    """Where a backup entry goes, or None for anything that is not one of Cornerplay's own files.
    A backup is a file from outside: names like "config//home/x/.bashrc" or "config/../../x"
    must never write anywhere else."""
    if name.endswith("/") or name == "cornerplay-backup.json" or "\\" in name:
        return None
    for prefix, base in (("config/", CONFIG_DIR), ("data/people/", DATA_DIR / "people")):
        if name.startswith(prefix):
            rel = name[len(prefix):]
            if not rel or rel.startswith("/") or any(p in ("", ".", "..") for p in rel.split("/")):
                return None
            target = (base / rel).resolve()
            return target if target.is_relative_to(base.resolve()) else None
    return None

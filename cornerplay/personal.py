"""What belongs to a person rather than to the PC: favourites, collections, backlog status,
stars, notes, and the playtime Cornerplay records. One store per profile (people sharing a
Steam Deck or a family PC each get their own), optionally synced between PCs.

Layout (per profile, "slug" is the profile's folder name):
    ~/.config/cornerplay/people/<slug>/personal.json   {"games": {key: {..., "t": changed}},
                                                       "collections": [names], "deleted": {name: t}}
    ~/.local/share/cornerplay/people/<slug>/playtime-<machine>.json, sessions-<machine>.json

Sync (Settings > Sync: a folder that Syncthing, Nextcloud, Dropbox ... keeps in step):
    <folder>/Cornerplay/<slug>/personal.json      merged game by game: the newer change wins
    <folder>/Cornerplay/<slug>/playtime-<machine>.json and sessions-<machine>.json
                                                  each PC writes only its own; totals add them up
"""
import os
import re
import socket
import threading
import time
import uuid
from pathlib import Path

from .config import CONFIG_DIR, DATA_DIR, game_options, read_json, settings, write_json

FIELDS = ("collections", "status", "rating", "note")
DEFAULT = "Me"
_lock = threading.RLock()
_docs = {}  # slug -> personal doc (in memory)


def slug(name):
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip()).strip("-").lower()
    return s or "me"


def machine():
    m = settings.get("machine_id") or ""
    if not m:
        m = re.sub(r"[^A-Za-z0-9_-]", "", socket.gethostname())[:24] + "-" + uuid.uuid4().hex[:6]
        settings.set("machine_id", m)
    return m


# --- profiles ------------------------------------------------------------------------
def profiles():
    names = settings.get("profiles")
    names = [n for n in names if isinstance(n, str) and n.strip()] if isinstance(names, list) else []
    return names or [DEFAULT]


def current():
    name = settings.get("profile") or ""
    return name if name in profiles() else profiles()[0]


def add_profile(name):
    name = " ".join(name.split())[:30]
    if not name or slug(name) in {slug(p) for p in profiles()}:
        return ""
    settings.set("profiles", profiles() + [name])
    return name


def remove_profile(name):
    """Forget a profile (its files stay on disk, so adding the same name brings it back)."""
    rest = [p for p in profiles() if p != name]
    if not rest:
        return False
    settings.set("profiles", rest)
    if settings.get("profile") == name:
        settings.set("profile", rest[0])
    return True


def switch(name):
    if name in profiles():
        settings.set("profile", name)


def people_dir(name=None):
    return CONFIG_DIR / "people" / slug(name or current())


def data_dir(name=None):
    return DATA_DIR / "people" / slug(name or current())


# --- the personal doc ----------------------------------------------------------------
def _path(name=None):
    return people_dir(name) / "personal.json"


def _empty():
    return {"games": {}, "collections": [], "deleted": {}}


def doc(name=None):
    s = slug(name or current())
    with _lock:
        if s not in _docs:
            d = read_json(_path(name)) or None
            if d is None:
                d = _migrate() if s == slug(profiles()[0]) else _empty()
                write_json(_path(name), d)
            for k, v in _empty().items():
                d.setdefault(k, v)
            _docs[s] = d
        return _docs[s]


def _migrate():
    """Before profiles: personal fields lived in games.json and settings. Move them to the first profile."""
    d = _empty()
    now = time.time()
    for key, entry in list(game_options.data.items()):
        mine = {f: entry[f] for f in FIELDS if f in entry}
        if mine:
            d["games"][key] = dict(mine, t=now)
    d["collections"] = [n for n in (settings.get("collections") or []) if isinstance(n, str)]
    old_play = DATA_DIR / "playtime.json"
    old_sessions = DATA_DIR / "sessions.json"
    target = data_dir(profiles()[0])
    target.mkdir(parents=True, exist_ok=True)
    for old, new in ((old_play, target / f"playtime-{machine()}.json"),
                     (old_sessions, target / f"sessions-{machine()}.json")):
        if old.exists() and not new.exists():
            old.replace(new)
    return d


def save(name=None):
    with _lock:
        write_json(_path(name), doc(name))
    changed()


def get(key, field):
    return (doc()["games"].get(key) or {}).get(field)


def put(key, field, value):
    with _lock:
        games = doc()["games"]
        entry = dict(games.get(key) or {})
        if value in (None, "", 0, []):
            entry.pop(field, None)
        else:
            entry[field] = value
        entry["t"] = time.time()  # kept even when empty, so a removal syncs too
        games[key] = entry
    save()


def collections():
    return list(doc()["collections"])


def set_collections(names, deleted=None):
    with _lock:
        d = doc()
        d["collections"] = list(names)
        for n in deleted or []:
            d["deleted"][n] = time.time()
        for n in names:
            d["deleted"].pop(n, None)
    save()


# --- playtime files --------------------------------------------------------------------
def playtime_files(kind):
    """This PC's file for "playtime" / "sessions", then the other PCs' (synced in)."""
    own = data_dir() / f"{kind}-{machine()}.json"
    others = [p for p in data_dir().glob(f"{kind}-*.json") if p != own]
    return own, others


# --- sync ------------------------------------------------------------------------------
_listeners = []
_last_sync = {"t": 0, "error": ""}


def on_change(fn):
    _listeners.append(fn)


def changed():
    for fn in _listeners:
        try:
            fn()
        except Exception:
            pass


def sync_root():
    folder = (settings.get("sync_dir") or "").strip()
    return Path(os.path.expanduser(folder)) / "Cornerplay" if folder else None


def _merge(a, b):
    """Two personal docs into one: per game the newer entry, collections by their last change."""
    out = _empty()
    keys = set(a["games"]) | set(b["games"])
    for k in keys:
        x, y = a["games"].get(k), b["games"].get(k)
        out["games"][k] = x if not y or (x and x.get("t", 0) >= y.get("t", 0)) else y
    deleted = dict(a.get("deleted") or {})
    for n, t in (b.get("deleted") or {}).items():
        deleted[n] = max(t, deleted.get(n, 0))
    names = []
    for n in list(a["collections"]) + list(b["collections"]):
        if n not in names:
            names.append(n)
    # A name deleted on one PC stays deleted unless it was (re)made after that; the docs carry
    # no "made" time, so a deletion wins over a plain listing.
    out["collections"] = [n for n in names if n not in deleted]
    out["deleted"] = deleted
    return out


def sync():
    """Merge this PC's personal data with the sync folder, both ways. Returns an error or ""."""
    root = sync_root()
    if not root:
        return ""
    try:
        for name in profiles():
            remote_dir = root / slug(name)
            remote_dir.mkdir(parents=True, exist_ok=True)
            remote = read_json(remote_dir / "personal.json") or _empty()
            for k, v in _empty().items():
                remote.setdefault(k, v)
            with _lock:
                merged = _merge(doc(name), remote)
                _docs[slug(name)] = merged
                write_json(_path(name), merged)
            write_json(remote_dir / "personal.json", merged)
            # playtime: send this PC's files, take the other PCs'
            local = data_dir(name)
            local.mkdir(parents=True, exist_ok=True)
            for kind in ("playtime", "sessions"):
                own = local / f"{kind}-{machine()}.json"
                if own.exists():
                    write_json(remote_dir / own.name, read_json(own))
                for theirs in remote_dir.glob(f"{kind}-*.json"):
                    if theirs.name != own.name:
                        write_json(local / theirs.name, read_json(theirs))
        # profiles made on another PC
        known = {slug(p) for p in profiles()}
        for d in root.iterdir() if root.exists() else []:
            if d.is_dir() and d.name not in known and (d / "personal.json").exists():
                settings.set("profiles", profiles() + [d.name.replace("-", " ").title()])
        _last_sync.update(t=time.time(), error="")
    except OSError as e:
        _last_sync.update(t=time.time(), error=str(e))
    return _last_sync["error"]


def last_sync():
    return dict(_last_sync)

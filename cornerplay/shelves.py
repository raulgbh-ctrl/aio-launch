"""Favourites, the user's own collections, and when each game first showed up.

A game's collections live in the profile's personal data (personal.py, "collections": [ids]) on
every store's copy, like "hidden", so a game owned twice is in a collection once.
Collection names are kept per profile (personal.py), in the order they were made.
The favourites collection has the fixed id "fav".

first_seen.json remembers when each game key first came back from its store, so
"Recently added" can list new purchases. The first time a store is read every game it
has is stamped 0 (already owned), so the shelf starts empty instead of listing everything.
"""
import os
import time

from . import personal
from .config import CONFIG_DIR, read_json, write_json

FAV = "fav"
SEEN_FILE = CONFIG_DIR / "first_seen.json"
RECENT_DAYS = 45  # "Recently added" covers games that arrived in the last six weeks or so


def names():
    return [n for n in personal.collections() if isinstance(n, str) and n]


def ids_of(key):
    return list(personal.get(key, "collections") or [])


def in_group(group, cid):
    return any(cid in ids_of(g.key) for g in group)


def set_member(group, cid, on):
    for g in group:
        ids = [i for i in ids_of(g.key) if i != cid]
        if on:
            ids.append(cid)
        personal.put(g.key, "collections", ids)


def create(name):
    name = " ".join(name.split())[:40]
    if not name or name.lower() in ("favourites", "favorites") or name in names():
        return ""
    personal.set_collections(names() + [name])
    return name


def delete(name):
    personal.set_collections([n for n in names() if n != name], deleted=[name])
    for key, entry in list(personal.doc()["games"].items()):
        if name in (entry.get("collections") or []):
            personal.put(key, "collections", [i for i in entry["collections"] if i != name])


# --- recently added ----------------------------------------------------------
_seen = None


def _load():
    global _seen
    if _seen is None:
        _seen = read_json(SEEN_FILE, {}) or {}
        _seen.setdefault("stores", [])
        _seen.setdefault("keys", {})
    return _seen


def note(store_id, keys):
    """Stamp the keys a store returned that were not known before. Returns True if any were new."""
    seen = _load()
    first_time = store_id not in seen["stores"]
    now = int(time.time())
    new = False
    for k in keys:
        if k not in seen["keys"]:
            seen["keys"][k] = 0 if first_time else now
            new = True
    if first_time:
        seen["stores"].append(store_id)
    if new or first_time:
        write_json(SEEN_FILE, seen)
    return new


def added(group):
    """When the game arrived: bought (first seen since Cornerplay knew the store) or installed."""
    keys = _load()["keys"]
    bought = max((keys.get(g.key, 0) for g in group), default=0)
    return max(bought, installed_at(group))


def is_recent(group):
    return added(group) > time.time() - RECENT_DAYS * 86400


NEW_DAYS = 7  # the "New" ribbon on a cover: bought or claimed in the last week


def is_new(group):
    """Bought or claimed in the last week (not merely installed): the cover gets a New ribbon
    until the game is played. Games already owned when a store was first connected never count."""
    keys = _load()["keys"]
    return max((keys.get(g.key, 0) for g in group), default=0) > time.time() - NEW_DAYS * 86400


# --- backlog status, your rating, your note --------------------------------------
# Kept on every copy of a game, like collections. Status: "playing", "want", "finished", "dropped".
STATUSES = [("playing", "Playing"), ("want", "Want to play"), ("finished", "Finished"), ("dropped", "Dropped")]
STATUS_NAMES = dict(STATUSES)


def meta(group, name):
    """The first copy's value of status / rating / note (all copies are kept the same)."""
    for g in group:
        v = personal.get(g.key, name)
        if v not in (None, ""):
            return v
    return "" if name != "rating" else 0


def set_meta(group, name, value):
    for g in group:
        personal.put(g.key, name, value)


# --- recently installed ------------------------------------------------------------
_mtimes = {}


def installed_at(group):
    """When the newest installed copy's folder was made (a cheap stand-in for the install date)."""
    best = 0
    for g in group:
        if not g.installed or not g.install_path:
            continue
        t = _mtimes.get(g.install_path)
        if t is None:
            try:
                st = os.stat(g.install_path)
                t = int(getattr(st, "st_birthtime", 0) or st.st_ctime)
            except OSError:
                t = 0
            _mtimes[g.install_path] = t
        best = max(best, t)
    return best


def forget_install_times():
    _mtimes.clear()

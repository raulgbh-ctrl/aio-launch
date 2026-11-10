"""Favourites, the user's own collections, and when each game first showed up.

A game's collections live in its per-game options (games.json, "collections": [ids]) on
every store's copy, like "hidden", so a game owned twice is in a collection once.
Collection names are kept in settings ("collections"), in the order they were made.
The favourites collection has the fixed id "fav".

first_seen.json remembers when each game key first came back from its store, so
"Recently added" can list new purchases. The first time a store is read every game it
has is stamped 0 (already owned), so the shelf starts empty instead of listing everything.
"""
import time

from .config import CONFIG_DIR, game_options, read_json, settings, write_json

FAV = "fav"
SEEN_FILE = CONFIG_DIR / "first_seen.json"
RECENT_DAYS = 45  # "Recently added" covers games that arrived in the last six weeks or so


def names():
    value = settings.get("collections")
    return [n for n in value if isinstance(n, str) and n] if isinstance(value, list) else []


def ids_of(key):
    return list(game_options.get(key).get("collections") or [])


def in_group(group, cid):
    return any(cid in ids_of(g.key) for g in group)


def set_member(group, cid, on):
    for g in group:
        ids = [i for i in ids_of(g.key) if i != cid]
        if on:
            ids.append(cid)
        game_options.set(g.key, "collections", ids or None)


def create(name):
    name = " ".join(name.split())[:40]
    if not name or name.lower() in ("favourites", "favorites") or name in names():
        return ""
    settings.set("collections", names() + [name])
    return name


def delete(name):
    settings.set("collections", [n for n in names() if n != name])
    for key, entry in list(game_options.data.items()):
        if name in (entry.get("collections") or []):
            game_options.set(key, "collections", [i for i in entry["collections"] if i != name] or None)


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
    """When the newest copy of a game arrived (0 = it was already there)."""
    keys = _load()["keys"]
    return max((keys.get(g.key, 0) for g in group), default=0)


def is_recent(group):
    return added(group) > time.time() - RECENT_DAYS * 86400

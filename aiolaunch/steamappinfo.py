"""What the Steam client knows about the apps in this account's library: Steam's own
binary caches, appcache/appinfo.vdf (formats 27, 28 and 29) and appcache/packageinfo.vdf
(the account's licences; used to leave out games only ever lent for a free weekend).

The client keeps an entry for every app it can show in the library (owned, free games
played, family-shared), so its "game" entries are the Library tab's games, with their
names, and no network is needed. Parsed once per change of the file and remembered in
~/.cache/aiolaunch/steam_appinfo.json.
"""
import os
import re
import struct

from .config import CACHE_DIR, read_json, write_json

CACHE = CACHE_DIR / "steam_appinfo.json"
PACKAGES_CACHE = CACHE_DIR / "steam_free_weekends.json"
MAGICS = {0x07564427: 27, 0x07564428: 28, 0x07564429: 29}
VERSION = 2  # bump when the remembered fields change


def _parse(data):
    magic = struct.unpack_from("<I", data, 0)[0]
    version = MAGICS.get(magic)
    if not version:
        raise ValueError("unknown appinfo.vdf format %08x" % magic)
    pos = 8
    strings = None
    if version >= 29:  # keys are indexes into a string table at the end of the file
        table = struct.unpack_from("<q", data, pos)[0]
        pos += 8
        count = struct.unpack_from("<I", data, table)[0]
        strings = [s.decode("utf-8", "replace") for s in data[table + 4:].split(b"\0")[:count]]

    def key(p):
        if strings is not None:
            return strings[struct.unpack_from("<i", data, p)[0]], p + 4
        end = data.index(b"\0", p)
        return data[p:end].decode("utf-8", "replace"), end + 1

    def kv(p, depth=0):
        out = {}
        while True:
            t = data[p]
            p += 1
            if t == 8:
                return out, p
            k, p = key(p)
            if t == 0:
                v, p = kv(p, depth + 1)
            elif t == 1:
                end = data.index(b"\0", p)
                v, p = data[p:end].decode("utf-8", "replace"), end + 1
            elif t in (2, 3):
                v, p = struct.unpack_from("<i" if t == 2 else "<f", data, p)[0], p + 4
            elif t == 7:
                v, p = struct.unpack_from("<Q", data, p)[0], p + 8
            else:
                raise ValueError(f"value type {t}")
            out[k] = v

    apps = {}
    while pos + 8 <= len(data):
        appid, size = struct.unpack_from("<II", data, pos)
        if appid == 0:
            break
        pos += 8
        start = pos + 4 + 4 + 8 + 20 + 4 + (20 if version >= 28 else 0)
        try:
            info, _ = kv(start)
        except (ValueError, IndexError, struct.error):
            pos += size
            continue
        common = (info.get("appinfo") or info).get("common") or {}
        extended = (info.get("appinfo") or info).get("extended") or {}
        # Regional editions ("Borderlands 2 RU") point their manual at the main game's id.
        manual = re.search(r"/manual/(\d+)", str(extended.get("GameManualURL", "")))
        variant_of = manual.group(1) if manual and manual.group(1) != str(appid) else ""
        apps[str(appid)] = {"name": str(common.get("name", "")), "type": str(common.get("type", "")).lower(),
                            "variant_of": variant_of}
        pos += size
    return apps


def apps(root):
    """{appid: {"name", "type"}} from <root>/appcache/appinfo.vdf, or {} if unreadable."""
    path = os.path.join(str(root), "appcache", "appinfo.vdf")
    try:
        st = os.stat(path)
    except OSError:
        return {}
    stamp = [path, st.st_mtime, st.st_size, VERSION]
    cached = read_json(CACHE) or {}
    if cached.get("stamp") == stamp:
        return cached.get("apps") or {}
    try:
        with open(path, "rb") as f:
            result = _parse(f.read())
    except (OSError, ValueError, struct.error):
        return {}
    write_json(CACHE, {"stamp": stamp, "apps": result})
    return result


def _binary_kv(data, p, key):
    """Steam's binary KeyValues at p -> (dict, next position). key(p) reads one key."""
    out = {}
    while True:
        t = data[p]
        p += 1
        if t == 8:
            return out, p
        k, p = key(p)
        if t == 0:
            v, p = _binary_kv(data, p, key)
        elif t == 1:
            end = data.index(b"\0", p)
            v, p = data[p:end].decode("utf-8", "replace"), end + 1
        elif t in (2, 3):
            v, p = struct.unpack_from("<i" if t == 2 else "<f", data, p)[0], p + 4
        elif t == 7:
            v, p = struct.unpack_from("<Q", data, p)[0], p + 8
        else:
            raise ValueError(f"value type {t}")
        out[k] = v


def _free_weekend_only(data):
    """App ids whose only licences here are free-weekend ones (lent for a few days, then gone)."""
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic not in (0x06565527, 0x06565528):
        raise ValueError("unknown packageinfo.vdf format %08x" % magic)

    def key(p):
        end = data.index(b"\0", p)
        return data[p:end].decode("utf-8", "replace"), end + 1

    pos, kept, weekend = 8, set(), set()
    while pos + 4 <= len(data):
        pid = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if pid == 0xFFFFFFFF:
            break
        pos += 20 + 4 + (8 if magic >= 0x06565528 else 0)  # sha1, change number, token
        info, pos = _binary_kv(data, pos, key)
        body = info.get(str(pid)) or next(iter(info.values()), {})
        lent = str((body.get("extended") or {}).get("freeweekend", "0")) == "1"
        for appid in (body.get("appids") or {}).values():
            (weekend if lent else kept).add(str(appid))
    return sorted(weekend - kept)


def free_weekend_only(root):
    """Games this account only had for a free weekend; {} if Steam's licence cache is unreadable."""
    path = os.path.join(str(root), "appcache", "packageinfo.vdf")
    try:
        st = os.stat(path)
    except OSError:
        return set()
    stamp = [path, st.st_mtime, st.st_size]
    cached = read_json(PACKAGES_CACHE) or {}
    if cached.get("stamp") == stamp:
        return set(cached.get("apps") or [])
    try:
        with open(path, "rb") as f:
            apps_ = _free_weekend_only(f.read())
    except (OSError, ValueError, IndexError, struct.error):
        return set()
    write_json(PACKAGES_CACHE, {"stamp": stamp, "apps": apps_})
    return set(apps_)

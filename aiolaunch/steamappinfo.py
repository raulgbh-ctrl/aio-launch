"""What the Steam client knows about the apps in this account's library: Steam's own
binary cache, appcache/appinfo.vdf (formats 27, 28 and 29).

The client keeps an entry for every app it can show in the library (owned, free games
played, family-shared), so its "game" entries are the Library tab's games, with their
names, and no network is needed. Parsed once per change of the file and remembered in
~/.cache/aiolaunch/steam_appinfo.json.
"""
import os
import struct

from .config import CACHE_DIR, read_json, write_json

CACHE = CACHE_DIR / "steam_appinfo.json"
MAGICS = {0x07564427: 27, 0x07564428: 28, 0x07564429: 29}


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
        apps[str(appid)] = {"name": str(common.get("name", "")), "type": str(common.get("type", "")).lower()}
        pos += size
    return apps


def apps(root):
    """{appid: {"name", "type"}} from <root>/appcache/appinfo.vdf, or {} if unreadable."""
    path = os.path.join(str(root), "appcache", "appinfo.vdf")
    try:
        st = os.stat(path)
    except OSError:
        return {}
    stamp = [path, st.st_mtime, st.st_size]
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

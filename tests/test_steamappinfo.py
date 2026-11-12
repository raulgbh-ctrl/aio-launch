import struct

import pytest

from cornerplay import steamappinfo

MAGIC = {27: 0x07564427, 28: 0x07564428, 29: 0x07564429}


def _kv(obj, key):
    out = b""
    for k, v in obj.items():
        if isinstance(v, dict):
            out += b"\x00" + key(k) + _kv(v, key)
        elif isinstance(v, int):
            out += b"\x02" + key(k) + struct.pack("<i", v)
        else:
            out += b"\x01" + key(k) + v.encode() + b"\0"
    return out + b"\x08"


def build(version, apps):
    """A minimal appinfo.vdf in the given format: {appid: kv dict}."""
    strings = []

    def key(k):
        if version < 29:
            return k.encode() + b"\0"
        if k not in strings:
            strings.append(k)
        return struct.pack("<i", strings.index(k))

    body = b""
    for appid, info in apps.items():
        head = struct.pack("<IIQ", 2, 0, 0) + b"\0" * 20 + struct.pack("<I", 1) + (b"\0" * 20 if version >= 28 else b"")
        entry = head + _kv(info, key)
        body += struct.pack("<II", appid, len(entry)) + entry
    body += struct.pack("<I", 0)
    header = struct.pack("<II", MAGIC[version], 1)
    if version < 29:
        return header + body
    table_at = len(header) + 8 + len(body)
    table = struct.pack("<I", len(strings)) + b"".join(s.encode() + b"\0" for s in strings)
    return header + struct.pack("<q", table_at) + body + table


APPS = {
    570: {"appinfo": {"appid": 570, "common": {"name": "Dota 2", "type": "Game"}}},
    49521: {"appinfo": {"common": {"name": "Borderlands 2 RU", "type": "game"},
                        "extended": {"GameManualURL": "https://store.steampowered.com/manual/49520/"}}},
    49520: {"appinfo": {"common": {"name": "Borderlands 2", "type": "game",
                                   "category": {"category_1": 1, "category_39": 1, "category_9": 1}},
                        "extended": {"GameManualURL": "https://store.steampowered.com/manual/49520/"}}},
    228980: {"appinfo": {"common": {"name": "Steamworks Common Redistributables", "type": "Tool"}}},
}


@pytest.mark.parametrize("version", [27, 28, 29])
def test_parse_each_format(version):
    apps = steamappinfo._parse(build(version, APPS))
    assert apps["570"] == {"name": "Dota 2", "type": "game", "variant_of": "", "cat": []}
    assert apps["49520"]["cat"] == [1, 9, 39]  # Steam's store categories: 39 is split-screen co-op
    assert apps["228980"]["type"] == "tool"
    assert apps["49521"]["variant_of"] == "49520"  # a regional edition points at the main game
    assert apps["49520"]["variant_of"] == ""


def test_unknown_magic():
    with pytest.raises(ValueError):
        steamappinfo._parse(struct.pack("<II", 0x12345678, 1))


def test_apps_reads_and_caches(tmp_path):
    (tmp_path / "appcache").mkdir()
    (tmp_path / "appcache" / "appinfo.vdf").write_bytes(build(29, APPS))
    first = steamappinfo.apps(tmp_path)
    assert first["570"]["name"] == "Dota 2"
    assert steamappinfo.apps(tmp_path) == first  # second call comes from the cache
    assert steamappinfo.apps(tmp_path / "missing") == {}

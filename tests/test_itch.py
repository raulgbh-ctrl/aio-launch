import io
import json
import os
import zipfile

from cornerplay import itchdl
from cornerplay.config import settings
from cornerplay.stores import itch


class Resp:
    def __init__(self, data=None, body=b"", status=200):
        self._data, self.body, self.status_code, self.ok = data, body, status, status < 400
        self.headers = {"Content-Length": str(len(body))}
        self.text = ""
    def json(self): return self._data
    def raise_for_status(self): pass
    def iter_content(self, n): yield self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o755 if data.startswith(b"\x7fELF") else 0o644) << 16
            z.writestr(info, data)
    return buf.getvalue()


def test_pick_prefers_platform_and_skips_extras():
    ups = [{"id": 1, "type": "soundtrack", "traits": ["p_linux"], "size": 9},
           {"id": 2, "type": "default", "traits": ["p_windows"], "size": 5},
           {"id": 3, "type": "default", "traits": ["p_linux"], "size": 4, "demo": True},
           {"id": 4, "type": "default", "traits": ["p_linux"], "size": 3}]
    assert itchdl.pick(ups, "linux") == (ups[3], "linux")
    assert itchdl.pick(ups, "windows") == (ups[1], "windows")
    assert itchdl.pick(ups[:2], "linux") == (ups[1], "windows")  # no Linux build: Windows through Proton


def test_find_program(tmp_path):
    (tmp_path / "Game_Data").mkdir()
    (tmp_path / "Game_Data" / "lib.so").write_bytes(b"\x7fELF")
    (tmp_path / "UnityCrashHandler64.exe").write_bytes(b"MZ")
    (tmp_path / "Game.exe").write_bytes(b"MZ" * 10)
    assert itchdl.find_program(tmp_path, "windows") == "Game.exe"
    (tmp_path / "Game.x86_64").write_bytes(b"\x7fELF")
    assert itchdl.find_program(tmp_path, "linux") == "Game.x86_64"


def test_zip_cannot_escape(tmp_path):
    z = tmp_path / "evil.zip"
    z.write_bytes(_zip({"../../escaped": b"x", "ok/file": b"y"}))
    dest = tmp_path / "dest"
    dest.mkdir()
    assert itchdl._safe_extract(str(z), str(dest))
    assert (dest / "ok" / "file").exists() and not (tmp_path.parent / "escaped").exists()


def test_library_install_and_launch(tmp_path, monkeypatch):
    monkeypatch.setitem(settings.data, "games_dir", str(tmp_path / "Games"))
    itch.AUTH_FILE.write_text(json.dumps({"api_key": "k", "username": "me"}))
    payload = _zip({"MyGame/MyGame.x86_64": b"\x7fELF" + b"0" * 50, "MyGame/data.pak": b"d"})

    def get(url, params=None, headers=None, timeout=None, stream=False):
        assert headers["Authorization"] == "Bearer k"
        if url.endswith("/profile/owned-keys"):
            return Resp({"per_page": 50, "owned_keys": [
                {"id": 77, "game_id": 5, "game": {"id": 5, "title": "My Game", "cover_url": "https://img/c.png",
                                                  "classification": "game", "traits": ["p_linux", "p_windows"]}},
                {"id": 78, "game_id": 6, "game": {"id": 6, "title": "A Soundtrack", "classification": "soundtrack"}}]})
        if url.endswith("/games/5/uploads"):
            assert params["download_key_id"] == "77"
            return Resp({"uploads": [{"id": 900, "type": "default", "traits": ["p_linux"], "filename": "mygame.zip",
                                      "size": len(payload)}]})
        if url.endswith("/uploads/900/download"):
            return Resp(body=payload)
        raise AssertionError(url)
    monkeypatch.setattr(itch.requests, "get", get, raising=False)
    monkeypatch.setattr(itchdl.requests, "get", get, raising=False)
    store = itch.Itch()
    assert store.logged_in() and store.account() == "me"
    games = store.fetch()
    assert [g.title for g in games] == ["My Game"] and not games[0].installed
    cmd = store.install(games[0])
    itchdl.main(*cmd.argv[3:])
    g = store.fetch()[0]
    assert g.installed
    launch = store.launch(g)
    assert launch.argv[-1].endswith("MyGame/MyGame.x86_64") and os.access(launch.argv[-1], os.X_OK)
    store.uninstall(g)
    assert not store.fetch()[0].installed
    itch.AUTH_FILE.unlink()

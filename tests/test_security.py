"""The protections around files and data that come from outside."""
import json
import os
import stat
import zipfile

import pytest

from cornerplay import backup, details, net, personal, playtime
from cornerplay.config import CONFIG_DIR, settings, write_private


def test_redact_hides_keys_and_tokens():
    msg = ("403 Client Error: Forbidden for url: https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
           "?key=ABCDEF123&steamid=7656&format=json")
    out = net.redact(msg)
    assert "ABCDEF123" not in out and "steamid=7656" in out
    assert "tok123" not in net.redact("Authorization: Bearer tok123")
    assert "s3cr3t" not in net.redact("x?client_secret=s3cr3t&refresh_token=r1")


def test_private_files(tmp_path):
    f = tmp_path / "a.json"
    write_private(f, "{}")
    assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_settings_and_config_dir_are_private():
    settings.set("card_size", settings.get("card_size"))
    assert stat.S_IMODE((CONFIG_DIR / "settings.json").stat().st_mode) == 0o600
    assert stat.S_IMODE(CONFIG_DIR.stat().st_mode) == 0o700


def _evil_backup(path, names):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("cornerplay-backup.json", "{}")
        for n in names:
            z.writestr(n, "pwned")


@pytest.mark.parametrize("name", ["config//tmp/pwned-abs", "config/../../pwned-up", "data/people/../../../pwned",
                                  "config/sub/../../pwned2", "other/pwned"])
def test_restore_never_writes_outside(tmp_path, name):
    evil = tmp_path / "b.zip"
    _evil_backup(evil, [name])
    assert backup._target(name) is None
    backup.restore(evil)
    assert not os.path.exists("/tmp/pwned-abs")
    assert not (CONFIG_DIR.parent / "pwned-up").exists()


def test_backup_leaves_out_keys_and_restore_keeps_them(tmp_path):
    settings.set("steam_api_key", "MYKEY")
    settings.set("igdb_client_secret", "MYSECRET")
    path = backup.make(tmp_path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    with zipfile.ZipFile(path) as z:
        saved = json.loads(z.read("config/settings.json"))
    assert "steam_api_key" not in saved and "igdb_client_secret" not in saved
    backup.restore(path)
    assert json.loads((CONFIG_DIR / "settings.json").read_text())["steam_api_key"] == "MYKEY"
    settings.data.update(steam_api_key="", igdb_client_secret="")


def test_store_text_cannot_smuggle_markup():
    out = details.clean('Fun &lt;img src="file:///etc/passwd"&gt; game <b>bold</b> &amp; more')
    assert "<" not in out and "img" not in out and "& more" in out


def test_malformed_sync_data_is_dropped():
    m = personal._merge({"games": [], "collections": "x", "deleted": 5},
                        {"games": {"a:1": {"t": "soon"}, "a:2": {"rating": 4, "t": 3}}, "collections": [1, "Co-op"]})
    assert m["games"] == {"a:2": {"rating": 4, "t": 3}} and m["collections"] == ["Co-op"]


def test_malformed_playtime_from_another_pc():
    own, _ = personal.playtime_files("playtime")
    own.parent.mkdir(parents=True, exist_ok=True)
    own.with_name("playtime-evil.json").write_text(json.dumps({"x:1": {"seconds": "lots"}, "x:2": 5, "x:3": {"seconds": 7}}))
    own.with_name("sessions-evil.json").write_text(json.dumps([["x:3", "a", 1], ["x:3", 1, 2], "junk"]))
    data = playtime.load()
    assert data["x:3"]["seconds"] == 7 and "x:1" not in data
    assert ["x:3", 1, 2] in playtime.sessions()


def test_update_downloads_only_from_this_project():
    from cornerplay import updates
    with pytest.raises(RuntimeError):
        updates.download("https://evil.example/cornerplay.run")
    with pytest.raises(RuntimeError):
        updates.download("https://github.com/someone-else/cornerplay/releases/download/v1/cornerplay.run")


def test_download_checked_rejects_mismatch(tmp_path, monkeypatch):
    class R:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, n): yield b"payload"
    monkeypatch.setattr(net.requests, "get", lambda *a, **k: R(), raising=False)
    with pytest.raises(RuntimeError):
        net.download_checked("https://x/y", tmp_path / "y", sha256="00" * 32)
    assert not (tmp_path / "y").exists() and not (tmp_path / "y.part").exists()
    import hashlib
    net.download_checked("https://x/y", tmp_path / "y", sha256=hashlib.sha256(b"payload").hexdigest(), mode=0o755)
    assert (tmp_path / "y").read_bytes() == b"payload"

import io
import zipfile

from cornerplay import humbledl
from cornerplay.stores import humble

ORDERS = {
    "KEY1": {"subproducts": [
        {"machine_name": "celeste", "human_name": "Celeste", "icon": "https://x/celeste.png", "url": "https://celeste",
         "downloads": [
             {"platform": "linux", "download_struct": [
                 {"name": "64-bit .deb", "url": {"web": "https://dl.humble.com/celeste.deb?t=1"}, "file_size": 10, "md5": ""},
                 {"name": "64-bit .tar.gz", "url": {"web": "https://dl.humble.com/celeste-linux.tar.gz?t=1"}, "file_size": 9, "md5": ""},
                 {"name": "32-bit .tar.gz", "url": {"web": "https://dl.humble.com/celeste-linux32.tar.gz?t=1"}, "file_size": 8, "md5": ""}]},
             {"platform": "windows", "download_struct": [
                 {"name": "Installer", "url": {"web": "https://dl.humble.com/celeste-setup.exe?t=1"}, "file_size": 20, "md5": ""},
                 {"name": "Zip", "url": {"web": "https://dl.humble.com/celeste.zip?t=1"}, "file_size": 19, "md5": ""}]},
             {"platform": "audio", "download_struct": [{"name": "MP3", "url": {"web": "https://dl/ost.zip"}, "file_size": 5}]}]},
        {"machine_name": "celeste_soundtrack", "human_name": "Celeste OST",
         "downloads": [{"platform": "audio", "download_struct": [{"name": "MP3", "url": {"web": "https://dl/ost.zip"}}]}]},
        {"machine_name": "book", "human_name": "A book", "downloads": [{"platform": "ebook", "download_struct": []}]}]},
    "KEY2": {"subproducts": [  # bought again in another bundle: listed once
        {"machine_name": "celeste", "human_name": "Celeste", "downloads": [
            {"platform": "windows", "download_struct": [{"name": "Zip", "url": {"web": "https://dl/c.zip"}, "file_size": 1}]}]},
        {"machine_name": "ftl", "human_name": "FTL", "downloads": [
            {"platform": "windows", "download_struct": [{"name": "Installer", "url": {"web": "https://dl/ftl.exe"}, "file_size": 3}]}]}]},
}


def test_games_in_orders():
    games = {g["machine"]: g for g in humble.games_in(ORDERS)}
    assert set(games) == {"celeste", "ftl"}            # no soundtracks or books
    assert games["celeste"]["linux"] and games["celeste"]["windows"] and games["celeste"]["gamekey"] == "KEY1"
    assert not games["ftl"]["linux"] and games["ftl"]["windows"]


def test_pick_file():
    files = humble.downloads(ORDERS["KEY1"]["subproducts"][0])
    assert humbledl.pick(files["linux"], "linux")["name"] == "64-bit .tar.gz"   # not the .deb, not 32-bit
    assert humbledl.pick(files["windows"], "windows")["name"] == "Zip"          # an archive before an installer


def test_mojosetup_unpacks_without_running(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("scripts/mojosetup_init.lua", "--")
        z.writestr("data/noarch/game.x86_64", "\x7fELF....")
        z.writestr("data/noarch/assets/a.pak", "x")
    sh = tmp_path / "game-installer.sh"
    sh.write_bytes(b"#!/bin/sh\necho installer\nexit 0\n" + buf.getvalue())
    staging = tmp_path / "game"
    staging.mkdir()
    humbledl._unpack_linux(str(sh), str(staging))
    assert (staging / "game.x86_64").exists() and (staging / "assets" / "a.pak").exists()
    assert humbledl.find_program(str(staging), "linux") == "game.x86_64"


def test_cookie_paste_forms(monkeypatch, tmp_path):
    monkeypatch.setattr(humble, "AUTH_FILE", tmp_path / "auth.json")
    seen = []
    monkeypatch.setattr(humble, "signed_in", lambda jar: seen.append(jar) or True)
    humble.Humble().login_finish('_simpleauth_sess="abc123|def"; Path=/')
    assert seen[-1] == {"_simpleauth_sess": "abc123|def"} and humble.cookie() == "abc123|def"
    humble.Humble().login_finish("abc123|def")
    assert seen[-1] == {"_simpleauth_sess": "abc123|def"}
    humble.Humble().login_finish("ory_session_x=s1; csrf_token_y=c2")  # the new sign-in's cookies
    assert humble.cookies() == {"ory_session_x": "s1", "csrf_token_y": "c2"}
    monkeypatch.setattr(humble, "signed_in", lambda jar: False)
    try:
        humble.Humble().login_finish("ory_session_x=gone")
        raise AssertionError("an unknown session was accepted")
    except humble.StoreError:
        pass


def test_find_program_skips_helpers(tmp_path):
    from cornerplay import unpack
    (tmp_path / "Game_Data").mkdir()
    (tmp_path / "Game_Data" / "lib.so").write_bytes(b"\x7fELF")
    (tmp_path / "UnityCrashHandler64.exe").write_bytes(b"MZ")
    (tmp_path / "Game.exe").write_bytes(b"MZ" * 10)
    assert unpack.find_program(tmp_path, "windows") == "Game.exe"
    (tmp_path / "Game.x86_64").write_bytes(b"\x7fELF")
    assert unpack.find_program(tmp_path, "linux") == "Game.x86_64"


def test_zip_cannot_escape(tmp_path):
    import io
    import zipfile
    from cornerplay import unpack
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../../escaped", b"x")
        z.writestr("ok/file", b"y")
    archive = tmp_path / "evil.zip"
    archive.write_bytes(buf.getvalue())
    dest = tmp_path / "dest"
    dest.mkdir()
    assert unpack._safe_extract(str(archive), str(dest))
    assert (dest / "ok" / "file").exists() and not (tmp_path.parent / "escaped").exists()

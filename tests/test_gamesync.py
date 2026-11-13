import time

from cornerplay import config, gamesync


def _pc(tmp_path, name, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / name)
    (tmp_path / name).mkdir()
    return config.GameOptions()


def test_settings_travel_and_newer_wins(tmp_path, monkeypatch):
    shared = tmp_path / "sync"
    shared.mkdir()
    a = _pc(tmp_path, "a", monkeypatch)
    b = _pc(tmp_path, "b", monkeypatch)
    a.set("gog:1", "proton", "/home/x/.steam/compatibilitytools.d/GE-Proton11-12")
    a.set("gog:1", "mangohud", True)
    a.set("gog:1", "cover", "/home/x/pic.png")  # a file on that PC: stays there
    monkeypatch.setattr(gamesync, "game_options", a)
    gamesync.sync(shared, builds=[])
    monkeypatch.setattr(gamesync, "game_options", b)
    assert gamesync.sync(shared, builds=["/opt/steam/compatibilitytools.d/GE-Proton11-12"]) == 1
    got = b.get("gog:1")
    assert got["proton"] == "/opt/steam/compatibilitytools.d/GE-Proton11-12"
    assert got["mangohud"] is True and "cover" not in got
    # later B changes it; A takes B's change
    time.sleep(0.01)
    b.times["gog:1"] = time.time() + 5
    b.data["gog:1"]["mangohud"] = False
    gamesync.sync(shared, builds=[])
    monkeypatch.setattr(gamesync, "game_options", a)
    assert gamesync.sync(shared, builds=[]) == 1
    assert a.get("gog:1")["mangohud"] is False
    # B had no matching Proton build on A's side: A keeps its own
    assert a.get("gog:1")["proton"].endswith("GE-Proton11-12")


def test_unknown_proton_build_keeps_local_choice(tmp_path, monkeypatch):
    shared = tmp_path / "sync"
    shared.mkdir()
    a = _pc(tmp_path, "a", monkeypatch)
    b = _pc(tmp_path, "b", monkeypatch)
    a.set("epic:2", "proton", "/x/Proton-Weird")
    b.set("epic:2", "proton", "GE-Proton")
    b.times["epic:2"] = 0
    monkeypatch.setattr(gamesync, "game_options", a)
    gamesync.sync(shared, builds=[])
    monkeypatch.setattr(gamesync, "game_options", b)
    gamesync.sync(shared, builds=[])
    assert b.get("epic:2")["proton"] == "GE-Proton"

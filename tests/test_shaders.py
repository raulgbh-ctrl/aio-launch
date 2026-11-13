from cornerplay import shaders


def test_replays_only_after_the_driver_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(shaders, "ROOT", tmp_path)
    monkeypatch.setattr(shaders, "STATE", tmp_path / "warmed.json")
    monkeypatch.setattr(shaders, "replayer", lambda: "/bin/true")
    game = tmp_path / "gog_1"
    game.mkdir()
    (game / "game.abc.1.foz").write_bytes(b"x")
    (tmp_path / "gog_2").mkdir()  # never recorded anything: nothing to do
    assert shaders.pending("drv1") == [str(game)]
    assert shaders.replay(str(game), "drv1")
    assert shaders.pending("drv1") == []
    assert shaders.pending("drv2") == [str(game)]  # the driver was updated
    shaders.mark_warm("gog", "1", "drv2")
    assert shaders.pending("drv2") == []


def test_steam_games_are_left_to_steam(monkeypatch):
    monkeypatch.setattr(shaders, "_layer", lambda: "/x.so")
    assert shaders.record_env("steam", "1") == {}

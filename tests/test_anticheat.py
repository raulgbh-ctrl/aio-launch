from cornerplay import protons, runner


def test_runtimes_found_in_any_steam_library(tmp_path, monkeypatch):
    root, lib2 = tmp_path / "Steam", tmp_path / "games"
    (root / "steamapps" / "common" / "Proton BattlEye Runtime").mkdir(parents=True)
    (lib2 / "steamapps" / "common" / "Proton EasyAntiCheat Runtime").mkdir(parents=True)
    monkeypatch.setattr(protons, "steam_roots", lambda: [str(root)])
    monkeypatch.setattr(protons, "_steam_libraries", lambda r: [str(root), str(lib2)])
    found = runner.anticheat_runtimes()
    assert found["PROTON_EAC_RUNTIME"].endswith("games/steamapps/common/Proton EasyAntiCheat Runtime")
    assert found["PROTON_BATTLEYE_RUNTIME"].endswith("Steam/steamapps/common/Proton BattlEye Runtime")


def test_nothing_when_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(protons, "steam_roots", lambda: [str(tmp_path)])
    monkeypatch.setattr(protons, "_steam_libraries", lambda r: [str(tmp_path)])
    assert runner.anticheat_runtimes() == {}

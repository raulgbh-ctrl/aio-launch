import pytest

from cornerplay.problems import explain


@pytest.mark.parametrize("log, fix", [
    ("./game: error while loading shared libraries: libSDL2-2.0.so.0: cannot open", "native"),
    ("write failed: No space left on device", "storage"),
    ("err: DXVK: No adapters found", "vulkan"),
    ("Starting EasyAntiCheat_EOS service", ""),
    ("err:module:import_dll Library MSVCP140.dll (needed by game.exe) not found", "vcrun"),
    ("err:module:load mscoree.dll failed", "dotnet"),
    ("wine: Unhandled page fault on read access", "proton"),
    ("err:module:import_dll Library xinput9.dll (needed by x) not found", "proton"),
])
def test_rules(log, fix):
    assert explain(log)["fix"] == fix


def test_names_the_missing_library():
    assert "libSDL2-2.0.so.0" in explain("x: error while loading shared libraries: libSDL2-2.0.so.0: no")["detail"]


def test_vulkan_beats_anticheat_when_both_appear():
    assert explain("EasyAntiCheat\nVK_ERROR_INITIALIZATION_FAILED")["fix"] == "vulkan"


@pytest.mark.parametrize("log", ["", None, "all fine, game exited normally"])
def test_nothing_recognisable(log):
    assert explain(log) == {}

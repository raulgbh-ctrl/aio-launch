import os
import time

from cornerplay import cleanup, workshop


def touch(path, data=b"x" * 100, age_days=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    if age_days:
        t = time.time() - age_days * 86400
        os.utime(path, (t, t))
        os.utime(os.path.dirname(path), (t, t))


def test_orphan_shader_caches(tmp_path):
    lib = tmp_path / "lib"
    touch(str(lib / "steamapps/appmanifest_10.acf"), b"x")
    touch(str(lib / "steamapps/shadercache/10/a.bin"))       # installed: kept
    touch(str(lib / "steamapps/shadercache/20/a.bin"))       # uninstalled: found
    touch(str(lib / "steamapps/shadercache/3000000000/a"))   # a non-Steam shortcut: kept
    other = tmp_path / "lib2"
    touch(str(other / "steamapps/appmanifest_30.acf"), b"x")
    touch(str(lib / "steamapps/shadercache/30/a.bin"))       # installed in another library: kept
    found = cleanup.orphan_shader_caches([str(lib), str(other)])
    assert found == [(str(lib / "steamapps/shadercache/20"), "20")]


def test_crash_dumps(tmp_path):
    game = tmp_path / "Game"
    touch(str(game / "crash_old.dmp"), age_days=3)
    touch(str(game / "crash_new.dmp"))                                  # under a day: kept
    touch(str(game / "Proj/Saved/Crashes/UE-1/minidump.dmp"), age_days=5)
    touch(str(game / "Proj/Saved/SaveGames/slot1.sav"), age_days=5)     # saves: never
    pfx = tmp_path / "pfx"
    touch(str(pfx / "drive_c/users/steamuser/AppData/LocalLow/Studio/Game/Crashes/c1/error.log"), age_days=2)
    touch(str(pfx / "drive_c/users/steamuser/AppData/Local/CrashDumps/game.exe.123.dmp"), age_days=2)
    found = cleanup.crash_dumps([str(game)], [str(pfx)])
    assert found == sorted([str(game / "crash_old.dmp"), str(game / "Proj/Saved/Crashes"),
                            str(pfx / "drive_c/users/steamuser/AppData/LocalLow/Studio/Game/Crashes"),
                            str(pfx / "drive_c/users/steamuser/AppData/Local/CrashDumps")])


def test_redist_and_delete(tmp_path):
    played, unplayed = tmp_path / "A", tmp_path / "B"
    touch(str(played / "_CommonRedist/vcredist/x64.exe"))
    touch(str(played / "Redist/runtime.dll"))  # not a known installer folder: kept
    touch(str(unplayed / "_CommonRedist/DirectX/dx.exe"))
    found = cleanup.redist_installers([str(played)])
    assert found == [str(played / "_CommonRedist")]
    freed = cleanup.delete(found + [str(unplayed / "_CommonRedist")], set(found))
    assert freed > 0 and not (played / "_CommonRedist").exists()
    assert (unplayed / "_CommonRedist").exists() and (played / "Redist/runtime.dll").exists()


def test_scan_totals(tmp_path):
    game = tmp_path / "G"
    touch(str(game / "__redist/setup.exe"), b"y" * 5000)
    r = cleanup.scan([str(game)], [str(game)], [])
    redist = next(g for g in r["groups"] if g["id"] == "redist")
    assert redist["count"] == 1 and redist["bytes"] >= 5000 and r["bytes"] >= redist["bytes"]


def test_workshop_installed(tmp_path):
    lib = tmp_path / "lib"
    acf = lib / "steamapps/workshop/appworkshop_646570.acf"
    touch(str(acf), b'''"AppWorkshop"
{
    "appid"     "646570"
    "WorkshopItemsInstalled"
    {
        "1610056683"
        {
            "size"          "4096"
            "timeupdated"   "1700000000"
            "manifest"      "123"
        }
    }
}''')
    os.makedirs(lib / "steamapps/workshop/content/646570/1610056683")
    items = workshop.installed("646570", [str(lib)])
    assert items == {"1610056683": {"size": 4096, "updated": 1700000000,
                                    "path": str(lib / "steamapps/workshop/content/646570/1610056683")}}
    assert workshop.installed("1", [str(lib)]) == {}

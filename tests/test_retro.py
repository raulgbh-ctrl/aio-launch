from cornerplay.config import settings
from cornerplay.stores import retro


def test_scan_systems_titles_and_launch(tmp_path, monkeypatch):
    roms = tmp_path / "ROMs"
    for rel in ("snes/Super Metroid (Japan, USA) (En,Ja).sfc", "PlayStation/Final Fantasy VII (USA)/FF7.m3u",
                "PlayStation/Final Fantasy VII (USA)/FF7 (Disc 1).cue", "gba/Minish Cap (Europe).gba",
                "psp/Lumines (USA).iso", "misc/random.iso", "misc/notes.txt", "arcade/sf2.zip", "gb/Tetris (World).zip"):
        p = roms / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"rom")
    monkeypatch.setitem(settings.data, "rom_dirs", [str(roms)])
    found = {(sid, p.name) for sid, p in retro.scan()}
    assert found == {("snes", "Super Metroid (Japan, USA) (En,Ja).sfc"), ("psx", "FF7.m3u"), ("gba", "Minish Cap (Europe).gba"),
                     ("psp", "Lumines (USA).iso"), ("arcade", "sf2.zip"), ("gb", "Tetris (World).zip")}
    games = {g.extra["system"]: g for g in retro.Retro().fetch()}
    assert games["snes"].title == "Super Metroid"
    assert games["snes"].cover.endswith("Nintendo%20-%20Super%20Nintendo%20Entertainment%20System/Named_Boxarts/"
                                         "Super%20Metroid%20%28Japan%2C%20USA%29%20%28En%2CJa%29.png")
    cores = tmp_path / "cores"
    cores.mkdir()
    (cores / "bsnes_libretro.so").write_bytes(b"")
    monkeypatch.setattr(retro, "retroarch", lambda: (["/usr/bin/retroarch"], [cores]))
    cmd = retro.Retro().launch(games["snes"])
    assert cmd.argv == ["/usr/bin/retroarch", "-f", "-L", str(cores / "bsnes_libretro.so"), games["snes"].extra["rom"]]
    try:
        retro.Retro().launch(games["gba"])
        raise AssertionError("no gba core: should say so")
    except retro.StoreError as e:
        assert "Game Boy Advance" in str(e)

import io
import os
import zipfile

import pytest

from cornerplay import mods


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(mods, "ROOT", tmp_path / "mods")
    game = tmp_path / "game"
    game.mkdir()
    return tmp_path, game


def make_zip(path, files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    path.write_bytes(buf.getvalue())
    return str(path)


def tree(root):
    return sorted(os.path.relpath(os.path.join(b, f), root) for b, _d, fs in os.walk(root) for f in fs)


def test_game_for():
    assert mods.game_for("Valheim") == "valheim"
    assert mods.game_for("The Elder Scrolls V: Skyrim Special Edition") == "skyrimspecialedition"
    assert mods.game_for("Whatever", "413150") == "stardewvalley"
    assert mods.game_for("Brotato") == ""


def test_bepinex_layout(tmp_path):
    raw = tmp_path / "raw"
    for rel in ("manifest.json", "icon.png", "Cool.dll", "plugins/Extra.dll", "config/cool.cfg", "patchers/P.dll"):
        (raw / rel).parent.mkdir(parents=True, exist_ok=True)
        (raw / rel).write_text("x")
    out = tmp_path / "out"
    out.mkdir()
    mods.layout_bepinex(str(raw), str(out), "Me-Cool")
    assert tree(out) == ["BepInEx/config/cool.cfg", "BepInEx/patchers/Me-Cool/P.dll",
                         "BepInEx/plugins/Me-Cool/Cool.dll", "BepInEx/plugins/Me-Cool/Extra.dll"]


def test_smapi_layout(home):
    tmp, game = home
    z = make_zip(tmp / "m.zip", {"Pack/ModA/manifest.json": "{}", "Pack/ModA/a.dll": "x", "Pack/ModB/manifest.json": "{}"})
    mods.install_archive("stardewvalley", "nx:1", z, {"name": "Pack", "source": "nexus"})
    mods.deploy("stardewvalley", str(game))
    assert tree(game) == ["Mods/ModA/a.dll", "Mods/ModA/manifest.json", "Mods/ModB/manifest.json"]


FOMOD = """<?xml version="1.0" encoding="utf-16"?>
<config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="x.xsd">
  <moduleName>Test</moduleName>
  <requiredInstallFiles><folder source="Core" destination="" /></requiredInstallFiles>
  <installSteps order="Explicit"><installStep name="Main"><optionalFileGroups order="Explicit">
    <group name="Size" type="SelectExactlyOne"><plugins order="Explicit">
      <plugin name="2K"><files><file source="Opt\\2k.dds" destination="textures\\t.dds" /></files>
        <conditionFlags><flag name="res">2k</flag></conditionFlags>
        <typeDescriptor><type name="Optional"/></typeDescriptor></plugin>
      <plugin name="4K"><files><file source="Opt\\4k.dds" destination="textures\\t.dds" /></files>
        <conditionFlags><flag name="res">4k</flag></conditionFlags>
        <typeDescriptor><type name="Recommended"/></typeDescriptor></plugin>
    </plugins></group>
  </optionalFileGroups></installStep></installSteps>
  <conditionalFileInstalls><patterns>
    <pattern><dependencies operator="And"><flagDependency flag="res" value="4k"/></dependencies>
      <files><file source="Opt\\hd.esp" destination="hd.esp"/></files></pattern>
    <pattern><dependencies operator="And"><flagDependency flag="res" value="2k"/></dependencies>
      <files><file source="Opt\\sd.esp" destination="sd.esp"/></files></pattern>
  </patterns></conditionalFileInstalls>
</config>"""


def test_bethesda_fomod_and_plugins(home, tmp_path):
    tmp, game = home
    z = make_zip(tmp / "f.zip", {"fomod/ModuleConfig.xml": FOMOD.encode("utf-16"), "Core/Main.esp": "x",
                                 "Opt/2k.dds": "2", "Opt/4k.dds": "4", "Opt/hd.esp": "h", "Opt/sd.esp": "s"})
    gid = "skyrimspecialedition"
    mods.install_archive(gid, "nx:2", z, {"name": "Textures", "source": "nexus"})
    prefix = tmp_path / "pfx"
    txt = prefix / "drive_c/users/steamuser/AppData/Local/Skyrim Special Edition/plugins.txt"
    txt.parent.mkdir(parents=True)
    txt.write_text("*ccBGSSSE001-Fish.esm\n")
    mods.deploy(gid, str(game), str(prefix))
    assert tree(game) == ["Data/Main.esp", "Data/hd.esp", "Data/textures/t.dds"]
    assert (game / "Data/textures/t.dds").read_text() == "4"  # the recommended choice
    assert txt.read_text().split() == ["*ccBGSSSE001-Fish.esm", "*Main.esp", "*hd.esp"]
    mods.set_enabled(gid, "nx:2", False)
    mods.deploy(gid, str(game), str(prefix))
    assert tree(game) == [] and txt.read_text().split() == ["*ccBGSSSE001-Fish.esm"]


def test_bethesda_loose_files(home):
    tmp, game = home
    z = make_zip(tmp / "l.zip", {"MyMod/meshes/a.nif": "m", "MyMod/MyMod.esp": "p", "MyMod/readme.txt": "r"})
    mods.install_archive("fallout4", "nx:3", z, {"name": "Loose", "source": "nexus"})
    mods.deploy("fallout4", str(game))
    assert tree(game) == ["Data/MyMod.esp", "Data/meshes/a.nif"]


def test_cyberpunk(home):
    tmp, game = home
    z = make_zip(tmp / "c.zip", {"archive/pc/mod/a.archive": "a", "r6/scripts/x.reds": "r"})
    mods.install_archive("cyberpunk2077", "nx:4", z, {"name": "A", "source": "nexus"})
    z2 = make_zip(tmp / "c2.zip", {"loose.archive": "b"})
    mods.install_archive("cyberpunk2077", "nx:5", z2, {"name": "B", "source": "nexus"})
    mods.deploy("cyberpunk2077", str(game))
    assert tree(game) == ["archive/pc/mod/a.archive", "archive/pc/mod/loose.archive", "r6/scripts/x.reds"]


def test_replaced_game_files_come_back(home):
    tmp, game = home
    (game / "Mods").mkdir()
    (game / "Mods" / "keep.txt").write_text("mine")
    z = make_zip(tmp / "s.zip", {"M/manifest.json": "{}", "M/x.dll": "mod"})
    mods.install_archive("stardewvalley", "nx:6", z, {"name": "M", "source": "nexus"})
    (game / "Mods" / "M").mkdir()
    (game / "Mods" / "M" / "x.dll").write_text("original")
    mods.deploy("stardewvalley", str(game))
    assert (game / "Mods/M/x.dll").read_text() == "mod"
    mods.undeploy("stardewvalley")
    assert (game / "Mods/M/x.dll").read_text() == "original" and (game / "Mods/keep.txt").read_text() == "mine"
    assert not (game / "Mods/M/manifest.json").exists()


def test_profiles(home):
    tmp, game = home
    z = make_zip(tmp / "s.zip", {"M/manifest.json": "{}"})
    mods.install_archive("stardewvalley", "nx:7", z, {"name": "M", "source": "nexus"})
    mods.new_profile("stardewvalley", "Vanilla", copy=False)
    assert mods.enabled(mods.load("stardewvalley")) == []
    mods.use_profile("stardewvalley", "Default")
    assert mods.enabled(mods.load("stardewvalley")) == ["nx:7"]
    with pytest.raises(mods.ModError):
        mods.new_profile("stardewvalley", "Vanilla")


def test_zip_cannot_escape(home):
    tmp, game = home
    z = make_zip(tmp / "e.zip", {"../../evil": "x", "M/manifest.json": "{}"})
    mods.install_archive("stardewvalley", "nx:8", z, {"name": "M", "source": "nexus"})
    assert not (tmp.parent / "evil").exists()


def test_parse_nxm():
    d = mods.parse_nxm("nxm://stardewvalley/mods/3753/files/12345?key=abc&expires=1700000000&user_id=9")
    assert d == {"gid": "stardewvalley", "mod": 3753, "file": 12345, "key": "abc", "expires": "1700000000"}
    with pytest.raises(mods.ModError):
        mods.parse_nxm("nxm://witcher3/mods/1/files/2?key=a&expires=1")
    with pytest.raises(mods.ModError):
        mods.parse_nxm("https://example.com")

import json

from cornerplay.stores import prism


def _instance(root, folder, cfg, pack=None, mods=()):
    d = root / folder
    (d / "minecraft" / "mods").mkdir(parents=True)
    (d / "instance.cfg").write_text(cfg)
    if pack:
        (d / "mmc-pack.json").write_text(json.dumps(pack))
    for m in mods:
        (d / "minecraft" / "mods" / m).write_text("")
    return d


def test_instances_become_games(tmp_path, monkeypatch):
    data = tmp_path / "share" / "PrismLauncher"
    (data / "instances").mkdir(parents=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setattr(prism, "HOME", tmp_path)
    _instance(data / "instances", "FO", "[General]\nname=Fabulously Optimized\ntotalTimePlayed=7200\nlastLaunchTime=1700000000000\niconKey=grass\n",
              {"components": [{"uid": "net.minecraft", "version": "1.21.1"}, {"uid": "net.fabricmc.fabric-loader", "version": "0.16"}]},
              mods=("sodium.jar", "lithium.jar", "old.jar.disabled"))
    _instance(data / "instances", "Vanilla", "name=Vanilla 1.8\n")  # an old instance.cfg without [General]
    monkeypatch.setattr(prism, "prism_argv", lambda kind: ["prismlauncher"])
    store = prism.Prism()
    assert store.logged_in() and store.problem() == ""
    games = {g.id: g for g in store.fetch()}
    fo = games["FO"]
    assert fo.title == "Fabulously Optimized" and fo.installed
    assert fo.extra["loader"] == "Fabric" and fo.extra["mc_version"] == "1.21.1" and fo.extra["mods"] == 2
    assert fo.extra["steam_playtime"] == 7200 and fo.extra["steam_last_played"] == 1700000000
    assert fo.extra["art_title"] == "Minecraft"
    assert games["Vanilla"].title == "Vanilla 1.8"
    assert store.launch(fo).argv == ["prismlauncher", "--launch", "FO"]


def test_custom_instance_folder(tmp_path):
    data = tmp_path / "PrismLauncher"
    data.mkdir()
    (data / "prismlauncher.cfg").write_text("[General]\nInstanceDir=/mnt/games/mc\n")
    assert str(prism.instances_dir(data)) == "/mnt/games/mc"

from cornerplay import covers, updates
from cornerplay.config import GameOptions, read_json
from cornerplay.stores.base import Game


def test_norm_matches_editions_across_stores():
    assert covers.norm("The Witcher® 3: Wild Hunt – Game of the Year Edition") == covers.norm("The Witcher 3: Wild Hunt")
    assert covers.norm("Mount & Blade") == covers.norm("Mount and Blade")
    assert covers.norm("Portal 2") != covers.norm("Portal")


def test_version_compare():
    assert updates._ver("v0.10.0") > updates._ver("0.9.9")
    assert updates._ver("1.0") == (1, 0, 0)
    assert updates._ver("0.8.0-rc1") == (0, 8, 1)


def test_game_roundtrip():
    g = Game("gog", "123", "Gwent", installed=True, extra={"dlc": 2})
    assert Game.from_dict(dict(g.to_dict(), unknown_field=1)) == g
    assert g.key == "gog:123"


def test_game_options_drop_defaults(tmp_path, monkeypatch):
    opts = GameOptions()
    opts.path = tmp_path / "games.json"
    opts.data = {}
    opts.set("epic:a", "proton", "/x")
    opts.set("epic:a", "bogus", 1)  # unknown keys are ignored
    assert read_json(opts.path) == {"epic:a": {"proton": "/x"}}
    opts.set("epic:a", "proton", "default")
    assert read_json(opts.path) == {}


def test_steam_shortcut_keys_from_either_install():
    from cornerplay.steamshortcut import play_key
    assert play_key({"LaunchOptions": '--play "epic:Fortnite"'}) == "epic:Fortnite"
    assert play_key({"LaunchOptions": 'run io.github.raulgbh_ctrl.Cornerplay --play "gog:123"'}) == "gog:123"
    assert play_key({"LaunchOptions": "--tv"}) == ""
    assert play_key({"LaunchOptions": "run org.other.App --play x"}) == ""


def test_host_outside_flatpak():
    from cornerplay import host
    assert not host.IN_FLATPAK
    assert host.argv(["steam"]) == ["steam"]


def test_one_store_list_everywhere():
    """--play (Steam shortcuts) must know every store Steam shortcuts are made for."""
    from cornerplay.stores import all_stores
    from cornerplay.steamgames import eligible
    from cornerplay.stores.base import Game
    ids = [s.id for s in all_stores()]
    assert {"steam", "epic", "gog", "amazon", "battlenet", "itch", "retro", "custom"} == set(ids)
    for sid in ids:
        if sid != "steam":
            assert eligible(Game(sid, "1", "X", installed=True))

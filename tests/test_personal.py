from cornerplay import personal, playtime
from cornerplay.config import write_json
from cornerplay.stores.base import Game


def test_merge_newer_entry_wins():
    a = {"games": {"epic:a": {"rating": 3, "t": 10}, "gog:b": {"note": "old", "t": 1}},
         "collections": ["Backlog", "Co-op"], "deleted": {}}
    b = {"games": {"epic:a": {"rating": 5, "t": 5}, "gog:b": {"note": "new", "t": 2}, "steam:c": {"t": 1}},
         "collections": ["Co-op", "Retro"], "deleted": {"Backlog": 7}}
    m = personal._merge(a, b)
    assert m["games"]["epic:a"]["rating"] == 3
    assert m["games"]["gog:b"]["note"] == "new"
    assert "steam:c" in m["games"]
    assert m["collections"] == ["Co-op", "Retro"]
    assert m["deleted"] == {"Backlog": 7}


def test_merge_keeps_latest_deletion_time():
    a = {"games": {}, "collections": [], "deleted": {"X": 5}}
    b = {"games": {}, "collections": [], "deleted": {"X": 9}}
    assert personal._merge(a, b)["deleted"]["X"] == 9


def test_playtime_adds_up_across_pcs():
    own, _ = personal.playtime_files("playtime")
    write_json(own, {"epic:a": {"seconds": 100, "last": 50}})
    write_json(own.with_name("playtime-otherpc.json"), {"epic:a": {"seconds": 20, "last": 90}, "gog:b": {"seconds": 5}})
    data = playtime.load()
    assert data["epic:a"] == {"seconds": 120, "last": 90}
    assert data["gog:b"]["seconds"] == 5


def test_playtime_record_skips_failed_starts():
    playtime.record("custom:z", started=1000, ended=1005)
    assert "custom:z" not in playtime.load()
    playtime.record("custom:z", started=1000, ended=1600)
    assert playtime.load()["custom:z"]["seconds"] == 600


def test_playtime_of_takes_steams_record_too():
    g = Game("steam", "1", "X", extra={"steam_playtime": 500, "steam_last_played": 7})
    assert playtime.of(g, {"steam:1": {"seconds": 100, "last": 9}}) == (500, 9)

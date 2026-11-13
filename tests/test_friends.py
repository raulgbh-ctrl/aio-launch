from cornerplay import friends


def test_shared_orders_by_owners_then_hours():
    mine = {"1": "Solo", "2": "Co-op A", "3": "Co-op B", "4": "Nobody"}
    chosen = {"a": {"2": 10.0, "3": 1.0}, "b": {"3": 2.5}}
    rows = friends.shared(mine, chosen, lambda appid: appid != "1")
    assert [r["appid"] for r in rows] == ["3", "2"]
    assert rows[0]["all"] and rows[0]["hours"] == 3.5 and sorted(rows[0]["owners"]) == ["a", "b"]
    assert not rows[1]["all"] and rows[1]["owners"] == ["a"]


def test_shared_skips_single_player():
    rows = friends.shared({"1": "Solo"}, {"a": {"1": 5}}, lambda appid: False)
    assert rows == []

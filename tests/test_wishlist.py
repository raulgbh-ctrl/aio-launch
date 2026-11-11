from cornerplay import wishlist
from cornerplay.config import CACHE_DIR, settings, write_json


def test_country(monkeypatch):
    monkeypatch.setitem(settings.data, "store_country", "au")
    assert wishlist.country() == "AU"
    monkeypatch.setitem(settings.data, "store_country", "")
    write_json(CACHE_DIR / "gog_user.json", {"country": "RO"})
    assert wishlist.country() == "RO"


def test_sales_announced_once(monkeypatch):
    (CACHE_DIR / "wishlist.json").unlink(missing_ok=True)
    items = [{"store": "steam", "id": "1", "title": "A", "price": "$5", "was": "$10", "discount": 50},
             {"store": "steam", "id": "2", "title": "B", "price": "$9", "was": "", "discount": 0}]
    monkeypatch.setattr(wishlist, "_steam", lambda sid, cc: [dict(i) for i in items])
    first = wishlist.get("765", force=True)
    assert [i["title"] for i in first["items"]] == ["A", "B"]   # biggest discount first
    assert first["new_sales"] == []                             # the very first look announces nothing
    items[1]["discount"], items[1]["was"] = 25, "$12"
    second = wishlist.get("765", force=True)
    assert second["new_sales"] == ["B"]                         # a new sale: announced
    assert wishlist.get("765", force=True)["new_sales"] == []   # ...once

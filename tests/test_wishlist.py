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


def test_itad_best_price_and_alerts(monkeypatch):
    from cornerplay import itad
    (CACHE_DIR / "itad.json").unlink(missing_ok=True)
    calls = []
    deal = {"cut": 60, "price": 8.0, "low": 8.0}

    def post(path, key, body, params=None):
        calls.append((path, body))
        assert key == "k"
        if path == "/lookup/id/shop/61/v1":
            return {"app/1": "g-1"}
        if path == "/lookup/id/title/v1":
            return {"Gwent": "g-2"}
        assert path == "/games/overview/v2" and params == {"country": "AU"}
        shop = {"id": 35, "name": "GOG"}
        return {"prices": [{"id": "g-1", "current": {"shop": shop, "price": {"amount": deal["price"], "amountInt": int(deal["price"] * 100), "currency": "AUD"},
                                                    "regular": {"amount": 20.0, "amountInt": 2000, "currency": "AUD"}, "cut": deal["cut"],
                                                    "url": "https://itad.link/x"},
                            "lowest": {"shop": shop, "price": {"amount": deal["low"], "amountInt": 800, "currency": "AUD"}}}],
                "bundles": []}
    monkeypatch.setattr(itad, "_post", post)
    items = [{"store": "steam", "id": "1", "title": "Hades"}, {"store": "gog", "id": "9", "title": "Gwent"}]
    assert itad.enrich(items, "k", "AU", 50) == ([], "")   # the first look only records
    assert items[0]["best"] == {"shop": "GOG", "price": "A$8.00", "was": "A$20.00", "cut": 60,
                                "url": "https://itad.link/x", "low": True, "lowPrice": "A$8.00", "lowShop": "GOG"}
    assert "best" not in items[1]                          # no deal found for it
    deal.update(price=6.0, low=6.0, cut=70)                # a deeper cut, and a new lowest price
    news, _ = itad.enrich([dict(i) for i in items], "k", "AU", 50)
    assert [(n["title"], n["cut"], n["low"]) for n in news] == [("Hades", 70, True)]
    assert itad.enrich([dict(i) for i in items], "k", "AU", 50)[0] == []   # announced once
    assert sum(1 for c in calls if c[0].startswith("/lookup")) == 2       # ids are looked up once
    assert itad.money({"amount": 5, "currency": "RON"}) == "5.00 lei"

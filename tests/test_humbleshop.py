import json

from cornerplay import humbleshop


def page(*objects, extra=""):
    """A Next.js page whose payload holds these objects (as the real pages ship them: in chunks)."""
    text = extra + "".join(json.dumps(o, separators=(",", ":"), ensure_ascii=False) for o in objects)
    half = len(text) // 2
    return "".join(f'<script>self.__next_f.push([1,{json.dumps(part)}])</script>' for part in (text[:half], text[half:]))


def price(cents, code="EUR"):
    return {"currentPrice": {"type": "centPrecision", "centAmount": cents, "currencyCode": code, "fractionDigits": 2}}


def test_money():
    assert humbleshop.money(price(6498.999999999999)["currentPrice"]) == "€64.99"
    assert humbleshop.money(price(895, "USD")["currentPrice"]) == "$8.95"
    assert humbleshop.money(price(100, "XYZ")["currentPrice"]) == "1.00 XYZ"
    assert humbleshop.money(None) == ""


def test_choice():
    html = page({"subscriptionProducts": [
        {"id": "a_choice", "productType": "humble-choice", "title": "Space Haven", "thumbnail": "https://hb-prd.imgix.net/x.jpg",
         "displayPrice": price(2499), "platforms": ["linux", "windows"], "deliveryMethods": ["steam"]},
        {"id": "b_choice", "productType": "humble-choice", "title": "IGN Plus", "displayPrice": price(499),
         "platforms": "$undefined", "deliveryMethods": ["external_key"]},
        {"id": "a_choice", "productType": "humble-choice", "title": "Space Haven"}]},  # shown twice on the page
        extra='{"label":"Get November’s Games","price":"€12.99"}')
    c = humbleshop.parse_choice(html)
    assert c["month"] == "November" and c["price"] == "€12.99"
    assert [g["title"] for g in c["games"]] == ["Space Haven", "IGN Plus"]
    assert c["games"][0]["worth"] == "€24.99" and c["games"][0]["store"] == "steam"
    assert c["games"][0]["image"].endswith("&w=600") and c["games"][1]["platforms"] == []


def test_bundles():
    def hit(i, cat, end, title):
        return {"relationTo": "algolia-hit", "value": {
            "id": i, "productType": "humble-bundle", "category": cat, "title": title, "url": f"/games/{i}",
            "thumbnail": "", "displayPrice": price(712), "endDate": end, "itemsCount": 8,
            "includedItemTitles": ["One", "Two", "$undefined"]}}
    html = page(hit("late", "games", "2026-12-03T05:00:00.000Z", "Late"), hit("soon", "games", "2026-11-14T05:00:00.000Z", "Soon"),
                hit("book", "books", "2026-11-15T05:00:00.000Z", "Books"), hit("soon", "games", "2026-11-14T05:00:00.000Z", "Soon"))
    b = humbleshop.parse_bundles(html)
    assert [x["title"] for x in b] == ["Soon", "Late"]  # games only, once each, ending soonest first
    assert b[0]["url"] == "https://www.humblebundle.com/games/soon" and b[0]["price"] == "€7.12"
    assert b[0]["items"] == 8 and b[0]["includes"] == ["One", "Two"] and b[0]["ends"] > 0


def test_bundle_tiers_follow_references():
    def item(title, usd):
        return {"title": title, "thumbnailImageUrl": "", "msrp": {"amount": usd, "currencyCode": "USD"},
                "deliveryMethods": ["steam"], "platforms": ["windows"]}
    ref = "$e:0:props:children:props:bundlePage:tiers:%d:bundleItems:%d"
    tiers = [{"id": "1", "price": {"amount": 1.5, "currencyCode": "EUR"}, "bundleItems": [item("A", 10)]},
             {"id": "2", "price": {"amount": 8, "currencyCode": "EUR"}, "bundleItems": [item("B", 20), item("C", 5), ref % (0, 0)]},
             {"id": "3", "price": {"amount": 12, "currencyCode": "EUR"}, "bundleItems": [item("D", 30), ref % (1, 0), ref % (1, 1), ref % (1, 2)]}]
    b = humbleshop.parse_bundle(page({"bundlePage": {"tiers": tiers}}))
    assert [t["price"] for t in b["tiers"]] == ["€1.50", "€8.00", "€12.00"]
    assert [[i["title"] for i in t["items"]] for t in b["tiers"]] == [["A"], ["B", "C", "A"], ["D", "B", "C", "A"]]
    assert [[i["new"] for i in t["items"]] for t in b["tiers"]] == [[True], [True, True, False], [True, False, False, False]]
    assert b["tiers"][0]["items"][0]["msrp"] == "$10.00"


def test_itad_prices(monkeypatch, tmp_path):
    from cornerplay import itad
    monkeypatch.setattr(itad, "FILE", tmp_path / "itad.json")
    calls = []

    def post(path, key, body, params=None):
        calls.append(path)
        if path == "/lookup/id/title/v1":
            return {"Game A": "id-a", "Game B": "id-b", "Unknown": None}
        return {"prices": [{"id": "id-a", "current": {"shop": {"name": "GOG"}, "price": {"amount": 4.99, "currency": "EUR"},
                                                       "regular": {"amount": 9.99, "currency": "EUR"}, "cut": 50, "url": "u"},
                            "lowest": {"price": {"amount": 2.99, "currency": "EUR"}}},
                           {"id": "id-b", "current": None}]}
    monkeypatch.setattr(itad, "_post", post)
    got, err = itad.prices(["Game A", "Game B", "Unknown"], "k", "RO")
    assert err == "" and list(got) == ["Game A"]
    assert got["Game A"]["amount"] == 4.99 and got["Game A"]["shop"] == "GOG" and got["Game A"]["price"] == "€4.99"
    itad.prices(["Game A"], "k", "RO")  # the id is cached now: no second lookup
    assert calls.count("/lookup/id/title/v1") == 1

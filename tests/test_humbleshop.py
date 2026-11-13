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

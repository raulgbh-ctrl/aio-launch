from cornerplay import steambundles as sb


def bundle(items, bd=10, price="11,61€"):
    return {"id": 1, "name": "B", "url": "u", "image": "", "cents": 0, "price": price, "discount": 0,
            "bundleDiscount": bd, "items": items}


def item(appid, name, kind, cents):
    return {"appid": appid, "name": name, "type": kind, "cents": cents}


def test_fmt():
    assert sb.fmt(1161, "11,61€") == "11,61€"
    assert sb.fmt(870, "$8.70") == "$8.70"
    assert sb.fmt(5, "1,00 zł") == "0,05 zł"


def test_for_you_and_extras():
    b = bundle([item(1, "Brotato", sb.GAME, 249), item(2, "Brotato: Abyssal Terrors", sb.DLC, 319),
                item(3, "Brotato: Primal Dread", sb.DLC, 399), item(4, "Brotato Soundtrack", sb.SOUNDTRACK, 399)], bd=15)
    full = sb.for_you(b, set())
    assert full["cents"] == round(1366 * 0.85) and full["price"] == "11,61€"
    mine = sb.for_you(b, {1})
    assert mine["cents"] == round(1117 * 0.85) and mine["ownedCount"] == 1 and mine["newCount"] == 3 and mine["saving"] == 15
    assert sb.is_extras_for(b, {1}, ["Brotato"])
    other = bundle([item(1, "Brotato", sb.GAME, 249), item(9, "Other Game", sb.GAME, 500)])
    assert not sb.is_extras_for(other, {1}, ["Brotato"])      # adds another game: not "extras"
    assert not sb.is_extras_for(b, set(), ["Brotato"])        # you don't own the game
    assert sb.for_you(b, {1, 2, 3, 4})["price"] == ""         # nothing left to buy

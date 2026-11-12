"""The best price for your wishlist across every store, from IsThereAnyDeal.

With a free IsThereAnyDeal API key (Settings > Library) each wishlist game (Steam and GOG
wishlists, wishlist.py) gets the cheapest current deal on any store ITAD follows (Steam, GOG,
Epic, Humble, Fanatical, GamesPlanet, ...) and its lowest price ever. A deal at least as deep
as your alert setting, or a new lowest price, is announced once.

API (https://docs.isthereanydeal.com): POST /lookup/id/shop/{shop}/v1 maps Steam app ids to
ITAD game ids (Steam is shop 61), POST /lookup/id/title/v1 maps titles (GOG games), and
POST /games/overview/v2 gives the current best deal and the historical low for up to 200 games.
ITAD game ids never change: they are kept in ~/.cache/cornerplay/itad.json.
"""
from .config import CACHE_DIR, read_json, write_json
from .net import requests

API = "https://api.isthereanydeal.com"
FILE = CACHE_DIR / "itad.json"
STEAM_SHOP = 61
SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "AUD": "A$", "CAD": "C$", "NZD": "NZ$", "JPY": "¥",
           "RON": " lei", "PLN": " zł", "BRL": "R$", "CHF": "CHF ", "SEK": " kr", "NOK": " kr", "DKK": " kr"}
_AFTER = {"RON", "PLN", "SEK", "NOK", "DKK"}


def money(p):
    """{"amount": 9.99, "currency": "EUR"} -> "€9.99" (or "9.99 lei" where the sign comes after)."""
    if not isinstance(p, dict) or p.get("amount") is None:
        return ""
    cur = str(p.get("currency") or "")
    amount = f"{float(p['amount']):.2f}"
    sym = SYMBOLS.get(cur)
    if not sym:
        return f"{amount} {cur}".strip()
    return amount + sym if cur in _AFTER else sym + amount


def _post(path, key, body, params=None):
    # The key goes in a header, not the URL: URLs end up in logs and error messages.
    r = requests.post(API + path, params=params or {}, json=body, headers={"ITAD-API-Key": key}, timeout=30)
    r.raise_for_status()
    return r.json()


def _ids(items, key, cache):
    """ITAD game id per wishlist item ("store:id" -> uuid or ""), asking only for new ones."""
    known = cache.setdefault("ids", {})
    steam = [i for i in items if i["store"] == "steam" and f"steam:{i['id']}" not in known]
    if steam:
        for at in range(0, len(steam), 200):
            chunk = steam[at:at + 200]
            got = _post(f"/lookup/id/shop/{STEAM_SHOP}/v1", key, [f"app/{i['id']}" for i in chunk]) or {}
            for i in chunk:
                known[f"steam:{i['id']}"] = got.get(f"app/{i['id']}") or ""
    others = [i for i in items if i["store"] != "steam" and f"{i['store']}:{i['id']}" not in known]
    if others:
        for at in range(0, len(others), 200):
            chunk = others[at:at + 200]
            got = _post("/lookup/id/title/v1", key, [i["title"] for i in chunk]) or {}
            for i in chunk:
                known[f"{i['store']}:{i['id']}"] = got.get(i["title"]) or ""
    return {f"{i['store']}:{i['id']}": known.get(f"{i['store']}:{i['id']}", "") for i in items}


def enrich(items, key, country, alert_cut=50):
    """Add "best" (the cheapest deal on any store) to each wishlist item in place, and return
    (titles to announce, error text). best = {"shop", "price", "was", "cut", "url", "low",
    "lowPrice", "lowShop"}; "low" is true when the deal matches the lowest price ever."""
    if not key or not items:
        return [], ""
    cache = read_json(FILE) or {}
    try:
        ids = _ids(items, key, cache)
        wanted = sorted({v for v in ids.values() if v})
        overview = {}
        for at in range(0, len(wanted), 200):
            got = _post("/games/overview/v2", key, wanted[at:at + 200], {"country": country}) or {}
            for row in got.get("prices") or []:
                if isinstance(row, dict) and row.get("id"):
                    overview[row["id"]] = row
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", 0)
        write_json(FILE, cache)
        return [], ("IsThereAnyDeal: the API key was not accepted" if code in (401, 403)
                    else f"IsThereAnyDeal: HTTP {code}")
    except (requests.RequestException, ValueError) as e:
        write_json(FILE, cache)
        return [], f"IsThereAnyDeal: {type(e).__name__}"
    first = "announced" not in cache  # the very first look only records (no burst of old deals)
    announced = set(cache.get("announced") or [])
    lows = cache.setdefault("lows", {})  # gid -> lowest amount seen in an alert, so a lower one is news
    news = []
    for item in items:
        gid = ids.get(f"{item['store']}:{item['id']}")
        row = overview.get(gid) if gid else None
        cur = (row or {}).get("current") or {}
        if not cur or not isinstance(cur.get("price"), dict):
            continue
        low = (row or {}).get("lowest") or {}
        amount = float(cur["price"].get("amount") or 0)
        low_amount = float(((low.get("price") or {}).get("amount")) or 0) if low else 0
        cut = int(cur.get("cut") or 0)
        is_low = bool(low) and cut > 0 and amount <= low_amount + 0.005
        item["best"] = {"shop": (cur.get("shop") or {}).get("name", ""), "price": money(cur["price"]),
                        "was": money(cur.get("regular")) if cut else "", "cut": cut, "url": cur.get("url", ""),
                        "low": is_low, "lowPrice": money(low.get("price")) if low else "",
                        "lowShop": (low.get("shop") or {}).get("name", "") if low else ""}
        if cut <= 0:
            continue
        tag = f"{gid}:{item['best']['shop']}:{cur['price'].get('amountInt')}"
        new_low = is_low and amount < float(lows.get(gid, 1e12)) - 0.005
        if tag not in announced and (cut >= alert_cut or new_low):
            news.append({"title": item["title"], "price": item["best"]["price"], "cut": cut,
                         "shop": item["best"]["shop"], "low": is_low, "url": item["best"]["url"]})
            announced.add(tag)
            if is_low:
                lows[gid] = amount
    cache["announced"] = sorted(announced)[-3000:]
    write_json(FILE, cache)
    return ([] if first else news), ""

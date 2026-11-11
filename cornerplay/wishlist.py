"""Your wishlists, and which games on them are on sale.

Steam: the public wishlist API (no key; your profile's game details must be public) and
Steam's store service for names, prices, discounts and art, in your country's currency.
GOG: your wishlist through your GOG sign-in, prices from GOG's price service.
Checked at most every 6 hours; a sale seen for the first time is announced once
(Cornerplay shows a toast), kept in ~/.cache/cornerplay/wishlist.json.
"""
import json
import locale
import time

from .config import CACHE_DIR, read_json, write_json
from .net import requests

FILE = CACHE_DIR / "wishlist.json"
TTL = 6 * 3600
STEAM_CDN = "https://shared.akamai.steamstatic.com/store_item_assets/"


def country():
    """Two-letter country for store prices: Settings (store_country), else your GOG account's
    country, else the system locale (en_AU -> AU), else US."""
    from .config import settings
    for cc in (str(settings.get("store_country") or ""), str((read_json(CACHE_DIR / "gog_user.json") or {}).get("country") or "")):
        cc = cc.strip().upper()
        if len(cc) == 2 and cc.isalpha():
            return cc
    for value in (locale.getlocale()[0], locale.setlocale(locale.LC_MESSAGES, None) if hasattr(locale, "LC_MESSAGES") else ""):
        if value and "_" in value:
            cc = value.split("_", 1)[1][:2].upper()
            if cc.isalpha() and len(cc) == 2:
                return cc
    return "US"


def _steam(steamid, cc):
    r = requests.get("https://api.steampowered.com/IWishlistService/GetWishlist/v1/",
                     params={"steamid": steamid}, timeout=20)
    r.raise_for_status()
    ids = [int(i["appid"]) for i in (r.json().get("response") or {}).get("items") or [] if i.get("appid")]
    out = []
    for at in range(0, len(ids), 100):
        req = {"ids": [{"appid": a} for a in ids[at:at + 100]], "context": {"language": "english", "country_code": cc},
               "data_request": {"include_assets": True}}
        r = requests.get("https://api.steampowered.com/IStoreBrowseService/GetItems/v1/",
                         params={"input_json": json.dumps(req)}, timeout=30)
        r.raise_for_status()
        for item in (r.json().get("response") or {}).get("store_items") or []:
            buy = item.get("best_purchase_option") or {}
            assets = item.get("assets") or {}
            fmt = assets.get("asset_url_format", "")

            def art(name, fmt=fmt):
                return STEAM_CDN + fmt.replace("${FILENAME}", name) if fmt and name else ""
            out.append({"store": "steam", "id": str(item.get("appid", "")), "title": item.get("name", ""),
                        "price": buy.get("formatted_final_price", ""),
                        "was": buy.get("formatted_original_price", ""),
                        "discount": int(buy.get("discount_pct") or 0),
                        "tall": art(assets.get("library_capsule")), "wide": art(assets.get("header")),
                        "url": f"https://store.steampowered.com/app/{item.get('appid')}/"})
    return out


def _gog(token, cc):
    r = requests.get("https://embed.gog.com/user/wishlist.json", headers={"Authorization": f"Bearer {token}"}, timeout=20)
    r.raise_for_status()
    ids = [i for i, on in ((r.json() or {}).get("wishlist") or {}).items() if on]
    out = []
    for at in range(0, len(ids), 50):
        chunk = ids[at:at + 50]
        info = requests.get("https://api.gog.com/products", params={"ids": ",".join(chunk), "expand": ""}, timeout=30).json()
        for p in info if isinstance(info, list) else []:
            gid = str(p.get("id", ""))
            price = {}
            try:
                pr = requests.get(f"https://api.gog.com/products/{gid}/prices", params={"countryCode": cc}, timeout=20).json()
                price = ((pr.get("_embedded") or {}).get("prices") or [{}])[0]
            except (requests.RequestException, ValueError):
                pass

            def money(v):  # "2499 AUD" -> "AUD 24.99"
                parts = str(v or "").split()
                return f"{parts[1]} {int(parts[0]) / 100:.2f}" if len(parts) == 2 and parts[0].isdigit() else ""
            final, base = money(price.get("finalPrice")), money(price.get("basePrice"))
            try:
                f, b = int(str(price.get("finalPrice")).split()[0]), int(str(price.get("basePrice")).split()[0])
                discount = round(100 - f * 100 / b) if b and f < b else 0
            except (ValueError, IndexError, TypeError):
                discount = 0
            images = p.get("images") or {}
            link = ((p.get("links") or {}).get("product_card")) or f"https://www.gog.com/game/{p.get('slug', '')}"
            out.append({"store": "gog", "id": gid, "title": p.get("title", ""), "price": final,
                        "was": base if discount else "", "discount": discount,
                        "tall": "", "wide": ("https:" + images["logo2x"]) if str(images.get("logo2x", "")).startswith("//") else "",
                        "url": link})
    return out


def get(steamid="", gog_token_fn=None, force=False):
    """{"items": [...], "new_sales": [...titles on sale since the last check...], "error": ""}."""
    saved = read_json(FILE) or {}
    if not force and time.time() - saved.get("t", 0) < TTL and "items" in saved:
        return {"items": saved["items"], "new_sales": [], "error": saved.get("error", "")}
    cc = country()
    items, errors = [], []
    if steamid:
        try:
            items += _steam(steamid, cc)
        except (requests.RequestException, ValueError, KeyError) as e:
            errors.append(f"Steam wishlist: {type(e).__name__}")
    if gog_token_fn:
        try:
            items += _gog(gog_token_fn(), cc)
        except Exception as e:
            errors.append(f"GOG wishlist: {type(e).__name__}")
    items = [i for i in items if i["title"]]
    items.sort(key=lambda i: (-i["discount"], i["title"].lower()))
    seen = set(saved.get("announced") or [])
    on_sale = {f"{i['store']}:{i['id']}:{i['discount']}" for i in items if i["discount"]}
    new_sales = [i["title"] for i in items if i["discount"] and f"{i['store']}:{i['id']}:{i['discount']}" not in seen]
    if errors and not items:
        items = saved.get("items") or []  # keep showing the last good list
    write_json(FILE, {"t": time.time(), "items": items, "announced": sorted(on_sale | seen)[-2000:],
                      "error": "; ".join(errors)})
    return {"items": items, "new_sales": new_sales if saved else [], "error": "; ".join(errors)}

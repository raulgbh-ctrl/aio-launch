"""Steam bundles: the ones with your games or your wishlist games in them, priced for you.

From Steam's public store API (IStoreBrowseService/GetItems, no key): a game's purchase options
include every bundle it is in; a bundle's included_items give its games, DLC and soundtracks with
today's prices. A bundle costs the sum of its items' current prices less its bundle discount, and
Steam leaves out what you already own ("complete the set"): the price for you is the same sum
over what you don't own. Cornerplay knows which games you own, not which DLC, so DLC counts as
not owned (the real price can only be lower). Prices are in your store country's currency.
Cached for a day in ~/.cache/cornerplay/steam_bundles.json.
"""
import json
import re
import time

from .config import CACHE_DIR, read_json, write_json
from .net import requests

API = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/"
FILE = CACHE_DIR / "steam_bundles.json"
TTL = 86400
BATCH = 50
ASSETS = "https://shared.akamai.steamstatic.com/store_item_assets/"
GAME, DLC, SOUNDTRACK = 0, 4, 11


def _items(ids, data_request, country):
    out = []
    for at in range(0, len(ids), BATCH):
        body = {"ids": ids[at:at + BATCH], "context": {"language": "english", "country_code": country},
                "data_request": data_request}
        r = requests.get(API, params={"input_json": json.dumps(body)}, timeout=30)
        r.raise_for_status()
        out += (r.json().get("response") or {}).get("store_items") or []
    return out


def _cache():
    c = read_json(FILE) or {}
    now = time.time()
    for part in ("apps", "bundles"):
        c[part] = {k: v for k, v in (c.get(part) or {}).items() if now - v.get("t", 0) < TTL}
    return c


def bundle_ids(appids, country, names=False):
    """{appid: [bundle id, ...]} (every bundle each game is in); names=True: [(id, name), ...]."""
    c = _cache()
    key = lambda a: f"{country}:{a}"  # noqa: E731
    todo = [a for a in dict.fromkeys(str(a) for a in appids) if key(a) not in c["apps"]]
    if todo:
        got = _items([{"appid": int(a)} for a in todo], {"include_all_purchase_options": True}, country)
        found = {str(it.get("appid") or it.get("id")): it for it in got}
        for a in todo:
            opts = (found.get(a) or {}).get("purchase_options") or []
            c["apps"][key(a)] = {"t": time.time(), "b": [[int(o["bundleid"]), o.get("purchase_option_name") or ""]
                                                         for o in opts if o.get("bundleid")]}
        write_json(FILE, c)
    out = {}
    for a in appids:
        rows = [r if isinstance(r, list) else [r, ""] for r in (c["apps"].get(key(str(a))) or {}).get("b") or []]
        out[str(a)] = [tuple(r) for r in rows] if names else [r[0] for r in rows]
    return out


def _price_format(sample):
    """How the store writes a price ("11,61€", "$8.70", "8,70 zł"): (before, after, decimal sep)."""
    m = re.match(r"^(\D*?)([\d.,\s ]+?)(\D*)$", sample or "")
    if not m:
        return "", "", "."
    number = m.group(2).strip()
    sep = number[-3] if len(number) > 3 and number[-3] in ",." else "."
    return m.group(1), m.group(3), sep


def fmt(cents, sample):
    before, after, sep = _price_format(sample)
    text = f"{cents / 100:.2f}".replace(".", sep)
    return f"{before}{text}{after}"


def bundles(ids, country):
    """{bundle id: {id, name, url, image, cents, price, discount, bundleDiscount, items: [{appid, name,
    type, cents}]}} for these bundles (those Steam still sells)."""
    c = _cache()
    key = lambda b: f"{country}:{b}"  # noqa: E731
    todo = [b for b in dict.fromkeys(int(b) for b in ids) if key(b) not in c["bundles"]]
    if todo:
        got = _items([{"bundleid": b} for b in todo], {"include_included_items": True, "include_assets": True}, country)
        for it in got:
            bid = int(it.get("id") or 0)
            best = it.get("best_purchase_option") or {}
            if not bid or not best.get("final_price_in_cents"):
                continue
            assets = it.get("assets") or {}
            head = assets.get("header") or ""
            fmt_url = assets.get("asset_url_format") or ""
            image = (ASSETS + fmt_url.replace("${FILENAME}", head)) if head and fmt_url else ""
            apps = []
            for a in (it.get("included_items") or {}).get("included_apps") or []:
                ap = a.get("best_purchase_option") or {}
                apps.append({"appid": int(a.get("appid") or a.get("id") or 0), "name": a.get("name") or "",
                             "type": int(a.get("type") or 0), "cents": int(ap.get("final_price_in_cents") or 0)})
            c["bundles"][key(bid)] = {"t": time.time(), "d": {
                "id": bid, "name": it.get("name") or "", "url": f"https://store.steampowered.com/{it.get('store_url_path') or f'bundle/{bid}'}",
                "image": image, "cents": int(best["final_price_in_cents"]), "price": best.get("formatted_final_price") or "",
                "discount": int(best.get("discount_pct") or 0), "bundleDiscount": int(best.get("bundle_discount_pct") or 0),
                "items": apps}}
        for b in todo:  # not sold any more: remember that too, for a day
            c["bundles"].setdefault(key(b), {"t": time.time(), "d": None})
        write_json(FILE, c)
    return {b: (c["bundles"].get(key(b)) or {}).get("d") for b in (int(x) for x in ids) if (c["bundles"].get(key(b)) or {}).get("d")}


def for_you(b, owned):
    """The bundle priced for someone owning these app ids: {cents, price, ownedCount, newCount,
    alone (what the new items cost one by one), saving %}."""
    new = [i for i in b["items"] if i["appid"] not in owned]
    alone = sum(i["cents"] for i in new)
    cents = round(alone * (100 - b["bundleDiscount"]) / 100)
    return {"cents": cents, "price": fmt(cents, b["price"]) if new else "", "alone": fmt(alone, b["price"]) if new else "",
            "ownedCount": len(b["items"]) - len(new), "newCount": len(new),
            "saving": round(100 * (1 - cents / alone)) if alone else 0}


def is_extras_for(b, owned, owned_titles):
    """A bundle that only adds DLC / soundtracks to games you own (and has something to add)."""
    titles = [t.lower() for t in owned_titles if len(t) >= 3]
    adds = False
    for i in b["items"]:
        if i["appid"] in owned:
            continue
        if i["type"] not in (DLC, SOUNDTRACK) or not any(i["name"].lower().startswith(t) for t in titles):
            return False
        adds = True
    return adds and any(i["appid"] in owned and i["type"] == GAME for i in b["items"])

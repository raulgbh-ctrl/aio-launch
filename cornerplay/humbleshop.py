"""Humble Bundle's shop window: this month's Humble Choice games and the game bundles on sale, with prices.

Read from Humble's public pages (/membership and /bundles); since the November 2026 rebuild they
carry their data in the Next.js page payload (self.__next_f.push chunks) rather than an API.
Prices are in the currency Humble picks for your country. Cached for 3 hours; offline, the last
list is used. Nothing here needs a Humble account.
"""
import json
import re
import time
from datetime import datetime

from .config import CACHE_DIR, read_json, write_json
from .net import requests

SITE = "https://www.humblebundle.com"
CHOICE_URL = SITE + "/membership"
BUNDLES_URL = SITE + "/bundles"
FILE = CACHE_DIR / "humble_shop.json"
TTL = 3 * 3600
SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "CAD": "CA$", "AUD": "A$", "JPY": "¥", "BRL": "R$", "PLN": "zł "}
_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')


def payload(html):
    """The page's Next.js data as one string."""
    out = []
    for c in _CHUNK.findall(html):
        try:
            out.append(json.loads('"%s"' % c))
        except ValueError:
            continue
    return "".join(out)


def _objects(text, marker):
    """Every JSON object in text that starts with marker."""
    dec = json.JSONDecoder()
    for m in re.finditer(re.escape(marker), text):
        try:
            yield dec.raw_decode(text, m.start())[0]
        except ValueError:
            continue


def money(price):
    """{"centAmount": 895, "currencyCode": "EUR", "fractionDigits": 2} -> "€8.95" ("" when unknown)."""
    if not isinstance(price, dict) or price.get("centAmount") is None:
        return ""
    digits = int(price.get("fractionDigits") or 0)
    amount = round(float(price["centAmount"])) / 10 ** digits
    code = price.get("currencyCode") or ""
    text = f"{amount:.{digits}f}"
    sym = SYMBOLS.get(code)
    return f"{sym}{text}" if sym else f"{text} {code}".strip()


def _strings(value):
    """A list of strings from the payload ("$undefined" is how it writes a missing one)."""
    return [v for v in value if isinstance(v, str) and not v.startswith("$")] if isinstance(value, list) else []


def _image(url, width):
    """Humble's images come from imgix: ask for a small one."""
    if "imgix.net" in (url or "") and "?" not in url:
        return f"{url}?auto=compress,format&w={width}"
    return url or ""


def _stamp(iso):
    try:
        return int(datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return 0


def parse_choice(html):
    """{"month", "price", "url", "games": [{title, image, worth, platforms, store}]}."""
    text = payload(html)
    games, seen = [], set()
    for block in _objects(text, '{"id":'):
        if not isinstance(block, dict) or block.get("productType") != "humble-choice" or block.get("id") in seen:
            continue
        seen.add(block["id"])
        price = (block.get("displayPrice") or {}).get("currentPrice")
        games.append({"title": (block.get("title") or "").strip(), "image": _image(block.get("thumbnail"), 600),
                      "worth": money(price), "platforms": _strings(block.get("platforms")),
                      "store": (_strings(block.get("deliveryMethods")) or [""])[0]})
    month = re.search(r"Get (\w+)[’']s Games", text)
    price = re.search(r'"price":"([^"$][^"]{0,15})"', text)  # the Join button's "€12.99"
    return {"month": month.group(1) if month else "", "price": price.group(1) if price else "",
            "url": CHOICE_URL, "games": [g for g in games if g["title"]]}


def parse_bundles(html, category="games"):
    """[{title, url, image, price, ends, items, includes}] for one category, ending soonest first."""
    out, seen = [], set()
    for hit in _objects(payload(html), '{"relationTo":"algolia-hit","value":'):
        b = hit.get("value") if isinstance(hit, dict) else None
        if not isinstance(b, dict) or b.get("id") in seen or b.get("productType") != "humble-bundle":
            continue
        if category and b.get("category") != category:
            continue
        seen.add(b.get("id"))
        price = (b.get("displayPrice") or {}).get("currentPrice")
        out.append({"title": (b.get("title") or "").strip(), "url": SITE + (b.get("url") or "/bundles"),
                    "image": _image(b.get("thumbnail"), 600), "price": money(price),
                    "ends": _stamp(b.get("endDate")), "items": int(b.get("itemsCount") or 0),
                    "includes": _strings(b.get("includedItemTitles"))[:6]})
    out.sort(key=lambda b: (b["ends"] or 1 << 40))
    return out


BUNDLES_FILE = CACHE_DIR / "humble_bundles.json"
_TIER_REF = re.compile(r":tiers:(\d+):bundleItems:(\d+)$")


def _amount(amount, code):
    """8.95, "EUR" -> "€8.95"."""
    return money({"centAmount": round(float(amount) * 100), "currencyCode": code, "fractionDigits": 2})


def parse_bundle(html):
    """{"tiers": [{price, amount, currency, items: [{title, image, msrp, store, platforms, new}]}]}:
    each tier with every game it gives (tiers add up: a higher one includes the lower ones'),
    "new" marking the games that tier adds. The page names a game again by reference
    ("$e:...:tiers:0:bundleItems:0"); those are followed."""
    text = payload(html)
    at = text.find('"tiers":[')
    if at < 0:
        return {"tiers": []}
    try:
        raw = json.JSONDecoder().raw_decode(text, at + len('"tiers":'))[0]
    except ValueError:
        return {"tiers": []}
    resolved, tiers = [], []
    for t in raw if isinstance(raw, list) else []:
        if not isinstance(t, dict):
            continue
        row = []
        for b in t.get("bundleItems") or []:
            if isinstance(b, str):
                m = _TIER_REF.search(b)
                b = None
                if m and int(m.group(1)) < len(resolved) and int(m.group(2)) < len(resolved[int(m.group(1))]):
                    b = resolved[int(m.group(1))][int(m.group(2))]
            row.append(b if isinstance(b, dict) else None)
        resolved.append(row)
        price = t.get("price") or {}
        if price.get("amount") is None:
            continue
        items, here = [], set()
        for b in row:
            if not b or not b.get("title") or b["title"] in here:
                continue
            here.add(b["title"])
            msrp = b.get("msrp") or {}
            items.append({"title": b["title"].strip(), "image": _image(b.get("thumbnailImageUrl"), 300),
                          "msrp": _amount(msrp["amount"], msrp.get("currencyCode") or "USD") if msrp.get("amount") else "",
                          "store": (_strings(b.get("deliveryMethods")) or [""])[0],
                          "platforms": _strings(b.get("platforms"))})
        tiers.append({"price": _amount(price["amount"], price.get("currencyCode") or ""), "amount": float(price["amount"]),
                      "currency": price.get("currencyCode") or "", "items": items})
    # The page doesn't list tiers cheapest first: sort them, then mark what each one adds.
    tiers.sort(key=lambda t: (t["amount"], len(t["items"])))
    seen = set()
    for t in tiers:
        for i in t["items"]:
            i["new"] = i["title"] not in seen
        seen |= {i["title"] for i in t["items"]}
        t["items"].sort(key=lambda i: not i["new"])
    return {"tiers": tiers}


def bundle(url, force=False):
    """A bundle's tiers (parse_bundle), cached for 3 hours; {} when it can't be read."""
    cache = read_json(BUNDLES_FILE) or {}
    entry = cache.get(url) or {}
    if not force and time.time() - entry.get("t", 0) < TTL and entry.get("b"):
        return entry["b"]
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        b = parse_bundle(r.text)
    except Exception:
        return entry.get("b") or {}
    if b["tiers"]:
        cache = {k: v for k, v in cache.items() if time.time() - v.get("t", 0) < 7 * 86400}
        cache[url] = {"t": time.time(), "b": b}
        write_json(BUNDLES_FILE, cache)
    return b


def fetch():
    """Both lists, read now. Raises on network errors."""
    choice = requests.get(CHOICE_URL, timeout=30)
    choice.raise_for_status()
    bundles = requests.get(BUNDLES_URL, timeout=30)
    bundles.raise_for_status()
    return {"choice": parse_choice(choice.text), "bundles": parse_bundles(bundles.text)}


def get(force=False):
    """The cached shop while it is fresh, else a new one (the cache when offline)."""
    cached = read_json(FILE) or {}
    if not force and time.time() - cached.get("t", 0) < TTL and cached.get("shop"):
        return cached["shop"]
    try:
        shop = fetch()
    except Exception:
        return cached.get("shop") or {}
    if shop["choice"]["games"] or shop["bundles"]:
        write_json(FILE, {"t": time.time(), "shop": shop})
    return shop

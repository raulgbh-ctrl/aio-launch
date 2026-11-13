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

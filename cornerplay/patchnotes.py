"""Patch notes and news for a game: the developer's own announcements on Steam.

From Steam's public news feed (ISteamNews/GetNewsForApp, the "steam_community_announcements"
feed only, so no press articles). Works for any game with a known Steam app id, also when it
was bought on another store. Steam's BBCode becomes plain text with bullets. Cached for 6 hours
in ~/.cache/cornerplay/patch_notes.json; offline, the last list is used.
"""
import html
import re
import threading
import time

from .config import CACHE_DIR, read_json, write_json
from .net import requests

FEED = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
FILE = CACHE_DIR / "patch_notes.json"
TTL = 6 * 3600
COUNT = 6
MAX_TEXT = 1800
PATCH_WORDS = re.compile(r"\b(patch|hotfix|update|fix(es|ed)?|changelog|release notes|v?\d+\.\d+(\.\d+)*)\b", re.I)
_lock = threading.Lock()


def plain(text):
    """Steam's BBCode (or the odd bit of HTML) as readable plain text."""
    t = text or ""
    t = re.sub(r"\{STEAM_CLAN_IMAGE\}\S*|\[img[^\]]*\].*?\[/img\]|\[previewyoutube[^\]]*\].*?\[/previewyoutube\]", "", t, flags=re.I | re.S)
    t = re.sub(r"\[(h[1-6])\](.*?)\[/\1\]", lambda m: "\n" + m.group(2).strip() + "\n", t, flags=re.I | re.S)
    t = re.sub(r"\[\*\]\s*", "\n• ", t)
    t = re.sub(r"\[p\b[^\]]*\]|<p\b[^>]*>", "", t, flags=re.I)  # a paragraph ends with one line break
    t = re.sub(r"\[/?(/p|list|olist|tr|table)\b[^\]]*\]|\[/p\]|<br\s*/?>|</p>", "\n", t, flags=re.I)
    t = re.sub(r"<li>\s*", "\n• ", t, flags=re.I)
    t = re.sub(r"\[/?[a-z0-9*]+(=[^\]]*)?\]|<[^>]+>", "", t, flags=re.I)
    t = html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"\u2022\s*\n+\s*", "\u2022 ", t)  # a bullet whose text sat in its own paragraph
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in t.split("\n")]
    out = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    t = re.sub(r"\n\n(?=• )", "\n", "\n".join(out).strip())  # a list stays together
    if len(t) > MAX_TEXT:
        t = t[:MAX_TEXT].rsplit(" ", 1)[0].rstrip() + "…"
    return t


def fetch(appid):
    """[{title, date, text, url, patch}], newest first. Raises on network errors."""
    r = requests.get(FEED, params={"appid": appid, "count": COUNT, "maxlength": 0,
                                   "feeds": "steam_community_announcements"}, timeout=20)
    r.raise_for_status()
    out = []
    for n in ((r.json().get("appnews") or {}).get("newsitems") or []):
        title = html.unescape(n.get("title") or "").strip()
        gid = n.get("gid") or ""
        tags = n.get("tags") or []
        out.append({"title": title, "date": int(n.get("date") or 0), "text": plain(n.get("contents")),
                    "url": f"https://store.steampowered.com/news/app/{appid}/view/{gid}" if gid else n.get("url") or "",
                    "patch": "patchnotes" in tags or bool(PATCH_WORDS.search(title))})
    out.sort(key=lambda x: -x["date"])
    return out


def get(appid, force=False):
    """The cached notes while fresh, else new ones (the cache when offline); [] without an app id."""
    appid = str(appid or "")
    if not appid.isdigit():
        return []
    with _lock:
        cache = read_json(FILE) or {}
    entry = cache.get(appid) or {}
    if not force and time.time() - entry.get("t", 0) < TTL:
        return entry.get("notes") or []
    try:
        notes = fetch(appid)
    except Exception:
        return entry.get("notes") or []
    with _lock:
        cache = read_json(FILE) or {}
        cache[appid] = {"t": time.time(), "notes": notes}
        if len(cache) > 400:  # keep the most recently asked ones
            for old in sorted(cache, key=lambda k: cache[k].get("t", 0))[:len(cache) - 400]:
                cache.pop(old, None)
        write_json(FILE, cache)
    return notes

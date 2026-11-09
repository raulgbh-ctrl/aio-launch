"""Put your Epic, GOG, Amazon and Battle.net games into Steam as non-Steam games, each with
its own cover, wide banner, background (hero), logo and icon, so they show up in Game Mode
and Big Picture. Each shortcut runs `aiolaunch --play <game>`, which applies the game's
Proton settings and cloud saves and stays open while the game runs, so Steam knows when
it is playing.

Steam rewrites shortcuts.vdf when it exits: edit it only while Steam is closed.
"""
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from . import covers
from .config import CACHE_DIR, settings
from .steamshortcut import accounts, dumps, launcher_path, loads, shortcut_id

TAG = "AIO Launch"
ART_CACHE = CACHE_DIR / "steam-art"
SGDB = "https://www.steamgriddb.com/api/v2"


def _is_ours(sc):
    return str(sc.get("LaunchOptions", "")).startswith("--play ")


def _key_of(sc):
    opts = str(sc.get("LaunchOptions", ""))
    return opts[len("--play "):].strip().strip('"') if opts.startswith("--play ") else ""


def eligible(game):
    """Games Steam does not already own a library entry for."""
    return game.store != "steam" and game.installed


def in_steam_keys():
    keys = set()
    for acct in accounts():
        try:
            data = loads((acct / "config/shortcuts.vdf").read_bytes())
        except (OSError, ValueError):
            continue
        keys |= {_key_of(sc) for sc in data.get("shortcuts", {}).values() if _is_ours(sc)}
    return keys


# ---------------------------------------------------------------- artwork sources
def _get(url, path):
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and r.content and r.headers.get("Content-Type", "").startswith("image"):
            path.write_bytes(r.content)
            return True
    except requests.RequestException:
        pass
    return False


def _steamgriddb(title, key):
    h = {"Authorization": "Bearer " + key}
    try:
        hits = requests.get(f"{SGDB}/search/autocomplete/{requests.utils.quote(title, safe='')}",
                            headers=h, timeout=15).json().get("data") or []
        if not hits:
            return {}
        want = covers.norm(title)
        gid = next((g for g in hits if covers.norm(g.get("name", "")) == want), hits[0])["id"]
        out = {}
        for kind, path, params in (("portrait", "grids", {"dimensions": "600x900"}),
                                   ("wide", "grids", {"dimensions": "920x430,460x215"}),
                                   ("hero", "heroes", {}), ("logo", "logos", {}), ("icon", "icons", {})):
            data = requests.get(f"{SGDB}/{path}/game/{gid}", headers=h, timeout=15,
                                params={"nsfw": "false", **params}).json().get("data") or []
            if data:
                out[kind] = data[0]["url"]
        return out
    except (requests.RequestException, ValueError, KeyError):
        return {}


def _steam_store(appid):
    import json
    q = {"ids": [{"appid": int(appid)}], "context": {"country_code": "US", "language": "english"},
         "data_request": {"include_assets": True}}
    try:
        items = requests.get("https://api.steampowered.com/IStoreBrowseService/GetItems/v1",
                             params={"input_json": json.dumps(q)}, timeout=15).json()["response"]["store_items"]
        a = items[0].get("assets") or {}
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return {}
    fmt = a.get("asset_url_format")
    if not fmt:
        return {}
    base = "https://shared.akamai.steamstatic.com/store_item_assets/"
    url = lambda name: base + fmt.replace("${FILENAME}", name) if name else ""
    return {"portrait": url(a.get("library_capsule")), "wide": url(a.get("header")),
            "hero": url(a.get("library_hero")),
            "logo": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/logo.png"}


def _steam_appid(game):
    if game.extra.get("steam_appid"):
        return game.extra["steam_appid"]
    try:
        r = requests.get("https://store.steampowered.com/api/storesearch/",
                         params={"term": game.title, "cc": "us", "l": "en"}, timeout=15).json()
        want = covers.norm(game.title)
        hit = next((i for i in r.get("items", []) if i.get("type") == "app" and covers.norm(i.get("name", "")) == want), None)
        return hit["id"] if hit else None
    except (requests.RequestException, ValueError):
        return None


def gather_art(game, folder: Path, sid: int):
    """Download the best available art into Steam's grid folder; draw what is missing."""
    folder.mkdir(parents=True, exist_ok=True)
    targets = {"portrait": folder / f"{sid}p.png", "wide": folder / f"{sid}.png",
               "hero": folder / f"{sid}_hero.png", "logo": folder / f"{sid}_logo.png",
               "icon": folder / f"{sid}_icon.png"}
    sources = []
    key = settings.get("steamgriddb_key").strip()
    if key:
        sources.append(_steamgriddb(game.title, key))
    appid = _steam_appid(game)
    if appid:
        sources.append(_steam_store(appid))
    sources.append({"portrait": game.cover if game.cover.startswith("http") else "",
                    "wide": game.cover_fallback if game.cover_fallback.startswith("http") else "",
                    "logo": game.extra.get("logo", ""), "hero": game.extra.get("hero", "")})
    got = {}
    for kind, path in targets.items():
        for src in sources:
            url = src.get(kind)
            if url and _get(url, path):
                got[kind] = path
                break
    _fill_missing(targets, got, game)
    return {k: v for k, v in targets.items() if v.exists()}


def _fill_missing(targets, got, game):
    """Make a wide banner, background and icon from the cover when no store had them."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    cover = QImage(str(got["portrait"])) if "portrait" in got else QImage()

    def background(w, h):
        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        img.fill(QColor("#141218"))
        p = QPainter(img)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if not cover.isNull():
            small = cover.scaled(24, 24, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)  # cheap blur
            p.drawImage(QRectF(0, 0, w, h), small)
            p.fillRect(0, 0, w, h, QColor(0, 0, 0, 90))
        return img, p

    if "wide" not in got:
        img, p = background(920, 430)
        if not cover.isNull():
            p.drawImage(QRectF(40, 25, 380 * 2 / 3 * 1.0, 380), cover)
        f = QFont()
        f.setPixelSize(40)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRectF(330, 0, 560, 430), Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap, game.title)
        p.end()
        img.save(str(targets["wide"]))
    if "hero" not in got:
        img, p = background(1920, 620)
        p.end()
        img.save(str(targets["hero"]))
    if "portrait" not in got:
        img, p = background(600, 900)
        f = QFont()
        f.setPixelSize(54)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRectF(40, 0, 520, 900), Qt.AlignCenter | Qt.TextWordWrap, game.title)
        p.end()
        img.save(str(targets["portrait"]))
    if "icon" not in got and not cover.isNull():
        side = min(cover.width(), cover.height())
        cover.copy((cover.width() - side) // 2, 0, side, side).scaled(
            256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(str(targets["icon"]))


# ---------------------------------------------------------------- write shortcuts
def sync_games(games, remove_missing=True, progress=None):
    """Make Steam's non-Steam list match `games` (only entries this app created are touched).
    Steam must be closed. Returns (added_or_updated, removed)."""
    exe = launcher_path()
    if not exe:
        raise RuntimeError("Could not find the installed aiolaunch command")
    accts = accounts()
    if not accts:
        raise RuntimeError("Sign in to Steam once first, so it has an account folder to add to")
    wanted = {g.key: g for g in games}
    done = removed = 0
    for acct in accts:
        cfg = acct / "config"
        f = cfg / "shortcuts.vdf"
        try:
            data = loads(f.read_bytes()) if f.exists() else {"shortcuts": {}}
        except ValueError:
            continue  # never overwrite a file we could not read
        shortcuts = data.setdefault("shortcuts", {})
        current = {_key_of(sc): idx for idx, sc in shortcuts.items() if _is_ours(sc)}
        if remove_missing:
            for k, idx in list(current.items()):
                if k not in wanted:
                    shortcuts.pop(idx, None)
                    removed += 1
        work = list(wanted.values())

        def one(g):
            sid = shortcut_id(f'"{exe}"', g.title)
            art = gather_art(g, cfg / "grid", sid)
            return g, sid, art

        with ThreadPoolExecutor(4) as pool:
            for n, (g, sid, art) in enumerate(pool.map(one, work), 1):
                idx = current.get(g.key)
                if idx is None or idx not in shortcuts:
                    idx = str(max([int(k) for k in shortcuts if k.isdigit()] + [-1]) + 1)
                old = shortcuts.get(idx, {})
                shortcuts[idx] = {
                    "appid": sid - 2**32, "AppName": g.title, "Exe": f'"{exe}"',
                    "StartDir": f'"{os.path.dirname(exe)}"', "icon": str(art.get("icon", "")),
                    "ShortcutPath": "", "LaunchOptions": f'--play "{g.key}"', "IsHidden": 0,
                    "AllowDesktopConfig": 1, "AllowOverlay": 1, "OpenVR": 0, "Devkit": 0,
                    "DevkitGameID": "", "DevkitOverrideAppID": 0,
                    "LastPlayTime": old.get("LastPlayTime", 0), "FlatpakAppID": "",
                    "tags": {"0": TAG, "1": {"epic": "Epic Games", "gog": "GOG", "amazon": "Amazon Games",
                                             "battlenet": "Battle.net"}.get(g.store, g.store)},
                }
                done += 1
                if progress:
                    progress(n, len(work))
        # re-number so Steam sees a clean 0..n list
        data["shortcuts"] = {str(i): sc for i, sc in enumerate(shortcuts.values())}
        if f.exists():
            shutil.copy2(f, cfg / "shortcuts.vdf.aiolaunch-backup")
        tmp = cfg / "shortcuts.vdf.tmp"
        tmp.write_bytes(dumps(data))
        os.replace(tmp, f)
    return done, removed

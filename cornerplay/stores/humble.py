"""Humble Bundle: the DRM-free games in your Humble library (bundles, the store, Humble Choice).

Humble has no public API: Cornerplay asks the same pages the Humble library page does
(/api/v1/user/order and /api/v1/orders), signed in with your session cookie (_simpleauth_sess),
as Lutris does. Signing in happens in Cornerplay's sign-in window (the cookie is read from it,
the password never), or by pasting the cookie's value. Kept in ~/.config/cornerplay/humble_auth.json,
readable only by you.

A game is listed when one of its downloads is for Linux or Windows (soundtracks, books and
Android files are left out; Steam keys from bundles show up through Steam once redeemed).
Games install into <games>/humble/<machine name>: the Linux download when there is one, else
the Windows one through Proton. Downloading and unpacking run in cornerplay.humbledl.
"""
import json
import os
import shutil
import sys

from ..config import CONFIG_DIR, read_json, settings, write_private
from ..net import redact, requests
from ..runner import StoreError, extras, perf_env, user_env, wine_env, wrapper_argv
from .base import Command, Game, Store

SITE = "https://www.humblebundle.com"
API = SITE + "/api/v1"
LOGIN_URL = SITE + "/login?goto=%2Fhome%2Flibrary"
COOKIE = "_simpleauth_sess"
AUTH_FILE = CONFIG_DIR / "humble_auth.json"
MANIFEST = ".cornerplay-humble.json"
PLATFORMS = ("linux", "windows")
BATCH = 40  # orders asked for at once


def install_root():
    return settings.games_dir / "humble"


def game_dir(machine):
    return install_root() / "".join(c for c in str(machine) if c.isalnum() or c in "_-")


def manifest(machine):
    return read_json(game_dir(machine) / MANIFEST) or {}


def cookie():
    return (read_json(AUTH_FILE) or {}).get("cookie", "")


def get(path, params=None, value=None):
    """A Humble API call with the session cookie; StoreError when signed out or unreachable."""
    value = value or cookie()
    if not value:
        raise StoreError("Not signed in to Humble Bundle")
    try:
        r = requests.get(API + path, params=params, timeout=30, cookies={COOKIE: value},
                         headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
    except requests.RequestException as e:
        raise StoreError(f"Could not reach Humble Bundle ({type(e).__name__})") from None
    if r.status_code in (401, 403) or "/login" in r.url:
        raise StoreError("Humble Bundle signed you out: sign in again in Accounts")
    if not r.ok:
        raise StoreError(redact(f"Humble Bundle: {r.status_code} {r.text[:120]}"))
    try:
        return r.json()
    except ValueError:
        raise StoreError("Humble Bundle sent something Cornerplay could not read") from None


def orders(value=None):
    """Every order in the library, with its products: {gamekey: order}."""
    keys = [o.get("gamekey") for o in get("/user/order", value=value) or [] if isinstance(o, dict) and o.get("gamekey")]
    out = {}
    for i in range(0, len(keys), BATCH):
        chunk = keys[i:i + BATCH]
        try:
            data = get("/orders", [("all_tpkds", "false")] + [("gamekeys", k) for k in chunk], value=value)
            if isinstance(data, dict):
                out.update(data)
                continue
        except StoreError as e:
            if "signed you out" in str(e):
                raise
        for k in chunk:  # the batch page failed: one order at a time
            try:
                out[k] = get(f"/order/{k}", value=value)
            except StoreError as e:
                if "signed you out" in str(e):
                    raise
    return out


def downloads(sub):
    """{"linux": [file, ...], "windows": [...]} for one product (files: name, url, size, md5)."""
    out = {}
    for d in sub.get("downloads") or []:
        platform = d.get("platform")
        if platform not in PLATFORMS:
            continue
        for f in d.get("download_struct") or []:
            url = (f.get("url") or {}).get("web") or ""
            if url:
                out.setdefault(platform, []).append({"name": f.get("name") or "", "url": url,
                                                     "size": int(f.get("file_size") or 0), "md5": f.get("md5") or ""})
    return out


def games_in(orders_):
    """The games in the orders, one per product (bought twice: listed once)."""
    games = {}
    for key, order in orders_.items():
        if not isinstance(order, dict):
            continue
        for sub in order.get("subproducts") or []:
            files = downloads(sub)
            machine = sub.get("machine_name") or ""
            if not files or not machine:
                continue
            games.setdefault(machine, {"machine": machine, "title": sub.get("human_name") or machine,
                                       "icon": sub.get("icon") or "", "gamekey": key, "url": sub.get("url") or "",
                                       "linux": "linux" in files, "windows": "windows" in files})
    return list(games.values())


class Humble(Store):
    id = "humble"
    name = "Humble Bundle"
    color = "#cc2929"
    tile = "#a32020"
    login_kind = "paste"   # the sign-in window when Qt WebEngine is there (humbleWebDone), else paste the cookie

    # --- state -----------------------------------------------------------
    def logged_in(self):
        return bool(cookie())

    def account(self):
        return (read_json(AUTH_FILE) or {}).get("account", "")

    def login_begin(self):
        return {"url": LOGIN_URL,
                "prompt": "Sign in to Humble Bundle in your browser, then copy the value of the "
                          "_simpleauth_sess cookie for humblebundle.com (Developer tools > Storage > Cookies) "
                          "and paste it here. It lets Cornerplay read your library; your password is never needed."}

    def login_finish(self, text):
        value = text.strip()
        if value.startswith(COOKIE + "="):         # pasted as name=value (maybe with ; Path=/ ...)
            value = value[len(COOKIE) + 1:].split(";")[0]
        value = value.strip().strip('"').strip()
        if not value or len(value) > 4000 or any(c.isspace() for c in value):
            raise StoreError("Paste just the value of the _simpleauth_sess cookie")
        found = get("/user/order", value=value)  # does Humble know this session?
        write_private(AUTH_FILE, json.dumps({"cookie": value, "account": f"{len(found or [])} orders"}))

    def logout(self):
        AUTH_FILE.unlink(missing_ok=True)

    # --- library ---------------------------------------------------------
    def fetch(self):
        if not self.logged_in():
            return []
        out = []
        for g in games_in(orders()):
            m = manifest(g["machine"])
            exe = m.get("exe", "")
            path = exe if os.path.isabs(exe) else os.path.join(game_dir(g["machine"]), exe)
            game = Game(store=self.id, id=g["machine"], title=g["title"], cover=g["icon"],
                        installed=bool(exe) and os.path.exists(path),
                        install_path=str(game_dir(g["machine"])) if m else "")
            game.extra.update(gamekey=g["gamekey"], url=g["url"], linux=g["linux"], windows=g["windows"],
                              platform=m.get("platform", "linux" if g["linux"] else "windows"))
            out.append(game)
        return out

    # --- actions ---------------------------------------------------------
    def install(self, game, platform=""):
        if not (game.extra.get("linux") or game.extra.get("windows")):
            raise StoreError(f"{game.title} has no Linux or Windows download on Humble Bundle")
        want = platform or ("linux" if game.extra.get("linux") and settings.get("gog_native") else "windows"
                            if game.extra.get("windows") else "linux")
        os.makedirs(install_root(), exist_ok=True)
        return Command([sys.executable, "-m", "cornerplay.humbledl", game.id, game.extra.get("gamekey", ""),
                        str(game_dir(game.id)), want])

    update = install  # a newer download simply replaces the old files

    def uninstall(self, game):
        target = game_dir(game.id)
        root = install_root().resolve()
        if target.resolve().parent != root or not target.name:
            raise StoreError("Not a Humble Bundle install folder")
        shutil.rmtree(target, ignore_errors=True)
        return None

    def launch(self, game):
        m = manifest(game.id)
        exe = m.get("exe", "")
        exe = exe if os.path.isabs(exe) else os.path.join(game_dir(game.id), exe) if exe else ""
        if not exe or not os.path.exists(exe):
            raise StoreError(f"{game.title} is not installed (or its program was moved); install it again")
        cwd = os.path.dirname(exe)
        if m.get("platform") == "linux":
            env = {k: v for k, v in perf_env(self.id, game.id).items() if k == "MANGOHUD_CONFIG"}
            env.update(user_env())
            return Command([*extras(), exe], env=env, cwd=cwd)
        return Command([*wrapper_argv(), exe], env=wine_env(self.id, game.id), cwd=cwd)

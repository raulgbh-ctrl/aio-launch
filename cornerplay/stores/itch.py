"""itch.io: the games you bought or claimed, through itch's own API (the one the itch app uses).

Sign in by pasting an API key from https://itch.io/user/settings/api-keys (it can only read
your library and download what you own). Kept in ~/.config/cornerplay/itch_auth.json,
readable only by you. Games install into <games>/itch/<game id>: the Linux build when the
game has one, else the Windows build (run through Proton). The download and unpacking run in
cornerplay.itchdl, which prints progress like the other stores' tools.
"""
import json
import os
import shutil
import sys

from ..config import CONFIG_DIR, read_json, settings, write_private
from ..net import redact, requests
from ..runner import StoreError, extras, perf_env, user_env, wine_env, wrapper_argv
from .base import Command, Game, Store

API = "https://api.itch.io"
AUTH_FILE = CONFIG_DIR / "itch_auth.json"
MANIFEST = ".cornerplay-itch.json"  # in a game's folder: which upload, which platform, which program


def install_root():
    return settings.games_dir / "itch"


def game_dir(game_id):
    return install_root() / "".join(c for c in str(game_id) if c.isdigit())


def manifest(game_id):
    return read_json(game_dir(game_id) / MANIFEST) or {}


class Itch(Store):
    id = "itch"
    name = "itch.io"
    color = "#fa5c5c"
    tile = "#c93f3f"
    login_kind = "paste"

    def _key(self):
        return (read_json(AUTH_FILE) or {}).get("api_key", "")

    def _get(self, path, **params):
        key = self._key()
        if not key:
            raise StoreError("Not signed in to itch.io")
        try:
            r = requests.get(API + path, params=params, timeout=30, headers={"Authorization": f"Bearer {key}"})
        except requests.RequestException as e:
            raise StoreError(f"Could not reach itch.io ({type(e).__name__})") from None
        if r.status_code in (401, 403):
            raise StoreError("itch.io did not accept the API key: sign in again with a new one")
        if not r.ok:
            raise StoreError(redact(f"itch.io: {r.status_code} {r.text[:120]}"))
        return r.json()

    # --- state -----------------------------------------------------------
    def logged_in(self):
        return bool(self._key())

    def account(self):
        return (read_json(AUTH_FILE) or {}).get("username", "")

    def login_begin(self):
        return {"url": "https://itch.io/user/settings/api-keys",
                "prompt": "On that page press \"Generate new API key\", then copy the key and paste it here. "
                          "It can only read your library and download your games."}

    def login_finish(self, text):
        key = text.strip()
        if not key or len(key) > 200 or any(c.isspace() for c in key):
            raise StoreError("Paste just the API key")
        write_private(AUTH_FILE, json.dumps({"api_key": key}))
        try:
            user = (self._get("/profile").get("user") or {})
        except StoreError:
            AUTH_FILE.unlink(missing_ok=True)
            raise
        write_private(AUTH_FILE, json.dumps({"api_key": key, "username": user.get("username", "")}))

    def logout(self):
        AUTH_FILE.unlink(missing_ok=True)

    # --- library ---------------------------------------------------------
    def fetch(self):
        if not self.logged_in():
            return []  # not signed in is not an error: nothing to list, no toast on every start
        games, seen, page = [], set(), 1
        while page < 100:
            data = self._get("/profile/owned-keys", page=page)
            keys = data.get("owned_keys") or []
            for k in keys:
                g = k.get("game") or {}
                gid = str(g.get("id") or k.get("game_id") or "")
                if not gid or gid in seen or g.get("classification", "game") not in ("game", "tool", ""):
                    continue
                seen.add(gid)
                traits = set(g.get("traits") or [])
                m = manifest(gid)
                game = Game(store=self.id, id=gid, title=g.get("title") or f"itch.io game {gid}",
                            cover=g.get("cover_url") or g.get("still_cover_url") or "",
                            installed=bool(m.get("exe")) and os.path.exists(os.path.join(game_dir(gid), m["exe"])),
                            install_path=str(game_dir(gid)) if m else "")
                game.extra.update(key_id=str(k.get("id", "")), url=g.get("url", ""),
                                  linux="p_linux" in traits, windows="p_windows" in traits,
                                  platform=m.get("platform", "linux" if "p_linux" in traits else "windows"))
                games.append(game)
            if len(keys) < int(data.get("per_page") or 50):
                break
            page += 1
        return games

    # --- actions ---------------------------------------------------------
    def install(self, game):
        if not (game.extra.get("linux") or game.extra.get("windows")):
            raise StoreError(f"{game.title} has no Linux or Windows download on itch.io")
        prefer = "windows" if game.extra.get("platform") == "windows" and not game.extra.get("linux") else "linux"
        os.makedirs(install_root(), exist_ok=True)
        return Command([sys.executable, "-m", "cornerplay.itchdl", game.id, game.extra.get("key_id", ""),
                        str(game_dir(game.id)), prefer])

    update = install  # a newer upload simply replaces the old files

    def uninstall(self, game):
        target = game_dir(game.id)
        root = install_root().resolve()
        if target.resolve().parent != root or not target.name:
            raise StoreError("Not an itch.io install folder")
        shutil.rmtree(target, ignore_errors=True)
        return None

    def launch(self, game):
        m = manifest(game.id)
        exe = os.path.join(game_dir(game.id), m.get("exe", "")) if m.get("exe") else ""
        if not exe or not os.path.exists(exe):
            raise StoreError(f"{game.title} is not installed (or its program was moved); install it again")
        cwd = os.path.dirname(exe)
        if m.get("platform") == "linux":
            env = {k: v for k, v in perf_env(self.id, game.id).items() if k == "MANGOHUD_CONFIG"}
            env.update(user_env())
            return Command([*extras(), exe], env=env, cwd=cwd)
        return Command([*wrapper_argv(), exe], env=wine_env(self.id, game.id), cwd=cwd)


"""Epic Games Store through the legendary CLI."""
import json
import os

import time

from ..config import CACHE_DIR, XDG_CONFIG, find_tool, read_json, settings, write_json
from ..runner import StoreError, wine_env, wrapper_string
from .base import Command, Game, PartialResult, Store, run

LOGIN_URL = "https://legendary.gl/epiclogin"


class Epic(Store):
    id = "epic"
    name = "Epic Games"
    color = "#9aa0aa"
    dlc_note = "Epic lists the DLC you own; DLC you have not bought is not shown."

    def tool(self):
        t = find_tool("legendary")
        if not t:
            raise StoreError(self.problem())
        return t

    def problem(self):
        return "" if find_tool("legendary") else "legendary not found (run: cornerplay --fetch-backends)"

    def _user(self):
        return read_json(XDG_CONFIG / "legendary/user.json") or {}

    def logged_in(self):
        return bool(self._user())

    def account(self):
        return self._user().get("displayName", "")

    def login_begin(self):
        self.tool()
        return {
            "url": LOGIN_URL,
            "prompt": "Sign in to Epic in your browser. The page then shows a short JSON "
                      "block: paste its authorizationCode value (or the whole block) here.",
        }

    def login_finish(self, text):
        text = text.strip()
        if text.startswith("{"):
            try:
                text = json.loads(text).get("authorizationCode") or ""
            except ValueError:
                pass
        code = text.strip().strip('"')
        if not code:
            raise StoreError("No authorization code found in what you pasted")
        r = run([self.tool(), "auth", "--code", code], timeout=90)
        if not self.logged_in():
            raise StoreError(_tail(r) or "Epic sign-in failed")

    def logout(self):
        run([self.tool(), "auth", "--delete"], timeout=30)

    def _installed(self):
        r = run([self.tool(), "list-installed", "--json"], timeout=60)
        try:
            return {g["app_name"]: g for g in json.loads(r.stdout or "[]")}
        except ValueError:
            return {}

    def fetch(self, force=False):
        installed = self._installed()
        games = {}
        error = ""
        if self.logged_in():
            argv = [self.tool(), "list", "--json"]
            stamp = CACHE_DIR / "epic_full_refresh.json"
            if force or time.time() - (read_json(stamp) or {}).get("t", 0) > 7 * 86400:
                argv.append("--force-refresh")  # Refresh button, else weekly: new games, art and details
            r = run(argv, timeout=300)
            if r.returncode == 0 and "--force-refresh" in argv:
                write_json(stamp, {"t": time.time()})
            try:
                listing = json.loads(r.stdout)
            except ValueError:
                listing, error = [], _tail(r) or "could not read the Epic library"
            for g in listing:
                if not g.get("asset_infos"):
                    continue  # third-party-store titles legendary cannot install
                app = g["app_name"]
                tall, wide, hero, logo = _images(g.get("metadata") or {})
                inst = installed.get(app)
                games[app] = Game(
                    store=self.id, id=app, title=(g.get("app_title") or app).strip(),
                    cover=tall or wide, cover_fallback=wide,
                    installed=bool(inst), install_path=(inst or {}).get("install_path", ""),
                    extra={"dlcs": [{"id": d.get("app_name", ""), "title": (d.get("app_title") or "").strip(),
                                     "image": _images(d.get("metadata") or {})[1]}
                                    for d in g.get("dlcs") or []],
                           "store_heroes": [hero] if hero else [], "store_logos": [logo] if logo else [],
                           "description": ((g.get("metadata") or {}).get("description") or "")[:600]},
                )
        for app, inst in installed.items():
            if app not in games and not inst.get("is_dlc"):
                games[app] = Game(store=self.id, id=app, title=inst.get("title", app),
                                  installed=True, install_path=inst.get("install_path", ""))
        for app in _updates(installed):
            if app in games:
                games[app].extra["update"] = True
        if error:
            raise PartialResult(list(games.values()), f"Epic: {error}")
        return list(games.values())

    def dlcs(self, game):
        installed = self._installed()
        rows = []
        for d in game.extra.get("dlcs") or []:
            status = "installed" if d["id"] in installed else "owned"
            rows.append({"id": d["id"], "title": d["title"] or d["id"], "status": status,
                         "image": d.get("image", ""), "price": "", "url": "",
                         "canInstall": status == "owned" and game.installed})
        return rows

    def install_dlc(self, game, dlc_id):
        if not game.installed:
            raise StoreError("Install the game first")
        return Command([self.tool(), "-y", "install", dlc_id])

    def install(self, game):
        base = settings.games_dir / "epic"
        base.mkdir(parents=True, exist_ok=True)
        return Command([self.tool(), "-y", "install", game.id, "--base-path", str(base)])

    def uninstall(self, game):
        return Command([self.tool(), "-y", "uninstall", game.id])

    def update(self, game):
        return Command([self.tool(), "-y", "update", game.id])

    def launch(self, game):
        """Blocking: asks legendary for the launch details so Cornerplay can run (and wait for) the game itself."""
        env = wine_env(self.id, game.id)
        base = [self.tool(), "launch", game.id, "--no-wine", "--wrapper", wrapper_string(), "--json"]
        r = run(base, timeout=90, env=env)
        if r.returncode != 0:  # offline, or Epic unreachable: legendary can still start most games
            r = run(base + ["--offline"], timeout=60, env=env)
        try:
            p = json.loads(r.stdout)
        except ValueError:
            raise StoreError(_tail(r) or "legendary could not prepare the launch")
        exe = os.path.join(p.get("game_directory", ""), p.get("game_executable", ""))
        argv = [*p.get("launch_command", []), exe, *p.get("game_parameters", []),
                *p.get("user_parameters", []), *p.get("egl_parameters", [])]
        env.update({k: str(v) for k, v in (p.get("environment") or {}).items()})
        return Command(argv, env=env, cwd=p.get("working_directory") or p.get("game_directory", ""))


def _updates(installed):
    """Installed games whose version differs from Epic's latest build.

    `legendary list` (run by fetch) refreshes assets.json with each game's newest
    build_version; this is the same comparison `legendary list-installed --check-updates` makes.
    """
    latest = {}
    for platform, items in (read_json(XDG_CONFIG / "legendary/assets.json") or {}).items():
        for a in items or []:
            latest[(platform, a.get("app_name"))] = a.get("build_version")
    out = set()
    for app, inst in installed.items():
        newest = latest.get((inst.get("platform") or "Windows", app))
        if newest and inst.get("version") and newest != inst["version"]:
            out.add(app)
    return out


def _images(meta):
    """(portrait cover, wide fallback, wide banner, logo) from Epic's key images."""
    tall = wide = hero = logo = ""
    for img in meta.get("keyImages") or []:
        kind, url = img.get("type"), img.get("url", "")
        if kind == "DieselGameBoxTall":
            tall = url + ("&" if "?" in url else "?") + "h=600&resize=1&w=400"
        elif kind in ("DieselGameBox", "Thumbnail") and not wide:
            wide = url
        if kind == "DieselGameBox":
            hero = url + ("&" if "?" in url else "?") + "w=1920&resize=1"  # 16:9 key art
        elif kind == "DieselGameBoxLogo":
            logo = url
    return tall, wide, hero, logo


def _tail(r, n=3):
    lines = [l for l in ((r.stderr or "") + (r.stdout or "")).splitlines() if l.strip()]
    return " ".join(lines[-n:])[-300:]

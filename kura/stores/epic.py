"""Epic Games Store through the legendary CLI."""
import json

from ..config import XDG_CONFIG, find_tool, read_json, settings
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
        return "" if find_tool("legendary") else "legendary not found (run: kura --fetch-backends)"

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

    def fetch(self):
        installed = self._installed()
        games = {}
        error = ""
        if self.logged_in():
            r = run([self.tool(), "list", "--json"], timeout=300)
            try:
                listing = json.loads(r.stdout)
            except ValueError:
                listing, error = [], _tail(r) or "could not read the Epic library"
            for g in listing:
                if not g.get("asset_infos"):
                    continue  # third-party-store titles legendary cannot install
                app = g["app_name"]
                tall, wide = _images(g.get("metadata") or {})
                inst = installed.get(app)
                games[app] = Game(
                    store=self.id, id=app, title=(g.get("app_title") or app).strip(),
                    cover=tall or wide, cover_fallback=wide,
                    installed=bool(inst), install_path=(inst or {}).get("install_path", ""),
                    extra={"dlcs": [{"id": d.get("app_name", ""), "title": (d.get("app_title") or "").strip()}
                                    for d in g.get("dlcs") or []]},
                )
        for app, inst in installed.items():
            if app not in games and not inst.get("is_dlc"):
                games[app] = Game(store=self.id, id=app, title=inst.get("title", app),
                                  installed=True, install_path=inst.get("install_path", ""))
        if error:
            raise PartialResult(list(games.values()), f"Epic: {error}")
        return list(games.values())

    def dlcs(self, game):
        installed = self._installed()
        return [{"title": d["title"] or d["id"], "url": "",
                 "status": "installed" if d["id"] in installed else "owned"}
                for d in game.extra.get("dlcs") or []]

    def install(self, game):
        base = settings.games_dir / "epic"
        base.mkdir(parents=True, exist_ok=True)
        return Command([self.tool(), "-y", "install", game.id, "--base-path", str(base)])

    def uninstall(self, game):
        return Command([self.tool(), "-y", "uninstall", game.id])

    def launch(self, game):
        return Command(
            [self.tool(), "launch", game.id, "--no-wine", "--wrapper", wrapper_string()],
            env=wine_env(self.id, game.id),
        )


def _images(meta):
    tall = wide = ""
    for img in meta.get("keyImages") or []:
        kind, url = img.get("type"), img.get("url", "")
        if kind == "DieselGameBoxTall":
            tall = url + ("&" if "?" in url else "?") + "h=600&resize=1&w=400"
        elif kind in ("DieselGameBox", "Thumbnail") and not wide:
            wide = url
    return tall, wide


def _tail(r, n=3):
    lines = [l for l in ((r.stderr or "") + (r.stdout or "")).splitlines() if l.strip()]
    return " ".join(lines[-n:])[-300:]

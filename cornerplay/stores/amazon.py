"""Amazon Games (Prime Gaming) through the nile CLI."""
import json
from urllib.parse import parse_qs, urlparse

from ..config import XDG_CONFIG, find_tool, read_json, settings
from ..runner import StoreError, wine_env, wrapper_string
from .base import Command, Game, PartialResult, Store, run

NILE_DIR = XDG_CONFIG / "nile"


class Amazon(Store):
    id = "amazon"
    name = "Amazon Games"
    color = "#ff9900"
    tile = "#d9800b"  # its logo sits in white on a tile of this colour

    def __init__(self):
        self._pending = None  # login data between login_begin and login_finish

    def tool(self):
        t = find_tool("nile")
        if not t:
            raise StoreError(self.problem())
        return t

    def problem(self):
        return "" if find_tool("nile") else "nile not found (run: cornerplay --fetch-backends)"

    def _user(self):
        return read_json(NILE_DIR / "current_user.json") or {}

    def logged_in(self):
        return bool(self._user().get("user_id"))

    def account(self):
        return self._user().get("name", "")

    def login_begin(self):
        r = run([self.tool(), "auth", "--login", "--non-interactive"], timeout=60)
        try:
            self._pending = json.loads(r.stdout.strip().splitlines()[-1])
            url = self._pending["url"]
        except (ValueError, IndexError, KeyError):
            raise StoreError("nile did not return a login link: " + (r.stderr or "")[-200:])
        return {
            "url": url,
            "prompt": "Sign in to Amazon in your browser. You are then sent to amazon.com: "
                      "copy that page's full address and paste it here.",
        }

    def login_finish(self, text):
        if not self._pending:
            raise StoreError("Start the sign-in again")
        query = parse_qs(urlparse(text.strip()).query)
        code = (query.get("openid.oa2.authorization_code") or [""])[0]
        if not code:
            raise StoreError("That address has no authorization code in it; paste the amazon.com "
                             "address you landed on after signing in")
        p = self._pending
        r = run([self.tool(), "register", "--code", code, "--client-id", p["client_id"],
                 "--code-verifier", p["code_verifier"], "--serial", p["serial"]], timeout=120)
        if not self.logged_in():
            raise StoreError("Amazon sign-in failed: " + ((r.stderr or r.stdout or "")[-200:]))
        self._pending = None

    def logout(self):
        run([self.tool(), "auth", "--logout"], timeout=60)

    def fetch(self):
        error = ""
        if self.logged_in():
            r = run([self.tool(), "library", "sync"], timeout=300)
            if r.returncode != 0:
                error = (r.stderr or "library sync failed").strip().splitlines()[-1][-200:]
        installed = {g["id"]: g for g in (read_json(NILE_DIR / "installed.json") or [])}
        games = []
        for entry in read_json(NILE_DIR / "library.json") or []:
            product = entry.get("product") or {}
            gid = product.get("id")
            if not gid:
                continue
            detail = (product.get("productDetail") or {})
            icon = detail.get("iconUrl") or (detail.get("details") or {}).get("logoUrl") or ""
            inst = installed.get(gid)
            games.append(Game(store=self.id, id=gid, title=product.get("title") or gid,
                              cover=icon, cover_fallback=icon,
                              installed=bool(inst), install_path=(inst or {}).get("path", "")))
        if installed and self.logged_in():
            updates = self._updates()
            for g in games:
                if g.id in updates and g.installed:
                    g.extra["update"] = True
        if error:
            raise PartialResult(games, f"Amazon: {error}")
        return games

    def install(self, game):
        base = settings.games_dir / "amazon"
        base.mkdir(parents=True, exist_ok=True)
        return Command([self.tool(), "install", game.id, "--base-path", str(base)])

    def uninstall(self, game):
        return Command([self.tool(), "uninstall", game.id])

    def _updates(self):
        """Ids of installed games with an update (`nile list-updates`); empty if the check fails."""
        try:
            r = run([self.tool(), "list-updates", "--json"], timeout=120)
            data = json.loads((r.stdout or "").strip() or "[]")
        except (StoreError, ValueError):
            return set()
        return {(d.get("id") if isinstance(d, dict) else d) for d in data or []} - {None}

    def verify(self, game):
        argv = [self.tool(), "verify", game.id]
        if game.install_path:
            argv += ["--path", game.install_path]
        return Command(argv)

    def update(self, game):
        argv = [self.tool(), "update", game.id]
        if game.install_path:
            argv += ["--path", game.install_path]
        return Command(argv)

    def launch(self, game):
        return Command(
            [self.tool(), "launch", game.id, "--no-wine", "--wrapper", wrapper_string()],
            env=wine_env(self.id, game.id),
        )

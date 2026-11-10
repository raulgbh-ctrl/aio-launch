"""GOG: library through GOG's own web API, downloads through gogdl."""
import glob
import os
import shlex
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

from ..net import requests

from pathlib import Path

from ..config import CACHE_DIR, CONFIG_DIR, XDG_CONFIG, find_tool, read_json, settings, write_json
from ..runner import StoreError, wine_env, wrapper_argv
from .base import Command, Game, PartialResult, Store

# GOG Galaxy's public client credentials, the same ones gogdl and Heroic use.
CLIENT_ID = "46899977096215655"
CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"
REDIRECT = "https://embed.gog.com/on_login_success?origin=client"
AUTH_URL = ("https://auth.gog.com/auth?client_id=" + CLIENT_ID +
            "&redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient"
            "&response_type=code&layout=client2")
AUTH_FILE = CONFIG_DIR / "gog_auth.json"  # same layout gogdl reads and refreshes
META_FILE = CACHE_DIR / "gog_meta.json"
# gogdl saves each installed build's manifest here (it holds the installed buildId).
GOGDL_MANIFESTS = Path(os.environ.get("GOGDL_CONFIG_PATH") or XDG_CONFIG) / "heroic_gogdl" / "manifests"


class Gog(Store):
    id = "gog"
    name = "GOG"
    color = "#b56cff"
    dlc_note = ""

    def problem(self):
        return "" if find_tool("gogdl") else "gogdl not found, needed to install games (run: cornerplay --fetch-backends)"

    # --- auth ------------------------------------------------------------
    def _creds(self):
        return (read_json(AUTH_FILE) or {}).get(CLIENT_ID)

    def _save(self, data):
        data["loginTime"] = time.time()
        allc = read_json(AUTH_FILE) or {}
        allc[CLIENT_ID] = data
        write_json(AUTH_FILE, allc)
        os.chmod(AUTH_FILE, 0o600)

    def _token(self):
        c = self._creds()
        if not c:
            raise StoreError("Not signed in to GOG")
        if time.time() >= c.get("loginTime", 0) + c.get("expires_in", 0) - 60:
            r = requests.get("https://auth.gog.com/token", params={
                "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token", "refresh_token": c["refresh_token"]}, timeout=20)
            if not r.ok:
                raise StoreError("GOG session expired, sign in again")
            c = r.json()
            self._save(c)
        return c["access_token"]

    def logged_in(self):
        return bool(self._creds())

    def account(self):
        return (read_json(CACHE_DIR / "gog_user.json") or {}).get("username", "")

    def login_begin(self):
        return {
            "url": AUTH_URL,
            "prompt": "Sign in to GOG in your browser. You end up on a blank page: "
                      "copy its full address (it contains code=...) and paste it here.",
        }

    def login_finish(self, text):
        text = text.strip()
        code = text
        if "code=" in text:
            code = (parse_qs(urlparse(text).query).get("code") or [""])[0]
        if not code:
            raise StoreError("No code found in what you pasted")
        try:
            r = requests.get("https://auth.gog.com/token", params={
                "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code", "redirect_uri": REDIRECT, "code": code}, timeout=20)
        except requests.RequestException as e:
            raise StoreError(f"Could not reach GOG ({type(e).__name__})")
        if not r.ok:
            raise StoreError("GOG rejected the code (codes expire quickly, try again)")
        self._save(r.json())

    def logout(self):
        for f in (AUTH_FILE, CACHE_DIR / "gog_user.json"):
            try:
                os.remove(f)
            except OSError:
                pass

    # --- library ---------------------------------------------------------
    def base_dir(self):
        return settings.games_dir / "gog"

    def _installed(self):
        """Scan the GOG folder for goggame-<id>.info files: {id: (path, info)}."""
        out = {}
        for info_path in glob.glob(str(self.base_dir() / "*" / "goggame-*.info")):
            info = read_json(info_path) or {}
            gid = str(info.get("gameId", ""))
            if gid and gid == str(info.get("rootGameId", gid)):
                out[gid] = (os.path.dirname(info_path), info)
        return out

    def fetch(self):
        installed = self._installed()
        games, error = {}, ""
        if self.logged_in():
            try:
                games = self._owned()
            except (requests.RequestException, ValueError, StoreError) as e:
                error = str(e)
        for gid, (path, info) in installed.items():
            g = games.setdefault(gid, Game(store=self.id, id=gid, title=info.get("name", gid)))
            g.installed, g.install_path = True, path
        for gid in self._updates(installed):
            games[gid].extra["update"] = True
        if error:
            raise PartialResult(list(games.values()), f"GOG: {error}")
        return list(games.values())

    def _updates(self, installed):
        """Installed games whose build is older than GOG's newest public build.

        The installed build comes from the manifest gogdl keeps after a download
        (or the game's goggame info file); games installed without either are skipped.
        """
        def check(gid):
            have = ((read_json(GOGDL_MANIFESTS / gid) or {}).get("buildId")
                    or installed[gid][1].get("buildId"))
            if not have:
                return None
            try:
                r = requests.get(f"https://content-system.gog.com/products/{gid}/os/windows/builds",
                                 params={"generation": 2}, timeout=15)
                items = [i for i in r.json().get("items") or []
                         if not i.get("branch") and i.get("generation", 2) == 2]
            except (requests.RequestException, ValueError):
                return None
            return gid if items and str(items[0].get("build_id")) != str(have) else None

        if not installed:
            return set()
        with ThreadPoolExecutor(4) as pool:
            return {gid for gid in pool.map(check, installed) if gid}

    def _owned(self):
        s = requests.Session()
        s.headers["Authorization"] = "Bearer " + self._token()
        try:
            write_json(CACHE_DIR / "gog_user.json", s.get("https://embed.gog.com/userData.json", timeout=20).json())
        except (requests.RequestException, ValueError):
            pass
        games, page, pages = {}, 1, 1
        while page <= pages:
            r = s.get("https://embed.gog.com/account/getFilteredProducts",
                      params={"mediaType": 1, "page": page}, timeout=30)
            r.raise_for_status()
            data = r.json()
            pages = int(data.get("totalPages", 1))
            for p in data.get("products", []):
                gid = str(p["id"])
                img = p.get("image") or ""
                wide = ("https:" + img + "_392.jpg") if img.startswith("//") else ""
                games[gid] = Game(store=self.id, id=gid, title=p.get("title", gid),
                                  cover=wide, cover_fallback=wide)
            page += 1

        # Vertical box art lives on a per-game endpoint; cached, and looked at again every week
        # so new art shows up.
        meta = read_json(META_FILE) or {}
        now = time.time()
        missing = [g for g in games if not isinstance(meta.get(g), dict) or "logo" not in meta[g]
                   or now - meta[g].get("t", 0) > 7 * 86400]

        def boxart(gid):
            """Portrait box art and the wide Galaxy background for one game."""
            try:
                links = requests.get(f"https://api.gog.com/v2/games/{gid}", timeout=15).json().get("_links", {})
            except (requests.RequestException, ValueError):
                return gid, None
            href = lambda name: (links.get(name) or {}).get("href", "")
            return gid, {"box": href("boxArtImage"), "logo": href("logo"), "t": time.time(),
                         "hero": href("galaxyBackgroundImage") or href("backgroundImage")}

        if missing:
            with ThreadPoolExecutor(8) as pool:
                for gid, url in pool.map(boxart, missing):
                    if url is not None:
                        meta[gid] = url
            write_json(META_FILE, meta)
        for gid, g in games.items():
            m = meta.get(gid)
            m = m if isinstance(m, dict) else {"box": m or ""}
            if m.get("box"):
                g.cover = m["box"]
            if m.get("hero"):
                g.extra["store_heroes"] = [m["hero"]]
            if m.get("logo"):
                g.extra["store_logos"] = [m["logo"]]
        return games

    def dlcs(self, game):
        try:
            r = requests.get(f"https://api.gog.com/products/{game.id}",
                             params={"expand": "expanded_dlcs"}, timeout=20)
            r.raise_for_status()
            items = r.json().get("expanded_dlcs") or []
            owned = set()
            if items and self.logged_in():
                o = requests.get("https://embed.gog.com/user/data/games", timeout=20,
                                 headers={"Authorization": "Bearer " + self._token()})
                owned = {str(i) for i in o.json().get("owned", [])} if o.ok else set()
        except (requests.RequestException, ValueError) as e:
            raise StoreError(f"Could not reach GOG ({type(e).__name__})")
        prices = self._prices([str(d.get("id")) for d in items])
        # gogdl leaves a goggame-<id>.info file in the game's folder for each DLC it installed
        installed = {os.path.basename(p)[8:-5] for p in glob.glob(os.path.join(game.install_path or "/nonexistent",
                                                                               "goggame-*.info"))}
        rows = []
        for d in items:
            did = str(d.get("id"))
            status = "installed" if did in installed else "owned" if did in owned else "available"
            img = (d.get("images") or {}).get("logo2x") or (d.get("images") or {}).get("logo") or ""
            rows.append({"id": did, "title": d.get("title", did), "status": status,
                         "image": ("https:" + img) if img.startswith("//") else img,
                         "price": "" if status != "available" else prices.get(did, ""),
                         "url": (d.get("links") or {}).get("product_card", ""),
                         "canInstall": status == "owned" and game.installed and d.get("is_installable", True)})
        return rows

    def _prices(self, ids):
        """{product id: "€29.99"} in the player's country (GOG account, else the system locale)."""
        if not ids:
            return {}
        country = (read_json(CACHE_DIR / "gog_user.json") or {}).get("country", "")
        if not country:
            from PySide6.QtCore import QLocale
            name = QLocale.system().name()  # "es_ES"
            country = name.split("_")[1] if "_" in name else "US"
        try:
            r = requests.get("https://api.gog.com/products/prices",
                             params={"ids": ",".join(ids), "countryCode": country}, timeout=15)
            items = (r.json().get("_embedded") or {}).get("items") or []
        except (requests.RequestException, ValueError):
            return {}
        out = {}
        for it in items:
            pid = ((it.get("_embedded") or {}).get("product") or {}).get("id") or it.get("id")
            for p in (it.get("_embedded") or {}).get("prices") or []:
                amount, _, cur = (p.get("finalPrice") or "").partition(" ")
                if amount.isdigit():
                    sym = {"USD": "$", "EUR": "€", "GBP": "£", "PLN": "zł "}.get(cur, cur + " ")
                    out[str(pid)] = "Free" if amount == "0" else f"{sym}{int(amount) / 100:.2f}"
                    break
        return out

    def install_dlc(self, game, dlc_id):
        # gogdl's update with --with-dlcs fetches every owned DLC that is not on disk yet.
        return self.update(game)

    # --- actions ---------------------------------------------------------
    def install(self, game):
        tool = find_tool("gogdl")
        if not tool:
            raise StoreError(self.problem())
        self._token()  # make sure the token file is fresh before gogdl reads it
        base = self.base_dir()
        base.mkdir(parents=True, exist_ok=True)
        return Command([tool, "--auth-config-path", str(AUTH_FILE), "download", game.id,
                        "--platform", "windows", "--path", str(base), "--with-dlcs", "--lang", "en-US"])

    def update(self, game):
        tool = find_tool("gogdl")
        if not tool:
            raise StoreError(self.problem())
        if not game.install_path or not os.path.isdir(game.install_path):
            raise StoreError("Game files not found; try Refresh")
        self._token()
        # For "update", gogdl takes the game's own folder as --path (for "download" it is the parent).
        return Command([tool, "--auth-config-path", str(AUTH_FILE), "update", game.id,
                        "--platform", "windows", "--path", game.install_path, "--with-dlcs", "--lang", "en-US"])

    def uninstall(self, game):
        path = os.path.realpath(game.install_path or "")
        base = os.path.realpath(self.base_dir())
        if not path.startswith(base + os.sep) or not os.path.isdir(path):
            raise StoreError("Refusing to delete a folder outside Cornerplay's GOG directory")
        shutil.rmtree(path)
        return None

    def launch(self, game):
        found = self._installed().get(game.id)
        if not found:
            raise StoreError("Game files not found; try Refresh")
        path, info = found
        tasks = [t for t in info.get("playTasks", []) if t.get("type") == "FileTask" and t.get("path")]
        task = next((t for t in tasks if t.get("isPrimary")), tasks[0] if tasks else None)
        if not task:
            raise StoreError("This game has no launch task Cornerplay understands")
        exe = _resolve(path, task["path"])
        cwd = _resolve(path, task.get("workingDir") or "") if task.get("workingDir") else os.path.dirname(exe)
        args = shlex.split(task.get("arguments") or "", posix=False)
        return Command([*wrapper_argv(), exe, *args], env=wine_env(self.id, game.id), cwd=cwd)


def _resolve(root, rel):
    """Join a Windows-style relative path, matching case-insensitively."""
    cur = root
    for part in rel.replace("\\", "/").split("/"):
        if not part or part == ".":
            continue
        cand = os.path.join(cur, part)
        if not os.path.exists(cand) and os.path.isdir(cur):
            low = part.lower()
            cand = next((os.path.join(cur, e) for e in os.listdir(cur) if e.lower() == low), cand)
        cur = cand
    return cur

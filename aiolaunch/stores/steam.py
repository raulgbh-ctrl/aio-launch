"""Steam: reads the local client's libraries; installs and launches via steam:// URLs."""
import glob
import os
import shutil

from ..net import requests

from .. import vdf
import json

from ..config import CACHE_DIR, HOME, read_json, settings, write_json
from ..runner import StoreError
from .base import Command, Game, PartialResult, Store

FLATPAK_ID = "com.valvesoftware.Steam"
ROOTS = [
    HOME / ".local/share/Steam",
    HOME / ".steam/steam",
    HOME / ".steam/root",
    HOME / f".var/app/{FLATPAK_ID}/.local/share/Steam",
    HOME / f".var/app/{FLATPAK_ID}/data/Steam",
]
# Runtimes and tools that live in steamapps but are not games.
TOOL_IDS = {"228980", "1070560", "1391110", "1628350", "1493710"}
TOOL_PREFIXES = ("Proton ", "Steam Linux Runtime", "Steamworks Common", "Steam Controller Configs")
CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps"
NAMES_FILE = CACHE_DIR / "steam_names.json"  # appid -> name ("" = not a game: tools, runtimes)


class Steam(Store):
    id = "steam"
    name = "Steam"
    color = "#66c0f4"
    dlc_note = ("Steam installs the DLC you own by itself. AIO Launch can only see which DLC is installed; "
                "open the others in Steam to buy or install them.")
    external_installs = True
    login_kind = "external"

    def root(self):
        for r in ROOTS:
            if (r / "steamapps").is_dir() or (r / "config").is_dir():
                return r.resolve()
        return None

    def client(self):
        exe = shutil.which("steam")
        if exe:
            return [exe]
        if shutil.which("flatpak") and (HOME / f".var/app/{FLATPAK_ID}").is_dir():
            return ["flatpak", "run", FLATPAK_ID]
        return None

    def problem(self):
        return "" if self.client() else "Steam is not installed (sudo pacman -S steam)"

    def _users(self) -> dict:
        root = self.root()
        if not root:
            return {}
        return vdf.load(root / "config/loginusers.vdf").get("users", {})

    def _recent_user(self):
        users = self._users()
        for sid, u in users.items():
            if u.get("MostRecent") == "1" or u.get("mostrecent") == "1":
                return sid, u
        return next(iter(users.items()), (None, {}))

    def logged_in(self):
        return bool(self._users())

    def account(self):
        return self._recent_user()[1].get("PersonaName", "")

    def login_begin(self):
        client = self.client()
        if not client:
            raise StoreError(self.problem())
        return {"command": client}

    def library_dirs(self):
        root = self.root()
        if not root:
            return []
        dirs = {str(root)}
        folders = vdf.load(root / "steamapps/libraryfolders.vdf").get("libraryfolders", {})
        for entry in folders.values():
            if isinstance(entry, dict) and entry.get("path"):
                dirs.add(os.path.realpath(entry["path"]))
        return sorted(dirs)

    def _local_cover(self, appid):
        root = self.root()
        if not root:
            return ""
        cache = root / "appcache/librarycache"
        for cand in (cache / f"{appid}_library_600x900.jpg", cache / appid / "library_600x900.jpg"):
            if cand.is_file():
                return cand.as_uri()
        hits = glob.glob(str(cache / appid / "*" / "library_600x900.jpg"))
        return "file://" + hits[0] if hits else ""

    def _local_hero(self, appid):
        """Steam's own cached banner for a game, if the client has downloaded it."""
        root = self.root()
        if not root:
            return ""
        cache = root / "appcache/librarycache"
        for cand in (cache / f"{appid}_library_hero.jpg", cache / appid / "library_hero.jpg"):
            if cand.is_file():
                return cand.as_uri()
        hits = glob.glob(str(cache / appid / "*" / "library_hero.jpg"))
        return "file://" + hits[0] if hits else ""

    def _game(self, appid, title, installed=False, path=""):
        hero = self._local_hero(appid)
        return Game(
            store=self.id, id=appid, title=title, installed=installed, install_path=path,
            cover=self._local_cover(appid) or f"{CDN}/{appid}/library_600x900.jpg",
            cover_fallback=f"{CDN}/{appid}/header.jpg",
            extra={"store_heroes": [hero]} if hero else {},
        )

    def fetch(self):
        games = {}
        for lib in self.library_dirs():
            for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
                st = vdf.load(acf).get("AppState", {})
                appid, name = st.get("appid"), st.get("name", "")
                if not appid or appid in TOOL_IDS or name.startswith(TOOL_PREFIXES):
                    continue
                try:
                    done = int(st.get("StateFlags", "0")) & 4 != 0
                except ValueError:
                    done = False
                path = os.path.join(lib, "steamapps", "common", st.get("installdir", ""))
                games[appid] = self._game(appid, name or f"App {appid}", done, path)
                depots = st.get("InstalledDepots", {})
                games[appid].extra["dlc_installed"] = sorted(
                    {d["dlcappid"] for d in depots.values() if isinstance(d, dict) and d.get("dlcappid")})

        # Owned-but-not-installed games need the Web API (optional key in Settings). Without
        # a key, the games this account has played (on any PC) are listed from Steam's own files.
        key = settings.get("steam_api_key").strip()
        steamid = settings.get("steam_id").strip() or self._recent_user()[0]
        if not key:
            self._add_library(games, steamid)
        if key and steamid:
            try:
                r = requests.get(
                    "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/",
                    params={"key": key, "steamid": steamid, "include_appinfo": 1,
                            "include_played_free_games": 1, "format": "json"},
                    timeout=20,
                )
                r.raise_for_status()
                for g in r.json().get("response", {}).get("games", []):
                    appid = str(g["appid"])
                    if appid not in games and appid not in TOOL_IDS:
                        games[appid] = self._game(appid, g.get("name") or f"App {appid}")
            except (requests.RequestException, ValueError) as e:
                self._add_playtime(games)
                self._mark_hidden(games, steamid)
                raise PartialResult(list(games.values()), f"Steam Web API: {e}")
        self._add_playtime(games)
        self._mark_hidden(games, steamid)
        return list(games.values())

    def _mark_hidden(self, games, steamid):
        """Games hidden in Steam's library get extra["steam_hidden"]; AIO Launch then keeps
        them under "Hidden games" too. Steam syncs its collections through the cloud into
        userdata/<id>/config/cloudstorage/cloud-storage-namespace-1.json."""
        root = self.root()
        try:
            account = int(steamid) - 76561197960265728
        except (TypeError, ValueError):
            return
        path = root / "userdata" / str(account) / "config" / "cloudstorage" / "cloud-storage-namespace-1.json" if root else None
        try:
            entries = json.loads(path.read_text()) if path else []
        except (OSError, ValueError):
            return
        hidden = set()
        for key, entry in entries:
            if key == "user-collections.hidden" and isinstance(entry, dict) and not entry.get("is_deleted"):
                try:
                    hidden = {str(a) for a in json.loads(entry.get("value") or "{}").get("added", [])}
                except ValueError:
                    pass
        for appid, g in games.items():
            if appid in hidden:
                g.extra["steam_hidden"] = True

    def _local_apps(self, steamid):
        """The "apps" section of the account's localconfig.vdf (every app it has run, with playtime)."""
        root = self.root()
        try:
            account = int(steamid) - 76561197960265728
        except (TypeError, ValueError):
            return {}
        if not root:
            return {}
        node = vdf.load(root / "userdata" / str(account) / "config" / "localconfig.vdf")
        for name in ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps"):
            node = next((v for k, v in node.items() if k.lower() == name.lower() and isinstance(v, dict)), {})
        return node

    def _add_library(self, games, steamid):
        """The Library tab's games, without a Web API key: every app Steam's own cache
        (appinfo.vdf) has as a "game" for this account. Falls back to the played games when
        that cache cannot be read."""
        from .. import steamappinfo
        known = steamappinfo.apps(self.root()) if self.root() else {}
        if not known:
            self._add_played(games, steamid)
            return
        for appid, app in known.items():
            if app.get("type") == "game" and app.get("name") and appid not in games and appid not in TOOL_IDS:
                games[appid] = self._game(appid, app["name"])

    def _add_played(self, games, steamid):
        """Games this account has played, though not installed here: listed without a Web API key."""
        played = []
        for appid, app in self._local_apps(steamid).items():
            if appid in games or appid in TOOL_IDS or not isinstance(app, dict):
                continue
            try:
                if int(app.get("Playtime", 0) or 0) > 0 or int(app.get("LastPlayed", 0) or 0) > 0:
                    played.append(appid)
            except ValueError:
                pass
        for appid, name in _names(played).items():
            if name:
                games[appid] = self._game(appid, name)

    def _add_playtime(self, games):
        """Steam's own playtime record (localconfig.vdf of the signed-in account)."""
        root, steamid = self.root(), settings.get("steam_id").strip() or self._recent_user()[0]
        if not root or not steamid:
            return
        try:
            account = int(steamid) - 76561197960265728
        except ValueError:
            return
        conf = vdf.load(root / "userdata" / str(account) / "config" / "localconfig.vdf")
        node = conf
        for name in ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps"):
            node = next((v for k, v in node.items() if k.lower() == name.lower() and isinstance(v, dict)), {})
        for appid, app in node.items():
            g = games.get(appid)
            if g is None or not isinstance(app, dict):
                continue
            try:
                g.extra["steam_playtime"] = int(app.get("Playtime", 0)) * 60
                g.extra["steam_last_played"] = int(app.get("LastPlayed", 0))
            except ValueError:
                pass

    def dlcs(self, game):
        try:  # no country given: Steam answers in the player's own currency
            r = requests.get("https://store.steampowered.com/api/dlcforapp/",
                             params={"appid": game.id, "l": "english"}, timeout=20)
            r.raise_for_status()
            items = r.json().get("dlc") or []
        except (requests.RequestException, ValueError) as e:
            raise StoreError(f"Could not reach the Steam store ({type(e).__name__})")
        have = set(game.extra.get("dlc_installed") or [])
        client = bool(self.client())
        rows = []
        for d in items:
            did = str(d.get("id"))
            rows.append({"id": did, "title": d.get("name", did),
                         "status": "installed" if did in have else "missing",  # owned or not: Steam does not say
                         "image": d.get("header_image", ""), "price": _price(d.get("price_overview")),
                         # the Steam client opens on the DLC's page, where it can be bought or installed
                         "url": f"steam://store/{did}" if client else f"https://store.steampowered.com/app/{did}",
                         "canInstall": False})
        return rows

    def _url(self, url):
        client = self.client()
        if not client:
            raise StoreError(self.problem())
        return Command([*client, url])

    def install(self, game):
        return self._url(f"steam://install/{game.id}")

    def uninstall(self, game):
        return self._url(f"steam://uninstall/{game.id}")

    def launch(self, game):
        return self._url(f"steam://rungameid/{game.id}")


CURRENCY = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "BRL": "R$", "AUD": "A$", "CAD": "C$", "RUB": "₽"}


def _price(p):
    """ "€39.99", "€9.99 (-50%)", "Free", or "" when there is no price."""
    if not p:
        return ""
    final = p.get("final", 0) / 100
    if not final:
        return "Free"
    cur = p.get("currency", "")
    text = f"{CURRENCY.get(cur, '')}{final:.2f}" + ("" if cur in CURRENCY else f" {cur}")
    return text + (f" (-{p['discount_percent']}%)" if p.get("discount_percent") else "")


def _names(appids):
    """{appid: store name, or "" for things that are not games}. From Steam's store, 50 per
    request, remembered in steam_names.json (names do not change)."""
    cache = read_json(NAMES_FILE) or {}
    todo = [a for a in appids if a not in cache and str(a).isdigit()]
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        query = {"ids": [{"appid": int(a)} for a in chunk],
                 "context": {"country_code": "US", "language": "english"}, "data_request": {}}
        try:
            r = requests.get("https://api.steampowered.com/IStoreBrowseService/GetItems/v1",
                             params={"input_json": json.dumps(query)}, timeout=20)
            items = r.json().get("response", {}).get("store_items") or []
        except (requests.RequestException, ValueError):
            break  # offline: try again next refresh
        got = {str(it.get("appid")): it.get("name", "") for it in items
               if it.get("success") == 1 and it.get("type") == 0}
        for a in chunk:
            cache[a] = got.get(a, "")
    if todo:
        write_json(NAMES_FILE, cache)
    return {a: cache.get(a, "") for a in appids}

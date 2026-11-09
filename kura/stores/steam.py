"""Steam: reads the local client's libraries; installs and launches via steam:// URLs."""
import glob
import os
import shutil

import requests

from .. import vdf
from ..config import HOME, settings
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


class Steam(Store):
    id = "steam"
    name = "Steam"
    color = "#66c0f4"
    dlc_note = "Steam only tells Kura which DLC is installed; the rest is listed as available even if you own it."
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

    def _game(self, appid, title, installed=False, path=""):
        return Game(
            store=self.id, id=appid, title=title, installed=installed, install_path=path,
            cover=self._local_cover(appid) or f"{CDN}/{appid}/library_600x900.jpg",
            cover_fallback=f"{CDN}/{appid}/header.jpg",
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

        # Owned-but-not-installed games need the Web API (optional key in Settings).
        key = settings.get("steam_api_key").strip()
        steamid = settings.get("steam_id").strip() or self._recent_user()[0]
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
                raise PartialResult(list(games.values()), f"Steam Web API: {e}")
        return list(games.values())

    def dlcs(self, game):
        try:
            r = requests.get("https://store.steampowered.com/api/dlcforapp/",
                             params={"appid": game.id}, timeout=20)
            r.raise_for_status()
            items = r.json().get("dlc") or []
        except (requests.RequestException, ValueError) as e:
            raise StoreError(f"Could not reach the Steam store ({type(e).__name__})")
        have = set(game.extra.get("dlc_installed") or [])
        return [{"title": d.get("name", str(d.get("id"))),
                 "status": "installed" if str(d.get("id")) in have else "available",
                 "url": f"https://store.steampowered.com/app/{d.get('id')}"} for d in items]

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


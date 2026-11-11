"""Battle.net: runs Blizzard's own launcher under Proton and lists what it installed.

Blizzard has no public library API, so games are installed inside the
Battle.net app. Cornerplay installs/starts that app and reads its product database
to show each installed game as its own tile.
"""
import os
from pathlib import Path

from ..config import CACHE_DIR, CONFIG_DIR, read_json, write_json
from ..runner import StoreError, compat, prefix_path, wine_env, wrapper_argv
from .base import Command, Game, Store

SETUP_URL = "https://downloader.battle.net/download/getInstaller?os=win&installer=Battle.net-Setup.exe"
LAUNCHER_ID = "battlenet-app"
# The Battle.net app's own tile: a cover drawn for Cornerplay (art/battlenet-cover.png).
LAUNCHER_COVER = (Path(__file__).resolve().parent.parent / "art" / "battlenet-cover.png").as_uri()
UMU_ID = "umu-battlenet"

# product code (as in product.db) -> (title, code for `Battle.net.exe --exec="launch CODE"`)
PRODUCTS = {
    "wow": ("World of Warcraft", "WoW"),
    "wow_classic": ("World of Warcraft Classic", "WoWC"),
    "wow_classic_era": ("WoW Classic Era", "WoWC"),
    "d3": ("Diablo III", "D3"),
    "fenris": ("Diablo IV", "Fen"),
    "osi": ("Diablo II: Resurrected", "OSI"),
    "anbs": ("Diablo Immortal", "ANBS"),
    "pro": ("Overwatch 2", "Pro"),
    "hs_beta": ("Hearthstone", "WTCG"),
    "s1": ("StarCraft: Remastered", "S1"),
    "s2": ("StarCraft II", "S2"),
    "heroes": ("Heroes of the Storm", "Hero"),
    "w3": ("Warcraft III: Reforged", "W3"),
    "gryphon": ("Warcraft Rumble", "GRY"),
    "rtro": ("Blizzard Arcade Collection", "RTRO"),
    "wlby": ("Crash Bandicoot 4", "WLBY"),
    "viper": ("Call of Duty: Black Ops 4", "VIPR"),
    "odin": ("Call of Duty: Modern Warfare", "ODIN"),
    "lazarus": ("Call of Duty: MW2 Campaign Remastered", "LAZR"),
    "zeus": ("Call of Duty: Black Ops Cold War", "ZEUS"),
    "fore": ("Call of Duty: Vanguard", "FORE"),
    "auks": ("Call of Duty", "AUKS"),
}
# Blizzard titles that are also sold on Steam, so their box art can come from there.
STEAM_APPIDS = {"pro": 2357570, "fenris": 2344520, "osi": 2536520, "auks": 1938090,
                "odin": 2000950, "zeus": 1985810, "wlby": 1378990}
NOT_GAMES = {"agent", "bna", "battle.net", "battlenet"}

# Owned games, read from the Blizzard account site by a hidden page in the app (qml/BlizzardSync.qml)
# while the user is signed in there. Blizzard's titleId -> (title, launch code); from Playnite's table.
OWNED_FILE = CONFIG_DIR / "blizzard_owned.json"
TITLE_IDS = {
    5730135: ("World of Warcraft", "WoW"), 17459: ("Diablo III", "D3"), 21298: ("StarCraft II", "S2"),
    21297: ("StarCraft: Remastered", "S1"), 1465140039: ("Hearthstone", "WTCG"),
    1214607983: ("Heroes of the Storm", "Hero"), 5272175: ("Overwatch 2", "Pro"),
    1447645266: ("Call of Duty: Black Ops 4", "VIPR"), 1329875278: ("Call of Duty: Modern Warfare", "ODIN"),
    22323: ("Warcraft III: Reforged", "W3"), 1279351378: ("Call of Duty: MW2 Campaign Remastered", "LAZR"),
    1514493267: ("Call of Duty: Black Ops Cold War", "ZEUS"), 1464615513: ("Crash Bandicoot 4", "WLBY"),
    5198665: ("Diablo II: Resurrected", "OSI"), 1381257807: ("Blizzard Arcade Collection", "RTRO"),
    1179603525: ("Call of Duty: Vanguard", "FORE"), 1095647827: ("Diablo Immortal", "ANBS"),
    1096108883: ("Call of Duty", "AUKS"), 4613486: ("Diablo IV", "Fen"), 1146246220: ("Diablo", "D1"),
    5714258: ("Warcraft: Remastered", "W1R"), 5714514: ("Warcraft II: Remastered", "W2R"),
    1463898673: ("Warcraft: Orcs & Humans", "W1"), 1462911566: ("Warcraft II: Battle.net Edition", "W2"),
    4674137: ("Warcraft Rumble", "GRY"), 1095911763: ("Doom: The Dark Ages", "ARIS"),
    1396920146: ("Sea of Thieves", "SCOR"), 4280907: ("The Outer Worlds 2", "ARK"),
    1279414849: ("Tony Hawk's Pro Skater 3 + 4", "LBRA"), 1095849281: ("Avowed", "AQUA"),
}
# Launch code -> Steam app, for box art (same games as STEAM_APPIDS, keyed by launch code).
STEAM_BY_LAUNCH = {"Pro": 2357570, "Fen": 2344520, "OSI": 2536520, "AUKS": 1938090,
                   "ODIN": 2000950, "ZEUS": 1985810, "WLBY": 1378990}


def owned():
    """The owned-games list the account site last gave, or None when no Blizzard account is linked."""
    data = read_json(OWNED_FILE)
    return data if isinstance(data, dict) else None


def save_owned(raw):
    """Keep what the account site returned: {"games": [gameAccounts…], "classic": [classicGames…]}."""
    import time
    games = []
    for a in raw.get("games") or []:
        try:
            tid = int(a.get("titleId") or 0)
        except (TypeError, ValueError):
            tid = 0
        known = TITLE_IDS.get(tid)
        name = (known[0] if known else "") or (a.get("localizedGameName") or "").strip()
        if name:
            games.append({"title_id": tid, "title": name, "launch": known[1] if known else ""})
    for c in raw.get("classic") or []:
        name = (c.get("localizedGameName") or "").strip()
        if name:
            games.append({"title_id": 0, "title": name, "launch": "", "classic": True})
    write_json(OWNED_FILE, {"t": time.time(), "games": games, "expired": False})
    return games


def mark_expired():
    """Blizzard wants the password again: keep the list, remember it needs a new sign-in.
    Returns True the first time (so the user is told once, not at every start)."""
    data = owned()
    if not data or data.get("expired"):
        return False
    data["expired"] = True
    write_json(OWNED_FILE, data)
    return True


def forget_owned():
    try:
        OWNED_FILE.unlink()
    except OSError:
        pass


class BattleNet(Store):
    id = "battlenet"
    name = "Battle.net"
    color = "#148eff"
    tile = "#1673d9"  # its logo sits in white on a tile of this colour
    login_kind = "external"

    def problem(self):
        try:
            compat()
            return ""
        except StoreError as e:
            return str(e)

    def prefix(self):
        return prefix_path(self.id, "launcher")

    def launcher_exe(self):
        root = os.path.join(self.prefix(), "drive_c")
        for rel in ("Program Files (x86)/Battle.net/Battle.net.exe",
                    "Program Files/Battle.net/Battle.net.exe",
                    "Program Files (x86)/Battle.net/Battle.net Launcher.exe"):
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                return p
        return None

    def env(self):
        return wine_env(self.id, "launcher", UMU_ID)

    # Signing in to play happens inside the Battle.net app itself; the Blizzard account link
    # (Accounts > Battle.net > Link account) is only there to list the games you own.
    def logged_in(self):
        return bool(self.launcher_exe() or owned())

    def account(self):
        linked = owned()
        if linked and linked.get("expired"):
            return f"{len(linked.get('games') or [])} games owned · sign in again (Link account) to update the list"
        if linked:
            return f"Blizzard account linked · {len(linked.get('games') or [])} games owned"
        return "app installed; sign in inside it" if self.launcher_exe() else ""

    def login_begin(self):
        exe = self.launcher_exe()
        if not exe:
            raise StoreError("Install the Battle.net app first (its tile is in the library)")
        return {"command": [*wrapper_argv(gamescope=False), exe], "env": self.env()}

    def fetch(self):
        exe = self.launcher_exe()
        games = [Game(store=self.id, id=LAUNCHER_ID, title="Battle.net", installed=bool(exe),
                      install_path=os.path.dirname(exe) if exe else "",
                      cover=LAUNCHER_COVER, cover_fallback=LAUNCHER_COVER)]
        if exe:
            db = os.path.join(self.prefix(), "drive_c/ProgramData/Battle.net/Agent/product.db")
            for uid, code, path in read_product_db(db):
                if code.lower() in NOT_GAMES or uid.lower() in NOT_GAMES:
                    continue
                title, launch = PRODUCTS.get(code.lower()) or PRODUCTS.get(uid.lower()) or (
                    os.path.basename(path.replace("\\", "/").rstrip("/")) or uid, code)
                games.append(Game(store=self.id, id=uid, title=title, installed=True,
                                  install_path=path,
                                  extra={"launch": launch, **({"steam_appid": STEAM_APPIDS[code.lower()]}
                                                              if code.lower() in STEAM_APPIDS else {})}))
        # Games the Blizzard account owns but this PC has not installed.
        have = {(g.extra.get("launch") or "").lower() for g in games} | {g.title.lower() for g in games}
        for o in (owned() or {}).get("games") or []:
            launch, title = o.get("launch", ""), o.get("title", "")
            if (launch and launch.lower() in have) or title.lower() in have:
                continue
            have |= {launch.lower(), title.lower()} - {""}
            extra = {"launch": launch, "owned_only": True}
            if launch in STEAM_BY_LAUNCH:
                extra["steam_appid"] = STEAM_BY_LAUNCH[launch]
            games.append(Game(store=self.id, id="owned-" + (launch or str(o.get("title_id") or title)),
                              title=title, installed=False, extra=extra))
        return games

    def install(self, game):
        if game.id != LAUNCHER_ID:
            exe = self.launcher_exe()
            if not exe:
                raise StoreError("Install the Battle.net app first (its tile is in the library), then install "
                                 + game.title + " from there")
            # Opens the Battle.net app on this game's page, where its Install button is.
            argv = [*wrapper_argv(gamescope=False), exe]
            if game.extra.get("launch"):
                argv.append("--game=" + game.extra["launch"].lower())
            return Command(argv, env=self.env(), cwd=os.path.dirname(exe))
        setup = str(CACHE_DIR / "Battle.net-Setup.exe")
        script = 'curl -fL --retry 3 -o "$1" "$2" && shift 2 && exec "$@"'
        return Command(["sh", "-c", script, "cornerplay", setup, SETUP_URL, *wrapper_argv(gamescope=False), setup],
                       env=self.env())

    def uninstall(self, game):
        raise StoreError("Uninstall Battle.net games from inside the Battle.net app")

    def launch(self, game):
        exe = self.launcher_exe()
        if not exe:
            raise StoreError("The Battle.net app is not installed yet")
        argv = [*wrapper_argv(gamescope=False), exe]
        if game.id != LAUNCHER_ID:
            argv.append("--exec=launch " + game.extra.get("launch", game.id))
        return Command(argv, env=self.env(), cwd=os.path.dirname(exe))


# --- product.db ---------------------------------------------------------
# A protobuf file: ProductDb { repeated ProductInstall = 1 }, where
# ProductInstall { uid = 1; product_code = 2; settings = 3 { install_path = 1 } }.

def _fields(buf):
    i, n = 0, len(buf)
    while i < n:
        tag, i = _varint(buf, i)
        num, wire = tag >> 3, tag & 7
        if wire == 0:
            val, i = _varint(buf, i)
        elif wire == 2:
            ln, i = _varint(buf, i)
            val, i = buf[i:i + ln], i + ln
        elif wire == 1:
            val, i = buf[i:i + 8], i + 8
        elif wire == 5:
            val, i = buf[i:i + 4], i + 4
        else:
            return
        yield num, wire, val


def _varint(buf, i):
    out = shift = 0
    while True:
        b = buf[i]
        i += 1
        out |= (b & 0x7F) << shift
        if not b & 0x80:
            return out, i
        shift += 7


def read_product_db(path):
    """Yield (uid, product_code, install_path) for every installed product."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []
    out = []
    try:
        for num, wire, val in _fields(data):
            if num != 1 or wire != 2:
                continue
            uid = code = install = ""
            for n2, w2, v2 in _fields(val):
                if w2 != 2:
                    continue
                if n2 == 1:
                    uid = v2.decode("utf-8", "replace")
                elif n2 == 2:
                    code = v2.decode("utf-8", "replace")
                elif n2 == 3:
                    for n3, w3, v3 in _fields(v2):
                        if n3 == 1 and w3 == 2:
                            install = v3.decode("utf-8", "replace")
            if uid:
                out.append((uid, code or uid, install))
    except (IndexError, ValueError):
        pass
    return out

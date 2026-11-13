"""Paths, settings and backend-tool discovery."""
import json
import os
import shutil
from pathlib import Path

APP = "cornerplay"
HOME = Path.home()
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / APP
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / APP
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / APP
BIN_DIR = DATA_DIR / "bin"
LOG_DIR = CACHE_DIR / "logs"
XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))

LANGUAGES = {"en": "English", "ro": "Română"}  # interface languages: cornerplay/i18n (English is the source)
OLD_NAMES = ("aiolaunch", "kura")  # earlier names of the app, newest first


def _migrate_from_kura():
    """The app was called Kura, then AIO Launch: move the newest old folders over once,
    and keep games where they are."""
    import shutil
    moved_config = False
    for new in (CONFIG_DIR, DATA_DIR, CACHE_DIR):
        for name in OLD_NAMES:
            old = new.with_name(name)
            if old.is_dir() and not new.exists():
                shutil.move(str(old), str(new))
                moved_config |= new == CONFIG_DIR
    old_games = next((HOME / "Games" / n for n in OLD_NAMES if (HOME / "Games" / n).is_dir()), None)
    settings_file = CONFIG_DIR / "settings.json"
    if old_games:
        data = read_json(settings_file, {}) or {}
        if "games_dir" not in data:
            data["games_dir"] = str(old_games)  # installed games and prefixes stay put
            write_json(settings_file, data)



DEFAULTS = {
    "library_dirs": [],  # folders games were moved to (Storage > Move); GOG installs are found there too
    "update_check": True,  # look for a new Cornerplay release once a day
    "tray_while_playing": True,  # the window steps aside into the tray while a game runs (tray.py)
    "close_to_tray": False,      # closing the window keeps Cornerplay running in the tray
    "start_with_pc": False,      # an autostart entry that opens Cornerplay in the tray
    "stream_pc": "",             # the gaming PC Moonlight streams from (its name or address; stream.py)
    "stream_mac": "",            # its network card's MAC address, to wake it (Wake-on-LAN)
    "profiles": [],        # people using this PC (personal.py); empty: one profile, "Me"
    "profile": "",
    "sync_dir": "",        # a folder another tool syncs between PCs; Cornerplay keeps personal data there
    "machine_id": "",
    "download_limit": 0.0,    # MB/s for Epic / GOG / Amazon downloads; 0 = as fast as it goes (throttle.py)
    "auto_update": False,     # update Epic / GOG / Amazon games overnight (mains power, not metered)
    "auto_update_from": 2,
    "auto_update_to": 6,
    "gog_native": True,    # GOG: install the Linux version when the game has one (no Proton)
    "view": "grid",            # main window: "grid" of covers or "list" (a table)
    "home_collapsed": ["free"],  # home sections folded away: "banner", "continue", "free" (Free on Epic starts as one line)
    "epic_free_hidden_until": 0,  # Free on Epic hidden until the current offers end
    "home_order": ["continue", "free"],
    "smart_lists": [],         # saved filters shown as lists in the sidebar: [{"name", "store", "installed", "tags"}]
    "ui_scale": 0.0,           # interface size: 0 = automatic, else 1.0 / 1.15 / 1.3 / 1.5 / 2.0 (after a restart)
    "save_backups": True,    # zip a game's saves before each start (savebackup.py)
    "sync_saves": True,      # with a sync folder: share each game's latest saves between your PCs (savebackup.share)
    "backup_keep": 5,        # backups kept per game
    "card_shadow": "soft",   # cover shadows: "none", "soft", "deep"
    "evening_warmth": True,  # surfaces turn a little warmer in the evening and at night
    "wallpaper_backdrop": True,  # Follow wallpaper: the wallpaper, blurred, behind the main window
    "bg_mode": "",           # behind the library: "" (plain), "picture" (bg_picture), "gradient" (slowly moving), "game" (the last played game's art)
    "bg_picture": "",
    "shelf_backgrounds": {}, # a collection's own picture: {"c:<name>": path}
    "tv_reflection": True,   # TV mode: covers reflected on the shelf below
    "tv_intro": False,       # TV mode: a short start-up animation and chime
    "tv_animated": True,   # animated covers and banners in TV mode (SteamGridDB key; only when plugged in)
    "shader_warmup": True,  # record games' shaders (Steam's Fossilize) and build them again after a driver update
    "shader_cache": True,  # keep each game's shader cache (DXVK, VKD3D, Mesa, NVIDIA) and let it grow
    "perf": "",            # default performance profile: "", "battery", "balanced", "quality"
    "show_fps": False,
    "perf_log": False,     # MangoHud logs each session; a game's page shows FPS, stutters and temperatures (perf.py)
    "games_dir": str(HOME / "Games" / APP),
    "proton": "GE-Proton",  # umu PROTONPATH: "GE-Proton", a path, or "" for UMU-Proton
    "mangohud": False,
    "gamescope": "",           # run games inside gamescope: "", "fullscreen" (at the screen's resolution) or "fsr" (upscaled)
    "gamescope_hdr": False,    # gamescope's HDR output (needs an HDR screen and a compositor that passes it on)
    "screen_size": [],         # the main screen in pixels, noted at start-up (gamescope's output size)
    "gamemode": False,
    "steam_api_key": "",
    "steam_id": "",
    "steamgriddb_key": "",
    "language": "",             # interface language: "" = the system's, "en", "ro" (after a restart)
    "rom_dirs": [],             # folders with ROMs for Retro games (stores/retro.py)
    "screenshot_dirs": [],      # more folders to find your screenshots in (screenshots.py)
    "wishlist_sales": True,
    "itad_key": "",             # IsThereAnyDeal API key: the best price on any store for the wishlist (itad.py)
    "deal_alert_cut": 50,       # announce a wishlist deal at least this much off (or a new lowest price)
    "store_country": "",        # two letters for store prices (AU, RO, ...); empty: your GOG account's, else the system's     # "On sale from your wishlist" on the home page (Steam and GOG wishlists)
    "discord_presence": False,  # "Playing <game>" on Discord for Epic / GOG / Amazon games (discord.py)
    "discord_app_id": "",       # the Application ID of a Discord application named "Cornerplay"
    "igdb_client_id": "",      # a Twitch developer app, for IGDB's time-to-beat (timetobeat.py)
    "igdb_client_secret": "",
    "env": "",                 # extra environment for every game: KEY=VALUE KEY2=VALUE2
    "theme_auto": "",           # "" (as chosen), "system" (follow the desktop's light/dark), "sunset" (dark from 7 pm)
    "theme_light": "Paper",     # the light and dark presets for theme_auto
    "theme_dark": "Cornerplay",
    "theme_mode": "Cornerplay",  # "Cornerplay" (amber, the signature look), "ryoku" (wallpaper), a preset, or "custom"
    "theme_bg": "#141218",
    "theme_accent": "#d2bcfd",
    "card_size": 196,
    "seasonal": True,          # a small seasonal touch on empty screens and the splash (Seasonal.qml)
    "density": "comfortable",  # space between covers: "compact", "comfortable", "roomy"
    "title_font": "",          # game titles: "" (rounded, Nunito), "condensed", "serif", "pixel"
    "card_radius": 14,
    "show_badges": True,
    "show_titles": False,
    "dim_uninstalled": True,
    "merge_duplicates": True,
    "cloud_saves": True,
    "steam_games": False,      # keep installed games in Steam (Game Mode) automatically
    "performance": "auto",     # "auto", "light" or "full"
    "sort": "name",            # library order: "name", "recent" or "playtime"
    "tv_trailers": True,       # TV mode plays the focused game's trailer (muted) after a moment
    "hover_trailers": True,    # the library plays a cover's trailer (muted) inside it while it is pointed at
    "tv_sounds": False,        # TV mode makes soft clicks when moving and choosing
    "tv_rumble": False,        # TV mode: the controller buzzes lightly when moving and choosing
    "tv_music": False,         # TV mode: a calm, original ambient loop (fades out for trailers and games)
    "tv_screensaver": 3,       # TV mode: minutes without input before the slideshow of your games (0 = never)
    "tv_who": True,            # TV mode: "Who's playing?" at start when there are several people
    "show_protondb": True,     # ProtonDB rating badge on covers
}

# Where Heroic keeps its bundled copies of legendary / gogdl / nile.
_HEROIC_BIN_DIRS = [
    "/opt/Heroic/resources/app.asar.unpacked/build/bin/x64/linux",
    "/opt/heroic/resources/app.asar.unpacked/build/bin/x64/linux",
    "/usr/lib/heroic/resources/app.asar.unpacked/build/bin/x64/linux",
]

BACKEND_REPOS = {"legendary": "Heroic-Games-Launcher/legendary", "gogdl": "Heroic-Games-Launcher/heroic-gogdl",
                 "nile": "imLinguin/nile"}


class Settings:
    def __init__(self):
        self.path = CONFIG_DIR / "settings.json"
        self.data = dict(DEFAULTS)
        try:
            self.data.update(json.loads(self.path.read_text()))
        except (OSError, ValueError):
            pass

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    listeners: list = []  # called after every change (the app drops what it worked out from settings)

    def set(self, key, value):
        self.data[key] = value
        write_private(self.path, json.dumps(self.data, indent=2))
        for fn in list(self.listeners):
            fn()

    @property
    def games_dir(self) -> Path:
        return Path(os.path.expanduser(self.get("games_dir")))




def find_tool(name: str) -> str | None:
    """Locate a backend binary: PATH, Cornerplay's own bin dir, then Heroic's bundle."""
    found = shutil.which(name)
    if found:
        return found
    from .host import BUNDLED_BIN
    for d in [str(BIN_DIR), BUNDLED_BIN, *_HEROIC_BIN_DIRS]:
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def write_private(path, text: str):
    """Write a file only this user can read (settings with API keys, sign-in tokens), atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o600)  # an older .tmp may have been made with wider rights
    tmp.replace(path)


def _lock_down():
    """Cornerplay's settings folder holds API keys and store sign-in tokens: only this user
    may open it (folders made by earlier versions were readable by everyone on the PC). The
    same for the sign-ins Cornerplay makes through legendary (Epic) and nile (Amazon): both
    leave their tokens readable by every account on the PC."""
    for f in (XDG_CONFIG / "legendary" / "user.json",):
        try:
            if f.stat().st_mode & 0o077:
                f.chmod(0o600)
        except OSError:
            pass
    for d in (CONFIG_DIR, DATA_DIR, XDG_CONFIG / "legendary", XDG_CONFIG / "nile"):
        try:
            if d.stat().st_mode & 0o077:
                d.chmod(0o700)
        except OSError:
            pass
    for f in CONFIG_DIR.glob("*.json"):
        try:
            if f.stat().st_mode & 0o077:
                f.chmod(0o600)
        except OSError:
            pass


class GameOptions:
    """Per-game overrides, keyed "store:id". A missing key means "use the default"."""
    KEYS = ("proton", "mangohud", "gamemode", "env", "args", "cover", "prefer", "cloud_saves", "hidden", "collections",
            "status", "rating", "note", "perf", "show_fps", "platform", "gamescope", "gamescope_hdr")

    def __init__(self):
        self.path = CONFIG_DIR / "games.json"
        self.data = read_json(self.path, {}) or {}

    def get(self, key) -> dict:
        return dict(self.data.get(key, {}))

    _EMPTY = {}

    def peek(self, key) -> dict:
        """The entry itself, for reading only (no copy: the library asks this thousands of times)."""
        return self.data.get(key) or self._EMPTY

    def set(self, key, name, value):
        if name not in self.KEYS:
            return
        entry = self.data.setdefault(key, {})
        if value in ("", None, "default"):
            entry.pop(name, None)
        else:
            entry[name] = value
        if not entry:
            self.data.pop(key, None)
        write_private(self.path, json.dumps(self.data))




_migrate_from_kura()
for _d in (CONFIG_DIR, DATA_DIR, CACHE_DIR, BIN_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)
_lock_down()
settings = Settings()
game_options = GameOptions()

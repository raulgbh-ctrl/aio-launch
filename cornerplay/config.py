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
    "profiles": [],        # people using this PC (personal.py); empty: one profile, "Me"
    "profile": "",
    "sync_dir": "",        # a folder another tool syncs between PCs; Cornerplay keeps personal data there
    "machine_id": "",
    "auto_update": False,     # update Epic / GOG / Amazon games overnight (mains power, not metered)
    "auto_update_from": 2,
    "auto_update_to": 6,
    "gog_native": True,    # GOG: install the Linux version when the game has one (no Proton)
    "view": "grid",            # main window: "grid" of covers or "list" (a table)
    "home_collapsed": ["free"],  # home sections folded away: "banner", "continue", "free" (Free on Epic starts as one line)
    "epic_free_hidden_until": 0,  # Free on Epic hidden until the current offers end
    "home_order": ["continue", "free"],
    "ui_scale": 0.0,           # interface size: 0 = automatic, else 1.0 / 1.15 / 1.3 / 1.5 / 2.0 (after a restart)
    "card_shadow": "soft",   # cover shadows: "none", "soft", "deep"
    "tv_reflection": True,   # TV mode: covers reflected on the shelf below
    "tv_intro": False,       # TV mode: a short start-up animation and chime
    "tv_animated": True,   # animated covers and banners in TV mode (SteamGridDB key; only when plugged in)
    "shader_cache": True,  # keep each game's shader cache (DXVK, VKD3D, Mesa, NVIDIA) and let it grow
    "perf": "",            # default performance profile: "", "battery", "balanced", "quality"
    "show_fps": False,
    "games_dir": str(HOME / "Games" / APP),
    "proton": "GE-Proton",  # umu PROTONPATH: "GE-Proton", a path, or "" for UMU-Proton
    "mangohud": False,
    "gamemode": False,
    "steam_api_key": "",
    "steam_id": "",
    "steamgriddb_key": "",
    "env": "",                 # extra environment for every game: KEY=VALUE KEY2=VALUE2
    "theme_mode": "Cornerplay",  # "Cornerplay" (amber, the signature look), "ryoku" (wallpaper), a preset, or "custom"
    "theme_bg": "#141218",
    "theme_accent": "#d2bcfd",
    "card_size": 196,
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
    "tv_sounds": False,        # TV mode makes soft clicks when moving and choosing
    "show_protondb": True,     # ProtonDB rating badge on covers
}

# Where Heroic keeps its bundled copies of legendary / gogdl / nile.
_HEROIC_BIN_DIRS = [
    "/opt/Heroic/resources/app.asar.unpacked/build/bin/x64/linux",
    "/opt/heroic/resources/app.asar.unpacked/build/bin/x64/linux",
    "/usr/lib/heroic/resources/app.asar.unpacked/build/bin/x64/linux",
]

BACKEND_URLS = {
    "legendary": "https://github.com/Heroic-Games-Launcher/legendary/releases/latest/download/legendary_linux_x86_64",
    "gogdl": "https://github.com/Heroic-Games-Launcher/heroic-gogdl/releases/latest/download/gogdl_linux_x86_64",
    "nile": "https://github.com/imLinguin/nile/releases/latest/download/nile_linux_x86_64",
}


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

    def set(self, key, value):
        self.data[key] = value
        self.path.write_text(json.dumps(self.data, indent=2))

    @property
    def games_dir(self) -> Path:
        return Path(os.path.expanduser(self.get("games_dir")))




def find_tool(name: str) -> str | None:
    """Locate a backend binary: PATH, Cornerplay's own bin dir, then Heroic's bundle."""
    found = shutil.which(name)
    if found:
        return found
    for d in [str(BIN_DIR), *_HEROIC_BIN_DIRS]:
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


class GameOptions:
    """Per-game overrides, keyed "store:id". A missing key means "use the default"."""
    KEYS = ("proton", "mangohud", "gamemode", "env", "args", "cover", "prefer", "cloud_saves", "hidden", "collections",
            "status", "rating", "note", "perf", "show_fps", "platform")

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
        write_json(self.path, self.data)




_migrate_from_kura()
for _d in (CONFIG_DIR, DATA_DIR, CACHE_DIR, BIN_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)
settings = Settings()
game_options = GameOptions()

"""Qt side of Cornerplay: the library model, background jobs and the object QML talks to."""
import json
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QByteArray, QFileSystemWatcher, QModelIndex, QCoreApplication, QObject,
                            QProcess, QProcessEnvironment, QSortFilterProxyModel, Qt, QTimer, QUrl,
                            Property, Signal, Slot)
from PySide6.QtGui import QDesktopServices, QGuiApplication

import shlex

import sys

from . import achievements, backup, search, couch, host, hostimport, statsdata, steamrun, wishlist, health, savebackup, importer, personal, problems, storage, updates, covers, details, epicfree, shelves, gamecolour, playtime, protondb, steamcompat, proton, runner, saves, session, steamgames, steamshortcut, theme as themes
from .config import CACHE_DIR, DEFAULTS, LANGUAGES, LOG_DIR, game_options, read_json, settings, write_json
from .net import redact
from .runner import StoreError
from .stores.base import Command, Game, PartialResult, run as store_run
from .stores import battlenet
from .stores.battlenet import LAUNCHER_COVER
from .stores import custom as custom_games
from .stores import all_stores

LIBRARY_CACHE = CACHE_DIR / "library.json"
PALETTE = themes.RYOKU_PALETTE
PROGRESS = re.compile(r"Progress:\s*([\d.]+)")
# Download speed and time left, as legendary / gogdl / nile print them ("+ Download - 25.3 MiB/s",
# "ETA: 00:04:10"); when a tool prints neither, the time left is worked out from the progress.
SPEED = re.compile(r"([\d.]+)\s*(B|KiB|MiB|GiB|kB|KB|MB|GB)/s", re.I)
ETA = re.compile(r"ETA:\s*(\d+):(\d\d):(\d\d)")
_UNITS = {"b": 1, "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "kb": 1000, "mb": 1000 ** 2, "gb": 1000 ** 3}


def job_detail(job):
    """'12.3 MB/s · 4 min left' (either part only when known), or ''."""
    if not job or job.get("kind") in ("queued", "paused"):
        return ""
    parts = []
    speed = job.get("speed") or 0
    if speed > 0:
        parts.append(f"{speed / 1e6:.1f} MB/s" if speed >= 1e6 else f"{speed / 1e3:.0f} kB/s")
    eta = job.get("eta")
    if eta is not None and job.get("etaAt"):
        left = max(0, eta - (time.monotonic() - job["etaAt"]))
        parts.append("under a minute left" if left < 60 else
                     f"{round(left / 60)} min left" if left < 3600 else
                     f"{int(left // 3600)} h {round(left % 3600 / 60)} min left")
    return "  \u00B7  ".join(parts)

ROLES = ["key", "store", "storeName", "storeColor", "title", "cover", "coverFallback",
         "installed", "job", "progress", "external", "installPath", "copies",
         "update", "playtime", "lastPlayed", "covers", "heroes", "logos", "protondb", "favourite",
         "status", "rating", "sizeBytes", "achieved"]
GROUP_ROLES = ("copies", "playtime", "lastPlayed", "favourite", "status", "rating")
SORTS = ("name", "recent", "playtime", "rating", "size")
RECENT_ROW = 8  # games in the "Continue playing" row  # worked out over every store's copy of a game


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _t(text):
    """Interface text from Python, in the interface language (cornerplay/i18n)."""
    return QCoreApplication.translate("app", text)


def _translatable_names():
    """Never called: lists names that reach _t() through variables, so lupdate finds them."""
    return (QCoreApplication.translate("app", "Playing"),
            QCoreApplication.translate("app", "Want to play"),
            QCoreApplication.translate("app", "Finished"),
            QCoreApplication.translate("app", "Dropped"),
            QCoreApplication.translate("app", "Continue playing"),
            QCoreApplication.translate("app", "Favourites"),
            QCoreApplication.translate("app", "Recently added"),
            QCoreApplication.translate("app", "Library"))


def _short_date(stamp, with_year=False):
    """ "21 Oct" in English whatever the system language, to match the rest of the app."""
    t = time.localtime(stamp)
    return f"{t.tm_mday} {MONTHS[t.tm_mon - 1]}" + (f" {t.tm_year}" if with_year else "")


STEAM_ART = re.compile(r"/steam/apps/(\d+)/")


def _unique(urls):
    out = []
    for u in urls:
        if u and u not in out:
            out.append(u)
    return out


def _covers(g):
    """Portrait cover sources, best first; the UI moves to the next when one fails to load."""
    return _unique([_cover(g), *(g.extra.get("covers") or []), g.cover_fallback])


def _appid(g):
    """The game's Steam app id, if known ("" if not)."""
    appid = g.id if g.store == "steam" else str(g.extra.get("steam_appid") or "")
    if not appid:  # covers that came from Steam's store carry the id in their URL
        m = STEAM_ART.search(_cover(g) or "")
        appid = m.group(1) if m else ""
    return appid if appid.isdigit() else ""


def _heroes(g):
    """Wide banner sources, best first (see covers.add_backup_art)."""
    heroes = list(g.extra.get("heroes") or g.extra.get("store_heroes") or [])
    if _appid(g):
        heroes.append(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{_appid(g)}/library_hero.jpg")
    return _unique(heroes + [g.cover_fallback])


def _logos(g):
    """Transparent game logo sources, best first; the UI shows the title when none loads."""
    logos = list(g.extra.get("logos") or g.extra.get("store_logos") or [])
    if _appid(g):
        logos.append(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{_appid(g)}/logo.png")
    return _unique(logos)


def _cover(g):
    custom = game_options.get(g.key).get("cover", "")
    if custom.startswith("/"):
        return "file://" + custom
    return custom or g.extra.get("current_cover") or g.cover


def _job(m, g):
    return m.jobs.get(g.key) or {}


_FIELDS = {
    "key": lambda m, g: g.key,
    "store": lambda m, g: g.store,
    "storeName": lambda m, g: m.stores[g.store].name,
    "storeColor": lambda m, g: m.stores[g.store].color,
    "title": lambda m, g: g.title,
    "cover": lambda m, g: _cover(g),
    "coverFallback": lambda m, g: g.cover_fallback,
    "favourite": lambda m, g: shelves.FAV in shelves.ids_of(g.key),
    "status": lambda m, g: shelves.meta([g], "status"),
    "rating": lambda m, g: int(shelves.meta([g], "rating") or 0),
    "sizeBytes": lambda m, g: float(g.extra.get("size", 0) or 0) if g.installed else 0.0,
    "installed": lambda m, g: g.installed,
    "job": lambda m, g: _job(m, g).get("kind", ""),
    "progress": lambda m, g: _job(m, g).get("progress", 0.0),
    "external": lambda m, g: m.stores[g.store].external_installs,
    "installPath": lambda m, g: g.install_path,
    "copies": lambda m, g: 1,
    "update": lambda m, g: bool(g.installed and g.extra.get("update")),
    "achieved": lambda m, g: achievements.progress(g.id) if g.store == "steam"
                             else achievements.progress("gog:" + g.id) if g.store == "gog" else -1.0,
    "playtime": lambda m, g: playtime.of(g, m.played)[0],
    "lastPlayed": lambda m, g: playtime.of(g, m.played)[1],
    "covers": lambda m, g: _covers(g),
    "heroes": lambda m, g: _heroes(g),
    "logos": lambda m, g: _logos(g),
    # ProtonDB tier ("platinum" … "borked", "" if unknown). Steam games too: most are Windows builds.
    "protondb": lambda m, g: protondb.rating(_appid(g)).get("tier", "") if g.id != "battlenet-app" else "",
}
assert set(_FIELDS) == set(ROLES)


class LibraryModel(QAbstractListModel):
    """One row per game; copies of the same game on several stores share a row."""

    def __init__(self, stores):
        super().__init__()
        self.stores = stores
        self.games: list[Game] = []
        self.groups: list[list[Game]] = []
        self.jobs: dict[str, dict] = {}  # key -> {"kind": str, "progress": float}
        self.focus_store = ""            # the sidebar's store filter decides which copy is shown
        self.played = playtime.load()    # Cornerplay's own playtime record
        self.generation = 0              # bumped on every change, so cached sort keys know they are stale
        self._gids = {}                  # id(group) -> group id, worked out once per regroup
        self._reps = {}                  # id(group) -> the copy shown, for the current generation
        self._reps_gen = -1

    def roleNames(self):
        return {Qt.UserRole + i: QByteArray(r.encode()) for i, r in enumerate(ROLES)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.groups)

    # --- grouping --------------------------------------------------------
    def group_id(self, g: Game) -> str:
        if settings.get("merge_duplicates") and g.id != "battlenet-app":
            n = covers.norm(g.title)
            if n:
                return "group:" + n
        return g.key

    def regroup(self):
        order = list(self.stores)
        groups: dict[str, list] = {}
        for g in self.games:
            groups.setdefault(self.group_id(g), []).append(g)
        for copies in groups.values():
            copies.sort(key=lambda g: order.index(g.store))
        self.groups = list(groups.values())
        self._gids = {id(grp): gid for gid, grp in groups.items()}
        self._by_key = {g.key: g for g in self.games}
        self._group_by_key = {g.key: grp for grp in self.groups for g in grp}
        self._reps_gen = -1

    def is_hidden(self, group):
        """Hidden in Cornerplay, or hidden in Steam when every copy is a hidden Steam copy
        (a copy on another store keeps it visible). Unhiding in Cornerplay overrides Steam."""
        opts = [game_options.peek(g.key).get("hidden") for g in group]
        if any(o is True for o in opts):
            return True
        if any(o is False for o in opts):
            return False
        return bool(group) and all(g.extra.get("steam_hidden") for g in group)

    def group_of(self, key):
        return self._group_by_key.get(key, []) if hasattr(self, "_group_by_key") else []

    def rep(self, group):
        """The copy a row stands for: focused store, running job, user's pick, installed.
        Remembered until the library next changes (every change bumps the generation)."""
        if len(group) == 1:
            return group[0]
        if self._reps_gen != self.generation:
            self._reps, self._reps_gen = {}, self.generation
        hit = self._reps.get(id(group))
        if hit is None:
            gid = self._gids.get(id(group)) or self.group_id(group[0])
            prefer = game_options.peek(gid).get("prefer", "")
            hit = min(group, key=lambda g: (g.store != self.focus_store, g.key not in self.jobs,
                                            g.key != prefer, not g.installed))
            self._reps[id(group)] = hit
        return hit

    # --- data ------------------------------------------------------------
    def value(self, g: Game, role: str):
        """One field of one game; only the asked-for field is worked out (the grid asks a lot)."""
        return _FIELDS[role](self, g)

    def group_value(self, group, role):
        """Row-level values: a game owned on several stores counts the time played on each."""
        if role == "copies":
            return len(group)
        if role == "favourite":
            return shelves.in_group(group, shelves.FAV)
        if role == "status":
            return shelves.meta(group, "status")
        if role == "rating":
            return int(shelves.meta(group, "rating") or 0)
        times = [playtime.of(g, self.played) for g in group]
        return sum(t[0] for t in times) if role == "playtime" else max(t[1] for t in times)

    # Plain ints: arithmetic on Qt's enum objects costs more than the rest of data() put together.
    _USER = int(Qt.UserRole.value) if hasattr(Qt.UserRole, "value") else int(Qt.UserRole)
    _DISPLAY = int(Qt.DisplayRole.value) if hasattr(Qt.DisplayRole, "value") else int(Qt.DisplayRole)
    _NROLES = len(ROLES)
    _GROUP = frozenset(GROUP_ROLES)

    def data(self, index, role=0):
        row = index.row()
        if row < 0 or row >= len(self.groups):
            return None
        role = role.value if hasattr(role, "value") else role
        group = self.groups[row]
        g = self.rep(group)
        if role == self._DISPLAY:
            return g.title
        i = role - self._USER
        if not 0 <= i < self._NROLES:
            return None
        name = ROLES[i]
        return self.group_value(group, name) if name in self._GROUP else _FIELDS[name](self, g)

    def find(self, key):
        return self._by_key.get(key) if hasattr(self, "_by_key") else None

    def as_dict(self, key):
        g = self.find(key)
        if not g:
            return {}
        d = {r: self.value(g, r) for r in ROLES}
        group = self.group_of(key)
        d["copies"] = [{"key": c.key, "storeName": self.stores[c.store].name,
                        "storeColor": self.stores[c.store].color, "installed": c.installed}
                       for c in group] if len(group) > 1 else []
        d["hasDlc"] = g.store in ("steam", "epic", "gog")
        d["jobDetail"] = job_detail(self.jobs.get(key))
        d["hidden"] = self.is_hidden(group or [g])
        pdb = protondb.rating(_appid(g)) if g.id != "battlenet-app" else {}
        d["protondbTrending"] = pdb.get("trending", "")
        d["protondbReports"] = pdb.get("reports", 0)
        d["steamAppId"] = _appid(g)
        d["favourite"] = shelves.in_group(group or [g], shelves.FAV)
        d["collections"] = [c for c in shelves.names() if shelves.in_group(group or [g], c)]
        d["linuxVersion"] = bool(g.extra.get("linux"))   # GOG: the game has a Linux version
        d["platform"] = g.extra.get("platform", "")      # installed as "linux" or "windows"
        d["status"] = shelves.meta(group or [g], "status")
        d["rating"] = int(shelves.meta(group or [g], "rating") or 0)
        d["note"] = shelves.meta(group or [g], "note")
        d["playtime"] = self.group_value(group or [g], "playtime")
        d["lastPlayed"] = self.group_value(group or [g], "lastPlayed")
        return d

    def set_games(self, games):
        self.generation += 1
        self.beginResetModel()
        self.games = list(games)
        self.regroup()
        self.endResetModel()

    def replace_store(self, store_id, games):
        """Put a store's fresh list in. Returns False (and changes nothing) when it is the same
        as what is shown: at start-up the library comes from the cache and most stores send
        back exactly that, and each full reset re-sorts and re-filters the whole library on the
        main thread (it froze the start-up animation)."""
        games = list(games)
        old = [g.to_dict() for g in self.games if g.store == store_id]
        if old == [g.to_dict() for g in games]:
            return False
        self.set_games([g for g in self.games if g.store != store_id] + games)
        return True

    def touch(self, key=None):
        self.generation += 1
        if key is None:
            if self.groups:
                self.dataChanged.emit(self.index(0), self.index(len(self.groups) - 1))
            return
        for row, group in enumerate(self.groups):
            if any(g.key == key for g in group):
                idx = self.index(row)
                self.dataChanged.emit(idx, idx)
                return


class LibraryProxy(QSortFilterProxyModel):
    filterChanged = Signal()

    def __init__(self, model):
        super().__init__()
        self._store, self._installed, self._search, self._hidden = "", False, "", False
        self._shelf = ""  # "", "fav", "c:<name>", "playing" (played, most recent first), "added" (newest first)
        self._tags = []   # filter chips: "unplayed", "linux", "controller", "protondb", "genre:<name>"
        self._sort = settings.get("sort") if settings.get("sort") in SORTS else "name"
        self._keys, self._keys_gen = {}, None
        self.setSourceModel(model)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.setDynamicSortFilter(True)
        self.sort(0)

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        group = model.groups[row]
        if model.is_hidden(group) != self._hidden:
            return False
        # A copy hidden in Steam does not count (unless it was unhidden here): the game then
        # only shows through its other stores' copies, and not at all under the Steam filter.
        if not self._hidden:
            group = [g for g in group if not g.extra.get("steam_hidden") or game_options.get(g.key).get("hidden") is False]
        if self._store:
            group = [g for g in group if g.store == self._store]
        if self._installed:
            group = [g for g in group if g.installed]
        if group and self._shelf and not self._on_shelf(model, model.groups[row]):
            return False
        if group and self._tags and not all(self._has_tag(model, model.groups[row], t) for t in self._tags):
            return False
        return bool(group) and (not self._search or any(self._matches(g) for g in group))

    def _matches(self, g):
        """Search: the title (forgiving: search.py), and from the game's details its developer and genres."""
        if self._search in g.title.lower() or search.matches(self._search, g.title):
            return True
        d = details.cached(g.key) or {}
        return search.matches(self._search, "", [d.get("developer") or ""] + list(d.get("genres") or []))

    def _has_tag(self, model, group, tag):
        if tag == "unplayed":
            return model.group_value(group, "playtime") == 0
        if tag == "linux":
            return any(g.extra.get("linux") or g.extra.get("platform") == "linux" for g in group)
        if tag == "controller":
            return any((details.cached(g.key) or {}).get("controller") == "full" for g in group)
        if tag == "couch":
            return any(couch.local(_appid(g)) for g in group)
        if tag == "protondb":
            return any(protondb.rating(_appid(g)).get("tier") in ("platinum", "gold", "native") for g in group)
        if tag.startswith("genre:"):
            want = tag[6:]
            return any(want in ((details.cached(g.key) or {}).get("genres") or []) for g in group)
        return True

    def _on_shelf(self, model, group):
        s = self._shelf
        if s == "fav":
            return shelves.in_group(group, shelves.FAV)
        if s.startswith("c:"):
            return shelves.in_group(group, s[2:])
        if s == "playing":
            return model.group_value(group, "lastPlayed") > 0
        if s == "added":
            return shelves.is_recent(group)
        if s == "together":
            return any(couch.local(_appid(g)) for g in group)
        if s.startswith("s:"):
            return shelves.meta(group, "status") == s[2:]
        return True

    def _sort_mode(self):
        return {"playing": "recent", "added": "added", "together": "recent"}.get(self._shelf, self._sort)

    def _key(self, row):
        """Sort key for a source row, worked out once per library change (a sort compares
        each row many times; recomputing titles and playtimes each time made it slow)."""
        model = self.sourceModel()
        sort = self._sort_mode()
        if self._keys_gen != (model.generation, sort):
            self._keys, self._keys_gen = {}, (model.generation, sort)
        key = self._keys.get(row)
        if key is None:
            group = model.groups[row]
            title = model.rep(group).title.lower()
            if sort == "name":
                key = (title,)
            elif sort == "added":
                key = (-shelves.added(group), title)
            elif sort == "size":  # biggest installed first
                sizes = [float(g.extra.get("size", 0) or 0) for g in group if g.installed]
                key = (-max(sizes) if sizes else 0, title)
            elif sort == "rating":  # your best-rated first, unrated last
                key = (-int(shelves.meta(group, "rating") or 0), title)
            else:  # most recent / most played first; never-played games fall to the end
                value = model.group_value(group, "lastPlayed" if sort == "recent" else "playtime")
                key = (-value, title)
            self._keys[row] = key
        return key

    def lessThan(self, left, right):
        return self._key(left.row()) < self._key(right.row())

    def _set_sort(self, mode):
        if mode in SORTS and mode != self._sort:
            self._sort = mode
            settings.set("sort", mode)
            self.invalidate()
            self.filterChanged.emit()

    sortMode = Property(str, lambda s: s._sort, _set_sort, notify=filterChanged)

    def _set(self, attr, value):
        if getattr(self, attr) != value:
            setattr(self, attr, value)
            if attr == "_shelf":
                self.invalidate()  # the shelf can change the order too
            if attr == "_store":
                self.sourceModel().focus_store = value
                self.sourceModel().touch()
            self.invalidateFilter()
            self.filterChanged.emit()

    storeFilter = Property(str, lambda s: s._store, lambda s, v: s._set("_store", v), notify=filterChanged)
    installedOnly = Property(bool, lambda s: s._installed, lambda s, v: s._set("_installed", v), notify=filterChanged)
    search = Property(str, lambda s: s._search, lambda s, v: s._set("_search", v.strip().lower()), notify=filterChanged)
    # False: the normal library (hidden games left out). True: only the hidden games.
    showHidden = Property(bool, lambda s: s._hidden, lambda s, v: s._set("_hidden", v), notify=filterChanged)
    shelf = Property(str, lambda s: s._shelf, lambda s, v: s._set("_shelf", v), notify=filterChanged)
    tags = Property("QVariantList", lambda s: list(s._tags), lambda s, v: s._set("_tags", list(v or [])), notify=filterChanged)

    def refilter(self):
        self.invalidateFilter()
        self.filterChanged.emit()

    @Slot(int, result=str)
    def keyAt(self, row):
        idx = self.mapToSource(self.index(row, 0))
        model = self.sourceModel()
        return model.rep(model.groups[idx.row()]).key if idx.isValid() else ""


class AioLaunch(QObject):
    storesChanged = Signal()
    refreshingChanged = Signal()
    themeChanged = Signal()
    settingsChanged = Signal()
    toast = Signal(str)
    gameChanged = Signal(str)
    loginReady = Signal(str, str, str)   # store, url, prompt
    loginWeb = Signal(str, str, str)     # store, store name, url (built-in sign-in window)
    loginDone = Signal(str, bool, str)   # store, ok, message
    dlcsReady = Signal(str, "QVariantList", str)  # key, rows, note
    saveConflict = Signal(str, str, str)          # key, local date, cloud date
    epicFreeChanged = Signal()
    storageReady = Signal("QVariantMap")
    updateChanged = Signal()
    achievementsReady = Signal(str, "QVariantMap")  # key, {"done", "total"}
    blizzardSync = Signal()      # QML's hidden page reads the Blizzard account's games (BlizzardSync.qml)
    blizzardForget = Signal()    # QML clears the Blizzard sign-in it keeps

    _fetched = Signal(str, object, str)
    _worker_toast = Signal(str)
    _after = Signal(object)

    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.stores = {s.id: s for s in all_stores()}
        self.model = LibraryModel(self.stores)
        self.proxy = LibraryProxy(self.model)
        self.tvProxy = LibraryProxy(self.model)  # TV mode's own list: its shelves leave the main view alone
        self.tvNextProxy = LibraryProxy(self.model)  # the shelf below, shown as a preview under TV mode's row
        self.pool = ThreadPoolExecutor(min(4, os.cpu_count() or 2))
        self.procs: dict[str, QProcess] = {}
        self.logs: dict[str, list] = {}
        self._pending = set()
        # storesInfo is read by many bindings (sidebar, cards, TV mode) and each read used to
        # ask every store for its sign-in again: worked out once per storesChanged instead.
        # Connected before QML exists, so it runs before any binding re-reads the property.
        self._stores_cache = None
        self._per_change = {}  # other values that only change with storesChanged (recentGames, updateCount)
        self.storesChanged.connect(self._forget_stores_info)
        self._per_settings = {}  # settingsMap and light: hundreds of reads at start-up, one value per change
        self.settingsChanged.connect(self._per_settings.clear)
        settings.listeners.append(self._per_settings.clear)  # also changes made without the signal
        self._updates_seen = set()
        self._colour_pending = set()
        self._details_pending = set()
        self._sounds = None  # TV-mode sound effects, created on first use
        self._dlc_cache = {}  # key -> (time, rows)
        self._last_local = 0.0
        self._fetched.connect(self._on_fetched)
        personal.on_change(self._personal_changed)
        self._scheme_timer = QTimer(self, interval=20000)  # light/dark following the desktop or the clock
        self._scheme_timer.timeout.connect(self._check_scheme)
        self._scheme_timer.start()
        self._night = QTimer(self, interval=10 * 60 * 1000)
        self._night.timeout.connect(self._night_tick)
        self._night.start()
        self._worker_toast.connect(self.toast)
        self._after.connect(lambda fn: fn())

        self._theme = themes.current(self._dark_now())
        if settings.get("evening_warmth") is not False:  # the same as _load_theme, from the first frame
            _now = time.localtime()
            self._theme = themes.warmed(self._theme, themes.evening_amount(_now.tm_hour + _now.tm_min / 60))
        self._shortcut = {"accounts": 0, "added": 0, "steam": False, "running": False, "gameMode": False,
                          "busy": False, "games": 0, "gamesInSteam": 0, "inSync": False, "progress": ""}
        self._ge = {"latest": "", "installed": (proton.installed_ge() or [""])[0], "busy": False,
                    "progress": 0.0, "error": "", "upToDate": False}
        # Ryoku rewrites its palette file in place when the wallpaper changes; a folder watch only
        # sees files being added or replaced, so watch the file too (and again after a replace).
        self._watch = QFileSystemWatcher(self)
        self._palette_timer = QTimer(self, singleShot=True, interval=250)
        self._palette_timer.timeout.connect(self._load_theme)
        self._palette_tries = 0
        if PALETTE.parent.is_dir():
            self._watch.addPath(str(PALETTE.parent))
            self._watch.directoryChanged.connect(lambda _: self._palette_changed())
            self._watch.fileChanged.connect(lambda _: self._palette_changed())
            self._rewatch(self._watch, PALETTE)
        # Follow-wallpaper: react to the files desktops rewrite when the wallpaper changes (no polling).
        from . import wallpaper
        self._wall_watch = QFileSystemWatcher(wallpaper.watch_paths(), self)
        self._wall_pending = QTimer(self, singleShot=True, interval=800)
        self._wall_pending.timeout.connect(lambda: settings.get("theme_mode") == "ryoku" and (self._load_theme(), self._find_wallpaper()))
        self._wall_files = [p for p in wallpaper.watch_paths() if not os.path.isdir(p)]
        self._wall_watch.fileChanged.connect(lambda _: self._wall_changed())
        self._wall_watch.directoryChanged.connect(lambda _: self._wall_changed())
        # swww and swaybg keep the wallpaper in a running program, not in a file: ask them now and then.
        self._wall_poll = QTimer(self, interval=10000)
        self._wall_poll.timeout.connect(self._poll_wallpaper)
        # Evening warmth changes slowly: look again every ten minutes.
        self._warm_timer = QTimer(self, interval=10 * 60 * 1000)
        self._warm_timer.timeout.connect(self._load_theme)
        self._warm_timer.start()
        self._arm_wall_poll()
        self._find_wallpaper()

        session.SESSIONS.mkdir(parents=True, exist_ok=True)
        self._sessions = QFileSystemWatcher([str(session.SESSIONS)], self)
        self._sessions.directoryChanged.connect(lambda _: QTimer.singleShot(300, self._check_sessions))
        self._sessions_seen = {}
        self._check_sessions()
        # Steam games run outside Cornerplay's sessions: look for them every so often, so they
        # show as playing (and in the tray), and their sessions reach the weekly stats.
        self._steam_watch = QTimer(self, interval=15000)
        self._steam_watch.timeout.connect(self._check_steam_running)
        if not demo:
            self._steam_watch.start()
            QTimer.singleShot(3000, self._check_steam_running)
            QTimer.singleShot(2500, self._load_couch)

        if demo:
            self._load_demo()
            QTimer.singleShot(0, self._load_epic_free)  # real, public data: shown in the demo too
        else:
            cached = read_json(LIBRARY_CACHE) or []
            self.model.set_games(Game.from_dict(d) for d in cached if d.get("store") in self.stores)
            # With the library already on screen from the cache, the first refresh waits for the
            # start-up animation (startupAnimationDone): each store's answer makes the whole
            # interface re-count, and coming in during the first second it held up the animation.
            # The fallback covers a window that never shows. Nothing cached: refresh at once.
            self._first_refresh_done = False
            QTimer.singleShot(2500 if cached else 0, self._first_refresh)

    def _first_refresh(self):
        if not self._first_refresh_done:
            self._first_refresh_done = True
            self.refresh()

    @Slot()
    def startupAnimationDone(self):
        """The splash (or TV mode's intro) has played: time for the first refresh."""
        if hasattr(self, "_first_refresh_done"):
            QTimer.singleShot(0, self._first_refresh)

    # --- theme -----------------------------------------------------------
    @staticmethod
    def _rewatch(watcher, path):
        """A file watch is dropped when an editor replaces the file: add it back if needed."""
        path = str(path)
        if os.path.exists(path) and path not in watcher.files():
            watcher.addPath(path)

    def _palette_changed(self):
        self._rewatch(self._watch, PALETTE)
        self._palette_tries = 0
        self._palette_timer.start()

    def _wall_changed(self):
        for f in self._wall_files:
            self._rewatch(self._wall_watch, f)
        self._wall_pending.start()

    def _load_theme(self):
        # Caught Ryoku's palette half-written: try again shortly instead of flashing other colours.
        if (settings.get("theme_mode") == "ryoku" and PALETTE.exists() and not read_json(PALETTE)
                and self._palette_tries < 8):
            self._palette_tries += 1
            self._palette_timer.start()
            return
        new = themes.current(self._dark_now())
        if settings.get("evening_warmth") is not False:
            now = time.localtime()
            new = themes.warmed(new, themes.evening_amount(now.tm_hour + now.tm_min / 60))
        if new != self._theme:
            self._theme = new
            self.themeChanged.emit()
        self._find_wallpaper()
        self._arm_wall_poll()

    # --- light and dark that follow the desktop or the clock (theme.auto_mode) -------------
    _scheme_dark = None

    def _dark_now(self):
        mode = settings.get("theme_auto")
        if mode == "sunset":
            now = time.localtime()
            return themes.sunset_dark(now.tm_hour)
        if mode == "system":
            if self._scheme_dark is None:
                self._scheme_dark = self._read_scheme()
            return self._scheme_dark
        return None

    @staticmethod
    def _read_scheme():
        """The desktop's light/dark choice: Qt's, else the portal's (org.freedesktop.appearance
        color-scheme: 1 dark, 2 light), else None (no preference: the chosen look stays)."""
        scheme = QGuiApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusMessage
            msg = QDBusMessage.createMethodCall("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                                                "org.freedesktop.portal.Settings", "ReadOne")
            msg.setArguments(["org.freedesktop.appearance", "color-scheme"])
            reply = QDBusConnection.sessionBus().call(msg, timeout=1500)
            args = reply.arguments() if reply.type() != QDBusMessage.ErrorMessage else []
            value = args[0] if args else None
            value = getattr(value, "variant", lambda: value)() if not isinstance(value, int) else value
            return {1: True, 2: False}.get(int(value)) if value is not None else None
        except Exception:
            return None

    def _check_scheme(self):
        mode = settings.get("theme_auto")
        if mode == "system":
            now = self._read_scheme()
            if now != self._scheme_dark:
                self._scheme_dark = now
                self._load_theme()
        elif mode == "sunset":
            self._load_theme()  # cheap when nothing changed (same theme: no signal)

    # The wallpaper image itself (Follow wallpaper): shown blurred behind the main window.
    wallpaperChanged = Signal()
    _wallpaper = ""

    _wallpaper_src = ""

    def _find_wallpaper(self):
        """The wallpaper behind the window: blurred once, in the background, into a small cached
        picture (wallpaper.backdrop), so showing it costs no GPU effect."""
        path = ""
        if settings.get("theme_mode") == "ryoku" and settings.get("wallpaper_backdrop") is not False:
            from . import wallpaper
            path = self._theme.get("wallpaper") or wallpaper.find()[1]
        if path == self._wallpaper_src:
            return
        self._wallpaper_src = path
        if not path:
            self._set_backdrop("")
            return

        def work():
            from . import wallpaper
            blurred = wallpaper.backdrop(path)
            return lambda: self._wallpaper_src == path and self._set_backdrop(blurred)
        self._bg(work)

    def _set_backdrop(self, path):
        if path != self._wallpaper:
            self._wallpaper = path
            self.wallpaperChanged.emit()

    wallpaperPath = Property(str, lambda s: s._wallpaper, notify=wallpaperChanged)  # the blurred copy

    POLLED_WALLPAPERS = ("swww", "awww", "swaybg")

    def _arm_wall_poll(self):
        poll = getattr(self, "_wall_poll", None)
        if poll is None:
            return
        if self._theme.get("wallpaperSource") in self.POLLED_WALLPAPERS:
            if not poll.isActive():
                poll.start()
        else:
            poll.stop()

    def _poll_wallpaper(self):
        if settings.get("theme_mode") != "ryoku":
            return
        from . import wallpaper
        _source, path = wallpaper.find()
        if path and path != self._theme.get("wallpaper"):
            self._load_theme()

    theme = Property("QVariantMap", lambda s: s._theme, notify=themeChanged)
    TITLE_FONTS = {"": "Nunito", "condensed": "Barlow Condensed", "serif": "Lora", "pixel": "Silkscreen"}
    titleFamily = Property(str, lambda s: s.TITLE_FONTS.get(settings.get("title_font") or "", "Nunito"), notify=settingsChanged)
    themePresets = Property("QVariantList", lambda s: list(themes.PRESETS), constant=True)
    lightPresets = Property("QVariantList", lambda s: [n for n, (bg, _a) in themes.PRESETS.items() if themes.luminance(bg) >= 0.5], constant=True)
    darkPresets = Property("QVariantList", lambda s: [n for n, (bg, _a) in themes.PRESETS.items() if themes.luminance(bg) < 0.5], constant=True)
    accentChoices = Property("QVariantList", lambda s: themes.ACCENTS, constant=True)
    backgroundChoices = Property("QVariantList", lambda s: themes.BACKGROUNDS, constant=True)

    @Slot(str, str)
    def setCustomColor(self, which, colour):
        """Switch to a custom theme, starting from the colours on screen now."""
        colour = colour.strip().lower()
        if which not in ("theme_bg", "theme_accent") or not themes.valid(colour):
            return
        if settings.get("theme_mode") != "custom":
            settings.set("theme_bg", self._theme["background"])
            settings.set("theme_accent", self._theme["primary"])
            settings.set("theme_mode", "custom")
        settings.set(which, colour)
        self.settingsChanged.emit()
        self._load_theme()

    # --- stores ----------------------------------------------------------
    def _forget_stores_info(self):
        self._stores_cache = None
        self._per_change.clear()

    def _once_per_change(self, name, work):
        if name not in self._per_change:
            self._per_change[name] = work()
        return self._per_change[name]

    def _stores_info(self):
        if self._stores_cache is None:
            self._stores_cache = self._work_out_stores_info()
        return self._stores_cache

    def _work_out_stores_info(self):
        out = []
        for s in self.stores.values():
            mine = [g for g in self.model.games if g.store == s.id
                    and not game_options.get(g.key).get("hidden")]
            try:
                logged, account, problem = s.logged_in(), s.account(), s.problem()
            except Exception as e:  # a broken config file must not take the UI down
                logged, account, problem = False, "", str(e)
            out.append({"id": s.id, "name": s.name, "color": s.color, "tile": getattr(s, "tile", s.color), "count": len(mine),
                        "inAccounts": getattr(s, "in_accounts", True),
                        "installed": sum(g.installed for g in mine), "loggedIn": logged,
                        "account": account, "problem": problem, "loginKind": s.login_kind,
                        "refreshing": s.id in self._pending})
        return out

    storesInfo = Property("QVariantList", _stores_info, notify=storesChanged)

    # Store logos as SVG text (white); QML recolours them (see qml/StoreIcon.qml).
    _icons = {p.stem: p.read_text() for p in (Path(__file__).parent / "icons").glob("*.svg")}
    storeIcons = Property("QVariantMap", lambda s: s._icons, constant=True)
    # Button and menu icons (Lucide, ISC licence), stroke="currentColor"; see qml/Icon.qml.
    _ui_icons = {p.stem: re.sub(r"<!--.*?-->", "", p.read_text(), flags=re.S).strip()
                 for p in (Path(__file__).parent / "icons" / "ui").glob("*.svg")}
    uiIcons = Property("QVariantMap", lambda s: s._ui_icons, constant=True)

    RUMBLE = {"move": (0.0, 0.12, 28), "select": (0.25, 0.35, 60), "back": (0.15, 0.0, 45)}  # low, high, ms

    @Slot(str)
    def uiSound(self, name):
        """A soft click in TV mode ("move", "select" or "back"), when turned on in Settings;
        "intro" is the TV intro's chime (its own setting). With rumble on, the pad buzzes too."""
        pad = getattr(self, "gamepad", None)
        if pad is not None and settings.get("tv_rumble") and name in self.RUMBLE:
            pad.rumble(*self.RUMBLE[name])
        if not settings.get("tv_intro" if name == "intro" else "tv_sounds"):
            return
        if self._sounds is None:
            self._sounds = {}
            try:  # Qt Multimedia is optional; without it there is simply no sound
                from PySide6.QtMultimedia import QSoundEffect
            except ImportError:
                return
            for n in ("move", "select", "back", "intro"):
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(Path(__file__).parent / "sounds" / f"{n}.wav")))
                effect.setVolume(0.6)
                self._sounds[n] = effect
        effect = self._sounds.get(name)
        if effect:
            effect.play()

    gameColourReady = Signal(str, str)  # key, accent ("" = no clear colour)
    detailsReady = Signal(str, "QVariantMap")  # key, {description, genres, developer, year}

    @Slot(str, result="QVariantMap")
    def gameDetails(self, key):
        """Description, genres, developer and year; {} until known (detailsReady follows)."""
        g = self.model.find(key)
        if not g or g.id == "battlenet-app":
            return {}
        d = details.cached(key)
        if d is not None:
            return d
        if key not in self._details_pending:
            self._details_pending.add(key)
            appid = _appid(g)

            def work():
                d = details.fetch(g, appid)
                return lambda: (self._details_pending.discard(key), self.detailsReady.emit(key, d))
            self._bg(work)
        return {}

    @Slot(str, result="QVariantList")
    def similarGames(self, key):
        """Games in your library like this one: most shared genres, then the same developer."""
        mine = details.cached(key) or {}
        genres, dev = set(mine.get("genres") or []), (mine.get("developer") or "").split(",")[0].strip()
        if not genres and not dev:
            return []
        me = self.model.group_of(key)
        scored = []
        for grp in self.model.groups:
            if grp is me or self.model.is_hidden(grp):
                continue
            g = self.model.rep(grp)
            d = details.cached(g.key) or {}
            score = len(genres & set(d.get("genres") or [])) * 2 + (2 if dev and dev in (d.get("developer") or "") else 0)
            if score >= 2:
                scored.append((score, self.model.group_value(grp, "playtime") == 0, g))
        scored.sort(key=lambda x: (-x[0], not x[1], x[2].title.lower()))
        return [{"key": g.key, "title": g.title, "covers": _covers(g), "installed": g.installed,
                 "unplayed": unplayed} for _s, unplayed, g in scored[:12]]

    @Slot(result="QVariantList")
    def genreList(self):
        """Genres in the library (from the details fetched so far), most common first."""
        counts = {}
        for grp in self.model.groups:
            for x in (details.cached(self.model.rep(grp).key) or {}).get("genres") or []:
                counts[x] = counts.get(x, 0) + 1
        return [g for g, _n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    detailsGrew = Signal()

    def _prefetch_details(self):
        """Fetch every game's details slowly in the background (one each 1.5 s, inside Steam's
        rate limit), so filters, search and similar games can use genres and controller support."""
        if getattr(self, "_prefetching", False) or self.demo:
            return
        todo = [self.model.rep(grp) for grp in self.model.groups]
        todo = [g for g in todo if details.cached(g.key) is None and g.id != "battlenet-app"]
        if not todo:
            return
        self._prefetching = True

        def work():
            done = 0
            for g in todo:
                if getattr(self, "_quitting", False):
                    break
                try:
                    details.fetch(g, _appid(g))
                except Exception:
                    pass
                done += 1
                if done % 25 == 0:
                    self._after.emit(self.detailsGrew.emit)
                time.sleep(1.5)

            def finish():
                self._prefetching = False
                self.detailsGrew.emit()
                if self.proxy.tags or self.proxy.search:
                    self.proxy.refilter()
            return finish
        self._bg(work)

    @Slot(str, result=str)
    def gameColour(self, key):
        """Accent taken from a game's cover; "" until it is known (gameColourReady follows)."""
        g = self.model.find(key)
        if not g or g.id == "battlenet-app":
            return ""
        value = gamecolour.cached(key)
        if value is not None:
            return gamecolour.accent(value, self._theme.get("dark", True))
        if key not in self._colour_pending:
            self._colour_pending.add(key)
            urls = _covers(g)[:3]

            def work():
                value = gamecolour.compute(key, urls)

                def done():
                    self._colour_pending.discard(key)
                    if value is not None:
                        self.gameColourReady.emit(key, gamecolour.accent(value, self._theme.get("dark", True)))
                return done
            self._bg(work)
        return ""

    def _recent_games(self):
        """The "Continue playing" row: games you have played (here or on another PC), most recent first."""
        m = self.model
        rows = []
        for group in m.groups:
            last = m.group_value(group, "lastPlayed")
            if last and not m.is_hidden(group):  # installed here or not: played is what counts
                rows.append((last, group))
        rows.sort(key=lambda r: -r[0])
        out = []
        for last, group in rows[:RECENT_ROW]:
            g = m.rep(group)
            out.append({"key": g.key, "store": g.store, "title": g.title, "cover": _cover(g), "coverFallback": g.cover_fallback,
                        "covers": _covers(g), "heroes": _heroes(g), "logos": _logos(g),
                        "storeName": self.stores[g.store].name, "storeColor": self.stores[g.store].color,
                        "lastPlayed": last})
        return out

    recentGames = Property("QVariantList", lambda s: s._once_per_change("recent", s._recent_games), notify=storesChanged)
    updateCount = Property(int, lambda s: s._once_per_change(
        "updates", lambda: sum(1 for g in s.model.games if g.installed and g.extra.get("update"))), notify=storesChanged)

    @Slot("QVariant", "QVariant", result=str)
    def playedText(self, seconds, last):
        """ "12 h played · last played 3 days ago", or "" for a game never played."""
        seconds, last = int(seconds or 0), int(last or 0)
        parts = []
        if seconds >= 3600:
            parts.append(QCoreApplication.translate("app", "%1 h played").replace("%1", f"{seconds / 3600:.1f}".rstrip("0").rstrip(".")))
        elif seconds >= 60:
            parts.append(QCoreApplication.translate("app", "%1 min played").replace("%1", str(seconds // 60)))
        if last:
            days = (time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)) - last) / 86400
            when = (QCoreApplication.translate("app", "today") if days < 0 else QCoreApplication.translate("app", "yesterday") if days < 1
                    else QCoreApplication.translate("app", "%1 days ago").replace("%1", str(int(days) + 1)) if days < 6
                    else _short_date(last, with_year=days > 300))
            parts.append(QCoreApplication.translate("app", "last played %1").replace("%1", when))
        text = " · ".join(parts)
        return text[:1].upper() + text[1:]

    def _reload_playtime(self):
        self.model.played = playtime.load()
        self.model.touch()
        self.storesChanged.emit()
    refreshing = Property(bool, lambda s: bool(s._pending), notify=refreshingChanged)
    totalCount = Property(int, lambda s: len(s.model.groups) - s._once_per_change("hidden", s._hidden_count),
                          notify=storesChanged)

    @Slot()
    @Slot(str)
    @Slot(str, bool)
    def refresh(self, store_id="", force=False):
        """force (the Refresh button): skip the stores' own caches so new purchases show at once."""
        if not store_id:
            self._load_epic_free(force)
            self._load_wishlist(force)
            self._load_other_free(force)
            self._check_update()
            self._check_host_import()
            self.syncPersonal()
        if self.demo:
            return
        for s in ([self.stores[store_id]] if store_id else self.stores.values()):
            if s.id in self._pending:
                continue
            self._pending.add(s.id)
            self.pool.submit(self._fetch, s, force)
        linked = battlenet.owned() if not store_id else None
        if linked is not None:
            # Blizzard's account site asks for the password again quite often, and owned games
            # rarely change: sync at most once a day (or on Refresh), never while the sign-in
            # has expired (only Refresh or a new link tries then). At start it waits a little:
            # the hidden page needs Chromium (~0.5 s to load), and the window comes first.
            stale = time.time() - linked.get("t", 0) > 86400
            if force or (stale and not linked.get("expired")):
                if getattr(self, "_blizzard_started", False):
                    self.blizzardSync.emit()
                else:
                    self._blizzard_started = True
                    QTimer.singleShot(6000, self.blizzardSync.emit)
        self.refreshingChanged.emit()
        self.storesChanged.emit()

    # --- add a game by hand, import installed games ---------------------------------
    @Slot(str, str, str)
    def addGame(self, exe, title, args):
        exe = QUrl(exe).toLocalFile() if exe.startswith("file:") else exe
        try:
            e = custom_games.add(exe, title, args)
        except StoreError as err:
            self.toast.emit(str(err))
            return
        self.toast.emit(f"Added {e['title']} ({'Linux program' if e['kind'] == 'linux' else 'Windows program, runs through Proton'})")
        self.refresh("custom")

    @Slot(str, result="QVariantList")
    def ownedNotInstalled(self, store_id):
        return sorted(({"id": g.id, "title": g.title} for g in self.model.games
                       if g.store == store_id and not g.installed), key=lambda r: r["title"].lower())

    @Slot(str)
    def importFolder(self, folder):
        """GOG games in a folder (or its subfolders) are found from now on."""
        folder = QUrl(folder).toLocalFile() if folder.startswith("file:") else folder

        def work():
            n = importer.import_gog(folder)
            return lambda: (self.toast.emit(f"Found {n} GOG game{'s' if n != 1 else ''}" if n else
                                            "No GOG games in that folder. For an Epic or Amazon game, pick the game first."),
                            self.refresh("gog") if n else None)
        self._bg(work)

    @Slot(str, str, str)
    def importGame(self, store_id, gid, folder):
        folder = QUrl(folder).toLocalFile() if folder.startswith("file:") else folder
        g = self.model.find(f"{store_id}:{gid}")
        title = g.title if g else gid

        def work():
            try:
                tool = self.stores[store_id].tool()
            except StoreError as e:
                return lambda msg=str(e): self.toast.emit(msg)
            ok, msg = (importer.import_epic if store_id == "epic" else importer.import_amazon)(tool, gid, folder)
            return lambda: (self.toast.emit(f"Imported {title}" if ok else f"Could not import {title}: {msg[0][-140:]}"),
                            self.refresh(store_id))
        self._bg(work)

    @Slot(result=int)
    def heroicCount(self):
        return len(importer.heroic_installs())

    @Slot()
    def importHeroic(self):
        """Every game Heroic installed: Epic and Amazon through their import commands, GOG by folder."""
        def work():
            done, failed = 0, []
            for e in importer.heroic_installs():
                if e["store"] == "gog":
                    importer.add_library_dir(os.path.dirname(e["path"]))
                    done += 1
                    continue
                try:
                    tool = self.stores[e["store"]].tool()
                except StoreError:
                    failed.append(e["title"] or e["id"])
                    continue
                ok, _msg = (importer.import_epic if e["store"] == "epic" else importer.import_amazon)(tool, e["id"], e["path"])
                done += ok
                if not ok:
                    failed.append(e["title"] or e["id"])
            return lambda: (self.toast.emit(f"Imported {done} game{'s' if done != 1 else ''} from Heroic"
                                            + (f"; could not import {', '.join(failed[:3])}" if failed else "")),
                            self.refresh("", False))
        self._bg(work)

    # --- save backups -----------------------------------------------------------------
    savesReady = Signal(str, "QVariantList")

    def _refresh_save_index(self):
        """The save-location index, once a week, in the background (13 s of parsing)."""
        if not settings.get("save_backups") or self.demo or not savebackup.index_is_old():
            return
        self._bg(lambda: (savebackup.build_index(), None)[1])

    @Slot(str)
    def loadSaveBackups(self, key):
        g = self.model.find(key)
        if not g:
            return

        def work():
            rows = [dict(b, when=time.strftime("%d %b %Y, %H:%M", time.localtime(b["made"])),
                         sizeText=storage.nice(b["size"])) for b in savebackup.backups(g)]
            known = bool(savebackup.entry_for(g, _appid(g)))
            found = len(savebackup.paths_for(g, _appid(g))) if known else 0
            info = [{"_meta": True, "known": known, "found": found, "indexed": bool(savebackup.index().get("games"))}]
            return lambda: self.savesReady.emit(key, info + rows)
        self._bg(work)

    @Slot(str)
    def backupSavesNow(self, key):
        g = self.model.find(key)
        if not g:
            return

        def work():
            name = savebackup.backup(g, _appid(g), reason="by hand")
            return lambda: (self.toast.emit(f"Saves of {g.title} backed up" if name else
                                            f"No saves of {g.title} found on this PC yet"), self.loadSaveBackups(key))
        self._bg(work)

    @Slot(str, str)
    def restoreSaves(self, key, name):
        g = self.model.find(key)
        if not g or self._playing.get(key):
            self.toast.emit("Close the game first, then restore")
            return

        def work():
            n = savebackup.restore(g, name, _appid(g))
            return lambda: (self.toast.emit(f"Put back {n} save file{'s' if n != 1 else ''} of {g.title} "
                                            "(what was there is backed up too)"), self.loadSaveBackups(key))
        self._bg(work)

    @Slot(str)
    def openSaveBackups(self, key):
        g = self.model.find(key)
        if g:
            folder = savebackup.folder_of(g)
            os.makedirs(folder, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # --- health check ------------------------------------------------------------
    healthReady = Signal("QVariantList")

    @Slot()
    def checkHealth(self):
        runner.forget_vulkan_check()
        gp = getattr(self, "gamepad", None)
        pad = gp.property("available") if gp is not None else True

        def work():
            rows = health.checks(self.stores, pad)
            return lambda: self.healthReady.emit(rows)
        self._bg(work)

    @Slot()
    def fetchBackends(self):
        self.toast.emit("Downloading the store tools…")
        self._detach([sys.executable, "-m", "cornerplay", "--fetch-backends"],
                     {"PYTHONPATH": str(Path(__file__).resolve().parent.parent)}, "", "fetch-backends")
        QTimer.singleShot(20000, self.checkHealth)

    @Slot(str)
    def copyText(self, text):
        QGuiApplication.clipboard().setText(text)
        self.toast.emit("Copied: paste it into a terminal")

    # --- launch problems explained --------------------------------------------------
    launchProblem = Signal(str, "QVariantMap")  # key, {"title", "cause", "detail", "fix"}

    def _after_session(self, data):
        """A game started from Cornerplay ended: if it closed within seconds, say why when the log shows it."""
        key = data.get("key", "")
        ran = (data.get("since") or 0) - (data.get("started") or data.get("since") or 0)
        if not key or ran > 25:
            return
        text = ""
        try:
            with open(data.get("log") or "", errors="replace") as f:
                text = f.read()[-200000:]
        except OSError:
            pass
        found = problems.explain(text)
        if not found and data.get("exit") in (0, None):
            return  # closed quickly but cleanly: probably a launcher handing over
        found = found or {"cause": "It closed right away", "fix": "proton",
                          "detail": "Nothing in its log says why. Another Proton version, or Repair files, often helps."}
        self.launchProblem.emit(key, dict(found, title=data.get("title", "")))

    @Slot(str, str)
    def fixProblem(self, key, fix):
        g = self.model.find(key)
        if not g:
            return
        if fix == "repair":
            self.verifyGame(key)
        elif fix in ("vcrun", "dotnet"):
            # winetricks through umu, into this game's own prefix
            verb = "vcrun2022" if fix == "vcrun" else "dotnet48"
            try:
                with runner.using(self._options_for(g)):
                    kind, run = runner.compat()
                    env = runner.wine_env(g.store, g.id)
            except StoreError as e:
                self.toast.emit(str(e))
                return
            if kind != "umu":
                self.toast.emit(f"Install {verb} with winetricks into {env.get('WINEPREFIX')}")
                return
            self._start_job(g, "fix", Command([run, "winetricks", "-q", verb], env))
            self.toast.emit(f"Installing {verb} for {g.title}; it can take a few minutes")

    # --- backup and restore -----------------------------------------------------------
    @Slot(str)
    def makeBackup(self, folder):
        folder = QUrl(folder).toLocalFile() if folder.startswith("file:") else (folder or "")
        try:
            path = backup.make(folder or None)
            self.toast.emit(f"Backup saved: {path}")
        except OSError as e:
            self.toast.emit(f"Backup failed: {e}")

    @Slot(str)
    def restoreBackup(self, file):
        file = QUrl(file).toLocalFile() if file.startswith("file:") else file
        try:
            backup.restore(file)
        except (OSError, ValueError, KeyError) as e:
            self.toast.emit(f"Restore failed: {e}")
            return
        self.toast.emit("Restored. Cornerplay restarts to load it…")
        QTimer.singleShot(1500, self.restartApp)

    # --- leftover Proton prefixes -------------------------------------------------------
    prefixesReady = Signal("QVariantList")

    @Slot()
    def loadPrefixes(self):
        root = str(settings.games_dir / "prefixes")
        # Every game that may run through Proton keeps its prefix: also games added by hand
        # (their prefix holds their saves) and itch.io games.
        wanted = {os.path.basename(runner.prefix_path(g.store, g.id)) for g in self.model.games
                  if g.installed and g.store in ("epic", "gog", "amazon", "custom", "itch")}
        if self.stores["battlenet"].launcher_exe():
            wanted.add(os.path.basename(runner.prefix_path("battlenet", "launcher")))

        def work():
            rows = storage.leftover_prefixes(root, wanted)
            return lambda: self.prefixesReady.emit(rows)
        self._bg(work)

    @Slot(str)
    def deletePrefix(self, path):
        root = os.path.realpath(str(settings.games_dir / "prefixes"))
        real = os.path.realpath(path)
        if os.path.dirname(real) != root or not os.path.isdir(real):
            self.toast.emit("Refusing to delete a folder outside the prefixes folder")
            return

        def work():
            import shutil
            shutil.rmtree(real, ignore_errors=True)
            return lambda: (self.toast.emit(f"Deleted {os.path.basename(real)}"), self.loadPrefixes())
        self._bg(work)

    # --- updates overnight ---------------------------------------------------------------
    def _night_tick(self):
        """Every 10 minutes: in the chosen hours, on mains power and a normal (not metered)
        connection, refresh once and update the games that have one."""
        if not settings.get("auto_update") or self.demo:
            return
        hour = time.localtime().tm_hour
        start, end = int(settings.get("auto_update_from")), int(settings.get("auto_update_to"))
        inside = start <= hour < end if start < end else (hour >= start or hour < end)
        if not inside:
            self._night_refreshed = False
            return
        batt = self.battery()
        if batt and not batt.get("charging"):
            return
        if not self._network_ok() or self._playing:
            return
        if not getattr(self, "_night_refreshed", False):
            self._night_refreshed = True
            self.refresh("", True)  # find the updates first; the next tick installs them
            return
        for g in self.model.games:
            if g.installed and g.extra.get("update") and g.key not in self.procs \
                    and g.store in ("epic", "gog", "amazon") and self.model.jobs.get(g.key, {}).get("kind") not in ("queued", "paused"):
                self.update(g.key)

    @staticmethod
    def _network_ok():
        """Not on a metered connection (phone hotspot). Without NetworkManager: assume fine."""
        import shutil, subprocess
        if not shutil.which("nmcli"):
            return True
        try:
            out = subprocess.run(["nmcli", "-t", "-f", "GENERAL.METERED", "device", "show"],
                                 capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.TimeoutExpired):
            return True
        return not any(line.split(":", 1)[-1].startswith("yes") for line in out.splitlines())

    # --- Cornerplay's own updates ---------------------------------------------
    _update = {}
    _updating = False

    def _check_update(self):
        if self.demo or updates.from_source() or not settings.get("update_check"):
            return
        if updates.managed() and not host.IN_FLATPAK:
            return  # pacman keeps it current

        def work():
            info = updates.latest()  # a Flatpak from Flathub gets {} here: Flatpak updates it
            return lambda: (setattr(self, "_update", info), self.updateChanged.emit())
        self._bg(work)

    appUpdate = Property("QVariantMap", lambda s: dict(s._update, busy=s._updating), notify=updateChanged)

    @Slot()
    def installUpdate(self):
        """Download the new installer and run it (no root: --no-system); then offer a restart."""
        info = self._update
        if not info.get("asset") or self._updating:
            return
        self._updating = True
        self.updateChanged.emit()

        def work():
            try:
                path = updates.download(info["asset"], info.get("sha256", ""))
            except Exception as e:
                def failed(msg=redact(e)):
                    self._updating = False
                    self.updateChanged.emit()
                    self.toast.emit(f"The update was not installed: {msg}")
                return failed

            def run():
                p = QProcess(self)
                p.finished.connect(lambda code, _s: self._update_done(code, info["version"]))
                if info.get("kind") == "flatpak":
                    cmd = updates.install_flatpak_argv(path)  # the host's flatpak installs it over this one
                    p.start(cmd[0], cmd[1:])
                else:
                    p.start("sh", [str(path), "--yes", "--no-system"])
                self._update_proc = p
            return run
        self._bg(work)

    def _update_done(self, code, version):
        self._updating = False
        if code == 0:
            self._update = {"version": version, "installed": True}
            self.toast.emit(f"Cornerplay {version} is installed. Restart to use it.")
        else:
            self.toast.emit("The update did not install; try again, or download it from GitHub")
        self.updateChanged.emit()

    @Slot()
    def restartApp(self):
        args = [a for a in sys.argv[1:] if a == "--tv"]
        if host.IN_FLATPAK:
            # A new start of the Flatpak, from the host: it runs the newest installed version
            # (after an update), where a start from inside this sandbox would run this one again.
            cmd = host.argv(["flatpak", "run", host.APP_ID, *args])
            QProcess.startDetached(cmd[0], cmd[1:])
            QGuiApplication.quit()
            return
        # The launcher the installer wrote knows where the new copy and its Python live.
        import shutil
        launcher = shutil.which("cornerplay") or str(Path.home() / ".local/bin/cornerplay")
        args = [a for a in sys.argv[1:] if a == "--tv"]
        if os.path.exists(launcher):
            QProcess.startDetached(launcher, args)
        else:
            QProcess.startDetached(sys.executable, ["-m", "cornerplay"] + args)
        QGuiApplication.quit()

    # --- the tray and starting with the PC (tray.py) ---------------------------------
    tray = None  # set by tray.Tray

    trayAvailable = Property(bool, lambda s: bool(s.tray and s.tray.available), constant=True)

    @Slot(result=bool)
    def keepInTray(self):
        """Closing the window: stay in the tray instead of quitting."""
        return bool(self.tray and self.tray.keep_on_close())

    @Slot(bool)
    def setStartWithPc(self, on):
        from . import tray as tray_mod
        err = tray_mod.set_autostart(on)
        if err:
            self.toast.emit(f"Could not change starting with the PC: {err}")
            return
        settings.set("start_with_pc", bool(on))
        self.settingsChanged.emit()
        self.toast.emit("Cornerplay starts in the tray when you log in" if on else "Cornerplay no longer starts with the PC")

    @Slot()
    def dismissUpdate(self):
        self._update = {}
        self.updateChanged.emit()

    # --- the Flatpak: bring the regular install's library over ---------------------
    hostImportChanged = Signal()
    _host_import = {}
    _host_import_checked = False

    def _check_host_import(self):
        """Once per start, in the Flatpak: has the regular install been used on this PC?"""
        if self.demo or not host.IN_FLATPAK or self._host_import_checked:
            return
        self._host_import_checked = True

        def work():
            offer = hostimport.available()
            return lambda: (setattr(self, "_host_import", {"offer": offer}), self.hostImportChanged.emit())
        self._bg(work)

    inFlatpak = Property(bool, lambda s: host.IN_FLATPAK, constant=True)
    # Started as the whole session from the login screen (cornerplay/session/cornerplay-session).
    inSession = Property(bool, lambda s: os.environ.get("CORNERPLAY_SESSION") == "1", constant=True)
    hostImport = Property("QVariantMap", lambda s: dict(s._host_import), notify=hostImportChanged)

    @Slot()
    def importFromHost(self):
        """Copy the regular install's settings, sign-ins and library into the Flatpak, then restart."""
        if not host.IN_FLATPAK or self._host_import.get("busy"):
            return
        self._host_import = {"busy": True}
        self.hostImportChanged.emit()

        def work():
            try:
                hostimport.run()
            except RuntimeError as e:
                def failed(msg=redact(e)):
                    self._host_import = {}
                    self.hostImportChanged.emit()
                    self.toast.emit(f"Nothing was brought over: {msg}")
                return failed

            def done():
                self.toast.emit("Your library, settings and sign-ins are here. Cornerplay restarts to load them…")
                QTimer.singleShot(1500, self.restartApp)
            return done
        self._bg(work)

    @Slot()
    def dismissHostImport(self):
        hostimport.dismiss()
        self._host_import = {}
        self.hostImportChanged.emit()

    # --- storage: sizes, drives, moving installs ------------------------------
    MOVABLE = ("epic", "gog", "amazon")

    @Slot()
    def loadStorage(self):
        """Sizes of every installed game and how full each drive is; storageReady follows."""
        games = [g for g in self.model.games if g.installed and g.install_path and g.id != "battlenet-app"]
        last = {g.key: playtime.of(g, self.model.played)[1] for g in games}

        def work():
            rows, drives = [], {}
            for g in games:
                size = storage.size_of(g.install_path, g.extra.get("size", 0))
                d = storage.drive(g.install_path)
                if d:
                    drives.setdefault(d["mount"], dict(d, games=0, gameBytes=0))
                    drives[d["mount"]]["games"] += 1
                    drives[d["mount"]]["gameBytes"] += size
                rows.append({"key": g.key, "title": g.title, "store": g.store,
                             "storeName": self.stores[g.store].name, "storeColor": self.stores[g.store].color,
                             "path": g.install_path, "bytes": size, "size": storage.nice(size),
                             "mount": d["mount"] if d else "", "last": last.get(g.key, 0),
                             "lastText": _short_date(last[g.key], True) if last.get(g.key) else "never",
                             "covers": _covers(g), "movable": g.store in self.MOVABLE})
            for extra in [str(settings.games_dir)] + list(settings.get("library_dirs") or []):
                d = storage.drive(extra) if os.path.isdir(extra) else None
                if d and d["mount"] not in drives:
                    drives[d["mount"]] = dict(d, games=0, gameBytes=0)
            rows.sort(key=lambda r: -r["bytes"])
            out = {"games": rows, "total": storage.nice(sum(r["bytes"] for r in rows)),
                   "drives": [dict(d, freeText=storage.nice(d["free"]), totalText=storage.nice(d["total"]),
                                   gamesText=storage.nice(d["gameBytes"])) for d in drives.values()]}
            return lambda: self.storageReady.emit(out)
        self._bg(work)

    @Slot(str, str)
    def moveGame(self, key, dest_dir):
        """Move an installed game into dest_dir (a folder; the game keeps its own folder name)."""
        g = self.model.find(key)
        if not g or not g.installed or key in self.procs:
            return
        if g.store == "steam":
            self.toast.emit("Steam moves its own games: in Steam, Settings > Storage, pick the game, then Move")
            client = self.stores["steam"].client()
            if client:
                self._detach(client + ["steam://open/main"], {}, "", "steam-client")
            return
        if g.store not in self.MOVABLE:
            self.toast.emit(f"{self.stores[g.store].name} games can only be moved from the {self.stores[g.store].name} app")
            return
        dest_dir = QUrl(dest_dir).toLocalFile() if dest_dir.startswith("file:") else dest_dir
        src = os.path.realpath(g.install_path)
        dst = os.path.join(dest_dir, os.path.basename(src.rstrip("/")))
        if os.path.realpath(dest_dir) == os.path.dirname(src):
            self.toast.emit(f"{g.title} is already there")
            return
        if os.path.exists(dst):
            self.toast.emit(f"There is already a folder called {os.path.basename(dst)} there")
            return
        self._moves[key] = (src, dst, dest_dir)
        root = str(Path(__file__).resolve().parent.parent)
        env = {"PYTHONPATH": root + (":" + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")}
        self._start_job(g, "move", Command([sys.executable, "-m", "cornerplay.mover", src, dst], env, root))

    _moves = {}

    def _after_move(self, g):
        """Tell the store where its game went (GOG finds it through library_dirs)."""
        src, dst, dest_dir = self._moves.pop(g.key, ("", "", ""))
        if not dst or not os.path.isdir(dst):
            return
        dirs = list(settings.get("library_dirs") or [])
        if dest_dir not in dirs:
            settings.set("library_dirs", dirs + [dest_dir])
        if g.store == "epic":
            tool = self.stores["epic"].tool()
            store_run([tool, "move", g.id, dest_dir, "--skip-move"], timeout=120)
        elif g.store == "amazon":
            from .stores.amazon import NILE_DIR
            path = NILE_DIR / "installed.json"
            data = read_json(path) or []
            for entry in data:
                if entry.get("id") == g.id:
                    entry["path"] = dst
            write_json(path, data)
        shelves.forget_install_times()

    # --- Epic's free games ---------------------------------------------------
    _epic_free = []

    def _load_epic_free(self, force=False):
        def work():
            games = epicfree.get(force)
            return lambda: (setattr(self, "_epic_free", games), self.epicFreeChanged.emit())
        self._bg(work)

    def _epic_free_info(self):
        """This week's free Epic games (and the next ones), marked when already in the library."""
        owned = {covers.norm(g.title) for g in self.model.games if g.store == "epic"}
        now = time.time()
        out = []
        if now < (settings.get("epic_free_hidden_until") or 0):
            return []  # hidden until this week's offers end
        for g in self._epic_free:
            if g.get("end") and g["end"] < now:
                continue  # the offer ran out since the list was fetched
            live = g["now"] or (g.get("start") and g["start"] <= now)
            when = g["end"] if live else g.get("start", 0)
            out.append(dict(g, now=bool(live), owned=covers.norm(g["title"]) in owned,
                            when=_short_date(when) if when else ""))
        return out

    epicFree = Property("QVariantList", _epic_free_info, notify=epicFreeChanged)

    # --- wishlist sales ---------------------------------------------------------
    _wishlist = []
    wishlistChanged = Signal()

    def _load_wishlist(self, force=False):
        if self.demo or not settings.get("wishlist_sales"):
            return
        steamid = settings.get("steam_id").strip() or self.stores["steam"]._recent_user()[0] or ""
        gog = self.stores["gog"]
        token_fn = gog._token if gog.logged_in() else None

        key = str(settings.get("itad_key") or "").strip()
        cut = int(settings.get("deal_alert_cut") or 50)

        def work():
            res = wishlist.get(steamid, token_fn, force, key, cut)

            def done():
                self._wishlist = res["items"]
                self.wishlistChanged.emit()
                deals = res.get("deals") or []
                if deals:
                    self._announce_deals(deals)
                elif res["new_sales"]:
                    names = res["new_sales"]
                    self.toast.emit(f"On sale from your wishlist: {names[0]}"
                                    + (f" and {len(names) - 1} more" if len(names) > 1 else ""))
            return done
        self._bg(work)

    # --- free to keep on other stores (IsThereAnyDeal giveaways, itad.py) -----------------
    _other_free = []
    otherFreeChanged = Signal()

    def _load_other_free(self, force=False):
        key = str(settings.get("itad_key") or "").strip()
        if self.demo or not key:
            if self._other_free:
                self._other_free = []
                self.otherFreeChanged.emit()
            return

        def work():
            from . import itad
            rows = itad.giveaways(key, force)
            return lambda: (setattr(self, "_other_free", rows), self.otherFreeChanged.emit())
        self._bg(work)

    def _other_free_info(self):
        owned = {covers.norm(g.title) for g in self.model.games}
        out = []
        for r in self._other_free:
            ends = r.get("ends") or 0
            out.append(dict(r, owned=covers.norm(r["title"]) in owned,
                            when=(lambda t: f"{t.tm_mday} {statsdata.MONTHS[t.tm_mon - 1][:3]}")(time.localtime(ends)) if ends else ""))
        return out

    otherFree = Property("QVariantList", _other_free_info, notify=otherFreeChanged)

    def _announce_deals(self, deals):
        """A desktop notification (it reaches you in a game or with Cornerplay in the tray), and a toast."""
        def line(d):
            return f"{d['title']}: {d['price']} on {d['shop']} (-{d['cut']}%{', lowest ever' if d['low'] else ''})"
        title = "Wishlist deal" if len(deals) == 1 else f"{len(deals)} wishlist deals"
        body = "\n".join(line(d) for d in deals[:5]) + (f"\nand {len(deals) - 5} more" if len(deals) > 5 else "")
        self.toast.emit(f"{title}: {line(deals[0])}" + (f" and {len(deals) - 1} more" if len(deals) > 1 else ""))
        if shutil.which("notify-send"):
            QProcess.startDetached("notify-send", ["--app-name=Cornerplay", "--icon=cornerplay", title, body])

    def _wishlist_sales(self):
        owned = {covers.norm(g.title) for g in self.model.games}
        return [w for w in self._wishlist
                if (w.get("discount") or (w.get("best") or {}).get("cut")) and covers.norm(w["title"]) not in owned]

    wishlistSales = Property("QVariantList", _wishlist_sales, notify=wishlistChanged)

    @Slot()
    def hideEpicFreeForNow(self):
        """Hide Free on Epic until this week's offers end (it comes back with the next ones)."""
        ends = [g.get("end", 0) for g in self._epic_free if g.get("now")]
        settings.set("epic_free_hidden_until", int(max(ends)) if ends else int(time.time() + 7 * 86400))
        self.settingsChanged.emit()
        self.epicFreeChanged.emit()

    # --- animated art (TV mode) ----------------------------------------------------
    animatedArtReady = Signal(str, "QVariantMap")

    @Slot(str, result="QVariantMap")
    def animatedArt(self, key):
        """Animated cover and banner (SteamGridDB, needs its key); {} until known."""
        sgdb = settings.get("steamgriddb_key").strip()
        g = self.model.find(key)
        if not sgdb or not g or g.id == "battlenet-app" or not settings.get("tv_animated"):
            return {}
        hit = covers.animated_cached(key)
        if hit is not None:
            return hit
        pend = "anim:" + key
        if pend not in self._details_pending:
            self._details_pending.add(pend)

            def work():
                d = covers.animated(key, g.title, _appid(g), sgdb) or {}
                return lambda: (self._details_pending.discard(pend), self.animatedArtReady.emit(key, d))
            self._bg(work)
        return {}

    # --- achievements (Steam) --------------------------------------------------
    @Slot(str, result="QVariantMap")
    def achievements(self, key):
        """Steam or GOG achievement progress for a game; {} until known (achievementsReady follows)."""
        g = self.model.find(key)
        if g and g.store == "gog":
            hit = achievements.cached("gog:" + g.id)
            if hit is not None:
                return hit
            pend = "ach:" + key
            if pend not in self._details_pending and self.stores["gog"].logged_in():
                self._details_pending.add(pend)

                def gog_work():
                    d = achievements.gog_fetch(self.stores["gog"], g.id) or {}
                    return lambda: (self._details_pending.discard(pend), self.achievementsReady.emit(key, d))
                self._bg(gog_work)
            return {}
        key_, steamid = settings.get("steam_api_key").strip(), settings.get("steam_id").strip()
        if not g or g.store != "steam" or not key_:
            return {}
        if not steamid:
            steamid = self.stores["steam"]._recent_user()[0] or ""
        if not steamid:
            return {}
        hit = achievements.cached(g.id)
        if hit is not None:
            return hit
        pend = "ach:" + key
        if pend not in self._details_pending:
            self._details_pending.add(pend)

            def work():
                d = achievements.fetch(g.id, key_, steamid) or {}
                return lambda: (self._details_pending.discard(pend), self.achievementsReady.emit(key, d))
            self._bg(work)
        return {}

    # --- Blizzard account (owned Battle.net games) -------------------------
    BLIZZARD_LOGIN = "https://account.battle.net/oauth2/authorization/account-settings"

    blizzardLinked = Property(bool, lambda s: battlenet.owned() is not None, notify=storesChanged)

    @Slot()
    def blizzardLink(self):
        if not self.web_login:
            self.toast.emit("Linking a Blizzard account needs Qt WebEngine (sudo pacman -S qt6-webengine)")
            return
        self.loginWeb.emit("blizzard", "Blizzard", self.BLIZZARD_LOGIN)

    @Slot(str)
    def blizzardOwned(self, payload):
        """The hidden page read the account's games: keep them and show the new ones."""
        import json
        try:
            raw = json.loads(payload)
        except ValueError:
            return self.blizzardFailed("Blizzard sent something Cornerplay could not read")
        first = battlenet.owned() is None
        games = battlenet.save_owned(raw)
        if first:
            self.loginDone.emit("blizzard", True, f"Blizzard account linked: {len(games)} games found")
        self.refresh("battlenet")

    @Slot(str)
    def blizzardFailed(self, reason):
        if battlenet.owned() is None:
            self.loginDone.emit("blizzard", False, reason)  # still in the sign-in window
        elif "expired" in reason:
            if battlenet.mark_expired():  # told once; Accounts keeps saying it
                self.toast.emit("Battle.net: Blizzard wants your password again to update your owned games. "
                                "Your games stay listed; Accounts > Battle.net > Link account when you like.")
            self.storesChanged.emit()
        else:
            self.toast.emit(f"Battle.net: {reason}")

    @Slot(QObject)
    def blizzardClearCookies(self, profile):
        try:
            profile.cookieStore().deleteAllCookies()
            profile.clearHttpCache()
        except (AttributeError, RuntimeError):
            pass

    @Slot()
    def blizzardUnlink(self):
        battlenet.forget_owned()
        self.blizzardForget.emit()
        self.toast.emit("Blizzard account unlinked")
        self.refresh("battlenet")

    @Slot()
    def refreshArtwork(self):
        """Forget the remembered art (Steam's asset list, title lookups, GOG art, Epic's game
        data age) and refresh every store, so the newest covers, banners and logos come in."""
        from .stores import gog
        for f in (covers.ASSETS_FILE, covers.CACHE_FILE, gog.META_FILE, CACHE_DIR / "epic_full_refresh.json"):
            try:
                f.unlink()
            except OSError:
                pass
        self.toast.emit("Fetching the newest artwork from every store…")
        self.refresh()

    @Slot()
    def windowActivated(self):
        """Cheap catch-up when the window gets focus: wallpaper (for desktops without a watched file)."""
        if settings.get("theme_mode") == "ryoku":
            self._wall_pending.start()
        self.refreshLocal()

    @Slot()
    def refreshLocal(self):
        """Cheap rescan when the window regains focus (Steam / Battle.net change outside Cornerplay)."""
        if time.time() - self._last_local > 30 and not self._pending:
            self._last_local = time.time()
            self.refresh("steam")
            self.refresh("battlenet")

    def _fetch(self, store, force=False):
        games, error = None, ""
        try:
            if store.id in ("epic", "amazon") and store.problem():
                games = []
            elif force and store.id == "epic":
                games = store.fetch(force=True)
            else:
                games = store.fetch()
        except PartialResult as e:
            games, error = e.games, str(e)
        except StoreError as e:
            error = f"{store.name}: {e}"
        except Exception as e:
            error = f"{store.name}: {type(e).__name__}: {e}"
        error = redact(error)
        if games:
            try:
                error = error or covers.fill(games)
            except Exception as e:  # cover art is never worth failing a refresh
                error = error or redact(f"Cover lookup: {type(e).__name__}: {e}")
        self._fetched.emit(store.id, games, error)
        # The library is on screen now. Backup covers, banners and logos can take a while the
        # first time (each game is matched to Steam once), so they fill in afterwards.
        if games:
            try:
                covers.add_backup_art(games)
            except Exception:
                pass
            try:  # ratings use the Steam matches made just above
                protondb.refresh(_appid(g) for g in games if g.id != "battlenet-app")
            except Exception:
                pass
            self._after.emit(self._art_added)

    def _art_added(self):
        self.model.touch()
        self.storesChanged.emit()
        write_json(LIBRARY_CACHE, [g.to_dict() for g in self.model.games])

    def _load_couch(self):
        """Which games have local or split-screen multiplayer (couch.py), off the main thread."""
        st = self.stores.get("steam")
        if not st or self.demo:
            return

        def work():
            couch.load(st.root())
            return lambda: (self.proxy.invalidate(), self.tvProxy.invalidate(), self.tvNextProxy.invalidate(),
                            self.storesChanged.emit())
        self._bg(work)

    def _on_fetched(self, store_id, games, error):
        self._pending.discard(store_id)
        if games:
            shelves.note(store_id, [g.key for g in games])
        if store_id == "epic":
            self.epicFreeChanged.emit()  # "In your library" marks
        if store_id == "steam":
            self._load_couch()
        if games is not None and self.model.replace_store(store_id, games):
            write_json(LIBRARY_CACHE, [g.to_dict() for g in self.model.games])
        if error:
            self.toast.emit(error)
        self.refreshingChanged.emit()
        self.storesChanged.emit()
        self.gameChanged.emit("")
        if not self._pending:
            QTimer.singleShot(20000, self._prefetch_details)  # after the library settles; slow, in the background
            QTimer.singleShot(45000, self._refresh_save_index)
            self.checkSteamShortcut()
            self._auto_steam()
            self._announce_updates()

    def _announce_updates(self):
        """One toast per newly found update (not again on every refresh)."""
        found = {g.key: g.title for g in self.model.games if g.installed and g.extra.get("update")
                 and not game_options.get(g.key).get("hidden")}
        new = [t for k, t in found.items() if k not in self._updates_seen]
        self._updates_seen = set(found)
        if len(new) == 1:
            self.toast.emit(f"Update available: {new[0]}")
        elif new:
            self.toast.emit(f"{len(new)} game updates available")

    # --- sign-in ---------------------------------------------------------
    def _bg(self, fn):
        """Run fn on a worker; it returns a callable to run back on the UI thread."""
        def work():
            try:
                done = fn()
            except StoreError as e:
                done = lambda msg=str(e): self.toast.emit(msg)
            except Exception as e:
                done = lambda msg=f"{type(e).__name__}: {e}": self.toast.emit(msg)
            if done:
                self._after.emit(done)
        self.pool.submit(work)

    web_login = False  # set by __main__ when Qt's web engine is available

    @Slot(str)
    @Slot(str, bool)
    def loginBegin(self, store_id, browser=False):
        """browser=True forces the old open-in-browser-and-paste flow."""
        store = self.stores[store_id]

        def work():
            info = store.login_begin()
            if "command" in info:
                def start():
                    self._detach(info["command"], info.get("env", {}), "", f"{store_id}-client")
                    self.toast.emit(f"Opening {store.name}; sign in there, then press Refresh")
                return start
            if self.web_login and not browser:
                return lambda: self.loginWeb.emit(store_id, store.name, info["url"])
            return lambda: (self.loginReady.emit(store_id, info["url"], info["prompt"]))
        self._bg(work)

    @Slot(str, str)
    def loginFinish(self, store_id, text):
        store = self.stores[store_id]

        def work():
            try:
                store.login_finish(text)
            except StoreError as e:
                return lambda msg=str(e): self.loginDone.emit(store_id, False, msg)

            def ok():
                self.loginDone.emit(store_id, True, f"Signed in to {store.name}")
                self.refresh(store_id)
            return ok
        self._bg(work)

    @Slot(str)
    def logout(self, store_id):
        store = self.stores[store_id]

        def work():
            store.logout()
            return lambda: (self.toast.emit(f"Signed out of {store.name}"), self.refresh(store_id))
        self._bg(work)

    # --- games -----------------------------------------------------------
    @Slot(str, result="QVariantMap")
    def game(self, key):
        return self.model.as_dict(key)

    @Slot(result="QVariantList")
    def jobList(self):
        """Installs, updates and the like under way or waiting, for TV mode's quick access."""
        out = []
        for key, job in list(self.model.jobs.items()):
            g = self.model.as_dict(key)
            out.append({"key": key, "title": g.get("title") or key, "job": job.get("kind", ""),
                        "progress": float(job.get("progress", -1.0)), "detail": job_detail(job)})
        return out

    def _env(self, extra):
        env = QProcessEnvironment.systemEnvironment()
        for k, v in extra.items():
            env.insert(k, v)
        return env

    def _detach(self, argv, env, cwd, log_name):
        p = QProcess()
        p.setProgram(argv[0])
        p.setArguments(argv[1:])
        p.setProcessEnvironment(self._env(env))
        if cwd and os.path.isdir(cwd):
            p.setWorkingDirectory(cwd)
        log = str(LOG_DIR / (re.sub(r"[^A-Za-z0-9_.-]", "_", log_name) + ".log"))
        p.setStandardOutputFile(log)
        p.setStandardErrorFile(log)
        result = p.startDetached()
        return result[0] if isinstance(result, tuple) else bool(result)

    cloudSaveStores = Property("QVariantList", lambda s: list(saves.SUPPORTED), constant=True)
    hasGamescope = Property(bool, lambda s: bool(shutil.which("gamescope")), constant=True)
    languages = Property("QVariantList", lambda s: [{"label": n, "value": c} for c, n in LANGUAGES.items()], constant=True)
    retroProblem = Property(str, lambda s: s.stores["retro"].problem(), notify=settingsChanged)

    @Slot(str)
    def addRomFolder(self, url):
        path = QUrl(url).toLocalFile() if url.startswith("file:") else url
        if not path or not os.path.isdir(path):
            return
        dirs = [d for d in (settings.get("rom_dirs") or []) if d != path] + [path]
        settings.set("rom_dirs", dirs)
        self.settingsChanged.emit()
        self.refresh("retro")

    def _light(self):
        """Light mode skips per-cover GPU effects, blur and animations, for older PCs."""
        mode = settings.get("performance")
        if mode in ("light", "full"):
            return mode == "light"
        try:
            ram_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
        except (ValueError, OSError):
            ram_gb = 8
        from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
        software = QQuickWindow.graphicsApi() == QSGRendererInterface.GraphicsApi.Software
        return software or (os.cpu_count() or 2) <= 2 or ram_gb < 6

    light = Property(bool, lambda s: s._per_settings["light"] if "light" in s._per_settings
                     else s._per_settings.setdefault("light", s._light()), notify=settingsChanged)

    def _guard(self, key):
        g = self.model.find(key)
        if not g:
            return None, None
        if self.demo:
            self.toast.emit("Demo mode: nothing is really launched or installed")
            return None, None
        return g, self.stores[g.store]

    @Slot(result="QVariantMap")
    def battery(self):
        """The first battery's charge (Steam Deck, laptops) for TV mode's top bar; {} on desktops."""
        for dev in sorted(Path("/sys/class/power_supply").glob("*")):
            try:
                if (dev / "type").read_text().strip() != "Battery" or (dev / "scope").exists():
                    continue  # "scope" marks a controller's or mouse's battery
                level = int((dev / "capacity").read_text().strip())
                status = (dev / "status").read_text().strip()
            except (OSError, ValueError):
                continue
            return {"level": level, "charging": status in ("Charging", "Full")}
        return {}

    @Slot(str, result=str)
    def launchTarget(self, key):
        """Which copy Play should start: the only installed one, or the user's pick. "" = ask."""
        group = self.model.group_of(key)
        installed = [g.key for g in group if g.installed]
        if len(installed) == 1:
            return installed[0]
        if group and installed:
            prefer = game_options.get(self.model.group_id(group[0])).get("prefer", "")
            if prefer in installed:
                return prefer
        return ""

    @Slot(str, bool)
    def setHidden(self, key, hidden):
        """Hide or show a game; every store's copy of it goes together."""
        group = self.model.group_of(key)
        for g in group:
            # Unhiding a game Steam hides stores False, so it stays shown here (Steam is not changed).
            game_options.set(g.key, "hidden", True if hidden else (False if g.extra.get("steam_hidden") else None))
        self.proxy.refilter()
        self.storesChanged.emit()
        self.gameChanged.emit(key)
        title = group[0].title if group else "Game"
        self.toast.emit(f"{title} hidden. Find it under Hidden games." if hidden else f"{title} is back in your library")

    # --- people and sync ------------------------------------------------------------
    profilesChanged = Signal()
    syncChanged = Signal()

    profiles = Property("QVariantList", lambda s: personal.profiles(), notify=profilesChanged)
    profile = Property(str, lambda s: personal.current(), notify=profilesChanged)

    def _personal_reloaded(self):
        self.model.played = playtime.load()
        self.model.generation += 1
        self._refilter_all()
        self.profilesChanged.emit()

    @Slot(str)
    def switchProfile(self, name):
        if name == personal.current():
            return
        personal.switch(name)
        self._personal_reloaded()
        self.toast.emit(f"Hi {name}: your favourites, collections and stats")

    # --- play on another screen (stream.py) ----------------------------------------------
    @Slot()
    def addToSunshine(self):
        """This PC hosts: TV mode and your favourites (else your recently played, installed games)
        in Sunshine's app list, for Moonlight on the TV, the laptop or the Deck."""
        m = self.model
        groups = [g for g in m.groups if not m.is_hidden(g) and any(x.installed for x in g)]
        favs = [g for g in groups if shelves.in_group(g, shelves.FAV)]
        pick = favs or sorted(groups, key=lambda g: -m.group_value(g, "lastPlayed"))[:12]
        games = [{"key": self.launchTarget(m.rep(g).key) or m.rep(g).key, "title": m.rep(g).title} for g in pick]
        icon = str(Path(__file__).parent / "icons" / "app" / "cornerplay-256.png")

        def work():
            from . import stream
            try:
                n = stream.add_to_sunshine(games, icon if os.path.exists(icon) else "")
            except Exception as e:  # unreadable JSON, no permission, the host's shell failing
                return lambda msg=str(e): self.toast.emit(f"Not added to Sunshine: {msg}")
            what = "Cornerplay's TV mode" + (f" and {n - 1} game{'s' if n > 2 else ''}" if n > 1 else "")
            return lambda: self.toast.emit(f"Added {what} to Sunshine. Restart Sunshine to see them in Moonlight.")
        self._bg(work)

    @Slot()
    def wakePc(self):
        from . import stream
        mac = str(settings.get("stream_mac") or "").strip()
        try:
            stream.wake(mac)
            self.toast.emit(f"Woke {settings.get('stream_pc') or 'the gaming PC'} (it can take a few seconds to start)")
        except (ValueError, OSError) as e:
            self.toast.emit(f"Could not wake it: {e}")

    @Slot()
    def streamFromPc(self):
        """Wake the gaming PC (when its MAC address is set) and stream its Cornerplay TV mode."""
        pc = str(settings.get("stream_pc") or "").strip()
        mac = str(settings.get("stream_mac") or "").strip()

        def work():
            from . import stream
            if mac:
                try:
                    stream.wake(mac)
                except (ValueError, OSError):
                    pass
            try:
                cmd = stream.stream_argv(pc)
            except RuntimeError as e:
                return lambda msg=str(e): self.toast.emit(msg)

            def start():
                if QProcess.startDetached(cmd[0], cmd[1:])[0]:
                    self.toast.emit(f"Streaming from {pc}…")
                else:
                    self.toast.emit("Moonlight did not start")
            return start
        self._bg(work)

    # --- TV mode's power menu ---------------------------------------------------------
    @Slot(str)
    def power(self, what):
        """Suspend, restart or shut down the PC (TV mode's Guide menu): systemd on the host."""
        verb = {"suspend": "suspend", "restart": "reboot", "shutdown": "poweroff"}.get(what)
        if not verb or self.demo:
            return
        cmd = host.argv(["systemctl", verb])
        if not QProcess.startDetached(cmd[0], cmd[1:])[0]:
            self.toast.emit("Could not ask the PC to " + {"suspend": "sleep", "reboot": "restart", "poweroff": "shut down"}[verb])

    @Slot(str, result=str)
    def addProfile(self, name):
        made = personal.add_profile(name)
        if made:
            self.profilesChanged.emit()
        return made

    @Slot(str)
    def removeProfile(self, name):
        if personal.remove_profile(name):
            self._personal_reloaded()

    def _sync_info(self):
        last = personal.last_sync()
        return {"dir": settings.get("sync_dir"), "error": last["error"], "busy": self._syncing,
                "when": time.strftime("%H:%M", time.localtime(last["t"])) if last["t"] else ""}

    _syncing = False
    syncState = Property("QVariantMap", _sync_info, notify=syncChanged)

    @Slot(str)
    def setSyncDir(self, folder):
        folder = QUrl(folder).toLocalFile() if folder.startswith("file:") else folder.strip()
        settings.set("sync_dir", folder)
        self.syncChanged.emit()
        self.syncPersonal()

    @Slot()
    def syncPersonal(self):
        if not settings.get("sync_dir") or self._syncing:
            return
        self._syncing = True
        self.syncChanged.emit()

        def work():
            err = personal.sync()

            def done():
                self._syncing = False
                self._personal_reloaded()
                self.syncChanged.emit()
                if err:
                    self.toast.emit(f"Sync: {err}")
            return done
        self._bg(work)

    def _personal_changed(self):
        """A local change (star, collection, note...): sync it out a few seconds later."""
        if settings.get("sync_dir"):
            if not hasattr(self, "_sync_soon"):
                self._sync_soon = QTimer(self, singleShot=True, interval=4000)
                self._sync_soon.timeout.connect(self.syncPersonal)
            self._after.emit(self._sync_soon.start)  # from any thread, onto the UI thread

    # --- favourites and collections ---------------------------------------
    collectionsChanged = Signal()

    def _refilter_all(self, key=None):
        self.proxy.refilter()
        self.tvProxy.refilter()
        self.model.touch(key)
        self.collectionsChanged.emit()
        self.storesChanged.emit()  # the sidebar's counts
        if key:
            self.gameChanged.emit(key)

    collections = Property("QVariantList", lambda s: shelves.names(), notify=collectionsChanged)

    @Slot(str, str, bool)
    def setInCollection(self, key, cid, on):
        """cid: "fav" for favourites, else a collection's name."""
        group = self.model.group_of(key)
        if not group:
            return
        shelves.set_member(group, cid, on)
        self._refilter_all(key)

    @Slot(str)
    def toggleFavourite(self, key):
        group = self.model.group_of(key)
        if not group:
            return
        on = not shelves.in_group(group, shelves.FAV)
        self.setInCollection(key, shelves.FAV, on)
        self.toast.emit(f"{group[0].title} {'added to' if on else 'removed from'} Favourites")

    @Slot(str, result=str)
    def createCollection(self, name):
        made = shelves.create(name)
        if made:
            self.collectionsChanged.emit()
            self.storesChanged.emit()  # the sidebar lists collections (it showed a new, empty one only later)
        return made

    @Slot(str)
    def deleteCollection(self, name):
        shelves.delete(name)
        for proxy in (self.proxy, self.tvProxy):
            if proxy.shelf == "c:" + name:
                proxy.shelf = ""
        self._refilter_all()

    @Slot(result="QVariantList")
    def shelfRows(self):
        """The desktop's Shelves view: TV mode's shelves (Continue playing, your lists, Play
        together, ...) and your biggest genres, each with its first games."""
        m = self.model
        groups = [g for g in m.groups if not m.is_hidden(g)]
        tests = {
            "playing": lambda g: m.group_value(g, "lastPlayed") > 0,
            "s:playing": lambda g: shelves.meta(g, "status") == "playing",
            "fav": lambda g: shelves.in_group(g, shelves.FAV),
            "s:want": lambda g: shelves.meta(g, "status") == "want",
            "added": shelves.is_recent,
            "s:finished": lambda g: shelves.meta(g, "status") == "finished",
            "together": lambda g: any(couch.local(_appid(x)) for x in g),
        }
        genres = {}
        for grp in groups:
            for name in {x for g in grp for x in ((details.cached(g.key) or {}).get("genres") or [])}:
                genres[name] = genres.get(name, 0) + 1
        rows = []
        for shelf in self.shelfList():
            sid = shelf["id"]
            if not sid:
                continue
            test = tests.get(sid) or (lambda g, c=sid[2:]: shelves.in_group(g, c))
            rows.append((sid, shelf["name"], "", test))
        for name, n in sorted(genres.items(), key=lambda kv: -kv[1])[:4]:
            if n >= 4:
                rows.append(("", name, "genre:" + name,
                             lambda g, name=name: any(name in ((details.cached(x.key) or {}).get("genres") or []) for x in g)))
        out = []
        for sid, name, tag, test in rows:
            hits = [g for g in groups if test(g)]
            if sid == "playing" or sid == "together":
                hits.sort(key=lambda g: -m.group_value(g, "lastPlayed"))
            elif sid == "added":
                hits.sort(key=lambda g: -shelves.installed_at(g))
            else:
                hits.sort(key=lambda g: m.rep(g).title.lower())
            games = []
            for grp in hits[:24]:
                g = m.rep(grp)
                games.append({"key": g.key, "title": g.title, "covers": _covers(g), "installed": any(x.installed for x in grp)})
            if games:
                out.append({"id": sid, "tag": tag, "name": name, "count": len(hits), "games": games})
        return out

    @Slot(result="QVariantList")
    def shelfList(self):
        """TV mode's rows, in order; empty ones are left out. Library is always there."""
        groups = [g for g in self.model.groups if not self.model.is_hidden(g)]
        out = []

        def add(sid, name, test):
            n = sum(1 for g in groups if test(g))
            if n:
                out.append({"id": sid, "name": name, "count": n})
        add("playing", _t("Continue playing"), lambda g: self.model.group_value(g, "lastPlayed") > 0)
        add("s:playing", _t("Playing"), lambda g: shelves.meta(g, "status") == "playing")
        add("fav", _t("Favourites"), lambda g: shelves.in_group(g, shelves.FAV))
        add("s:want", _t("Want to play"), lambda g: shelves.meta(g, "status") == "want")
        for c in shelves.names():
            add("c:" + c, c, lambda g, c=c: shelves.in_group(g, c))
        add("added", _t("Recently added"), shelves.is_recent)
        add("s:finished", _t("Finished"), lambda g: shelves.meta(g, "status") == "finished")
        add("together", _t("Play together"), lambda g: any(couch.local(_appid(x)) for x in g))
        out.append({"id": "", "name": _t("Library"), "count": len(groups)})
        # Two or more controllers: friends are on the sofa, so games to play together come first.
        pads = len(getattr(getattr(self, "gamepad", None), "_pads", None) or {})
        if pads >= 2:
            out.sort(key=lambda s: s["id"] != "together")
        return out

    def _sidebar_shelves(self):
        """Favourites and the collections, with counts, for the sidebar (shown even when empty)."""
        groups = [g for g in self.model.groups if not self.model.is_hidden(g)]
        out = [{"id": "fav", "name": _t("Favourites"),
                "count": sum(1 for g in groups if shelves.in_group(g, shelves.FAV))}]
        for c in shelves.names():
            out.append({"id": "c:" + c, "name": c, "count": sum(1 for g in groups if shelves.in_group(g, c))})
        return out

    def _sidebar_statuses(self):
        """Backlog statuses that have games, for the sidebar."""
        groups = [g for g in self.model.groups if not self.model.is_hidden(g)]
        counts = {}
        for g in groups:
            st = shelves.meta(g, "status")
            if st:
                counts[st] = counts.get(st, 0) + 1
        return [{"id": "s:" + sid, "name": _t(name), "count": counts[sid]} for sid, name in shelves.STATUSES if counts.get(sid)]

    sidebarStatuses = Property("QVariantList", lambda s: s._once_per_change("statuses", s._sidebar_statuses), notify=storesChanged)

    @Slot(str, str)
    def setStatus(self, key, status):
        group = self.model.group_of(key)
        if group:
            shelves.set_meta(group, "status", status if status in shelves.STATUS_NAMES else "")
            self._refilter_all(key)

    @Slot(str, int)
    def setRating(self, key, stars):
        group = self.model.group_of(key)
        if group:
            shelves.set_meta(group, "rating", max(0, min(5, int(stars))))
            self._refilter_all(key)

    @Slot(str, str)
    def setNote(self, key, text):
        group = self.model.group_of(key)
        if group and text.strip() != (shelves.meta(group, "note") or ""):
            shelves.set_meta(group, "note", text.strip()[:2000])
            self.gameChanged.emit(key)

    statusNames = Property("QVariantList", lambda s: [{"id": i, "name": _t(n)} for i, n in shelves.STATUSES], constant=True)

    @Slot(result="QVariantMap")
    def stats(self):
        """Play stats: totals, per store, most played, and the last weeks from Cornerplay's session log."""
        groups = [g for g in self.model.groups if not self.model.is_hidden(g)]
        rows = []
        for grp in groups:
            secs = self.model.group_value(grp, "playtime")
            rep_ = self.model.rep(grp)
            rows.append((secs, grp, rep_))
        played = [r for r in rows if r[0] > 0]
        per_store = {}
        for secs, grp, rep_ in played:
            name = self.stores[rep_.store].name
            per_store[name] = per_store.get(name, 0) + secs
        top = sorted(played, key=lambda r: -r[0])[:10]
        now = time.time()
        log = playtime.sessions()
        week = sum(e - s for _, s, e in log if e > now - 7 * 86400)
        month = sum(e - s for _, s, e in log if e > now - 30 * 86400)
        days = []  # hours per day, last 14 days (oldest first)
        for d in range(13, -1, -1):
            lo = now - (d + 1) * 86400
            hi = now - d * 86400
            days.append(round(sum(max(0, min(e, hi) - max(s, lo)) for _, s, e in log) / 3600, 2))
        statuses, by_id = {}, {}
        for grp in groups:
            st = shelves.meta(grp, "status")
            if st:
                statuses[shelves.STATUS_NAMES[st]] = statuses.get(shelves.STATUS_NAMES[st], 0) + 1
                by_id[st] = by_id.get(st, 0) + 1
        years = sorted(set(statsdata.years(log)) | {time.localtime(now).tm_year}, reverse=True)
        return {
            "weeks": statsdata.weekly(log, now),
            "backlog": statsdata.backlog(by_id),
            "years": years,
            "year": self.yearStats(years[0]),
            "totalHours": round(sum(r[0] for r in played) / 3600),
            "games": len(groups), "played": len(played), "neverPlayed": len(groups) - len(played),
            "installed": sum(1 for g in groups if any(x.installed for x in g)),
            "weekHours": round(week / 3600, 1), "monthHours": round(month / 3600, 1),
            "sessions": len(log), "days": days,
            "perStore": [{"name": n, "hours": round(v / 3600)} for n, v in sorted(per_store.items(), key=lambda kv: -kv[1])],
            "top": [{"key": r[2].key, "title": r[2].title, "hours": round(r[0] / 3600, 1),
                     "cover": _cover(r[2]), "covers": _covers(r[2])} for r in top],
            "statuses": [{"name": n, "count": c} for n, c in statuses.items()],
        }

    @Slot(int, result="QVariantMap")
    def yearStats(self, year):
        """Your year in Cornerplay. Hours come from the session log; for the current year the
        games played also count those whose last-played date (Steam's too) is this year."""
        titles = {}

        def title_of(key):
            if key not in titles:
                grp = self.model.group_of(key)
                g = self.model.find(key)
                titles[key] = self.model.rep(grp).title if grp else (g.title if g else "")
            return titles[key]
        finished_at, played_now = {}, set()
        lo = time.mktime((year, 1, 1, 0, 0, 0, 0, 0, -1))
        hi = time.mktime((year + 1, 1, 1, 0, 0, 0, 0, 0, -1))
        for grp in self.model.groups:
            if self.model.is_hidden(grp):
                continue
            if shelves.meta(grp, "status") == "finished":
                when = next((personal.get(g.key, "finished_at") for g in grp if personal.get(g.key, "finished_at")), 0)
                if isinstance(when, (int, float)) and when:
                    finished_at[self.model.rep(grp).key] = when
            if year == time.localtime().tm_year and lo <= self.model.group_value(grp, "lastPlayed") < hi:
                played_now.add(self.model.rep(grp).title)
        out = statsdata.year_summary(playtime.sessions(), year, title_of, finished_at)
        if played_now:
            out["games"] = len(played_now | {t["title"] for t in out["top"]} | set(out["newGames"]))
        return out

    # --- your screenshots of a game (screenshots.py) ------------------------------------
    screenshotsReady = Signal(str, "QVariantList")  # key, [{"thumb", "full", "path", "time", "source"}]

    @Slot(str)
    def loadScreenshots(self, key):
        group = self.model.group_of(key) or ([self.model.find(key)] if self.model.find(key) else [])
        if not group or self.demo:
            return
        keys = {g.key for g in group}
        steam = next((g for g in group if g.store == "steam"), None)
        st = self.stores.get("steam")

        def work():
            from . import screenshots
            steam_dir = None
            if steam and st:
                try:
                    sid = settings.get("steam_id").strip() or st._recent_user()[0]
                    steam_dir = screenshots.steam_folder(st.root(), int(sid) - 76561197960265728, steam.id)
                except (TypeError, ValueError):
                    steam_dir = None
            rows = screenshots.for_game(keys, playtime.sessions(), steam_dir)
            out = [{"thumb": QUrl.fromLocalFile(r["path"]).toString(), "full": QUrl.fromLocalFile(r["path"]).toString(),
                    "path": r["path"], "time": r["time"], "source": r["source"]} for r in rows]
            return lambda: self.screenshotsReady.emit(key, out)
        self._bg(work)

    @Slot(str)
    def showInFolder(self, path):
        """The folder a screenshot is in (the file manager selects it where it can)."""
        if not path or not os.path.isfile(path):
            return
        from PySide6.QtDBus import QDBusConnection, QDBusMessage
        msg = QDBusMessage.createMethodCall("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                                            "org.freedesktop.FileManager1", "ShowItems")
        msg.setArguments([[QUrl.fromLocalFile(path).toString()], ""])
        reply = QDBusConnection.sessionBus().call(msg, timeout=3000)
        if reply.type() == QDBusMessage.ErrorMessage:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    sidebarShelves = Property("QVariantList", lambda s: s._once_per_change("shelves", s._sidebar_shelves), notify=storesChanged)

    @Slot(str, bool, str, result="QVariantMap")
    def pickGame(self, length, installed_only, avoid):
        """A game to play: from the backlog first, never Finished or Dropped ones.
        length: "" any, "short" (about an hour), "long". avoid: keys picked a moment ago (comma separated)."""
        import random
        skip = set(filter(None, avoid.split(",")))
        per_game = {}
        for key, start, end in playtime.sessions():
            per_game.setdefault(key, []).append(end - start)
        pool = []
        for grp in self.model.groups:
            if self.model.is_hidden(grp):
                continue
            g = self.model.rep(grp)
            if g.id == "battlenet-app" or g.key in skip or (installed_only and not any(x.installed for x in grp)):
                continue
            status = shelves.meta(grp, "status")
            if status in ("finished", "dropped"):
                continue
            runs = [t for x in grp for t in per_game.get(x.key, [])]
            avg = sum(runs) / len(runs) / 60 if runs else None
            if length == "short" and avg is not None and avg > 75:
                continue
            if length == "long" and avg is not None and avg < 60:
                continue
            played = self.model.group_value(grp, "playtime")
            if status == "want":
                weight, why = 4, "It's on your Want to play list"
            elif status == "playing":
                weight, why = 4, "You're in the middle of it"
            elif not played:
                weight, why = 3, "You haven't started it yet"
            else:
                weight, why = 1, f"You've played {round(played / 3600, 1)} h so far"
            if avg is not None:
                why += f" · usually about {round(avg)} min a session"
            if shelves.in_group(grp, shelves.FAV):
                weight += 1
            pool.append((weight, g.key, why))
        if not pool:
            return {}
        _w, key, why = random.choices(pool, weights=[p[0] for p in pool])[0]
        return dict(self.model.as_dict(key), why=why, poolSize=len(pool))

    def _hidden_count(self):
        return sum(1 for grp in self.model.groups if self.model.is_hidden(grp))

    hiddenCount = Property(int, lambda s: s._once_per_change("hidden", s._hidden_count), notify=storesChanged)

    @Slot(str)
    def preferCopy(self, key):
        g = self.model.find(key)
        if g and len(self.model.group_of(key)) > 1:
            game_options.set(self.model.group_id(g), "prefer", key)
            self._touch(key)

    DLC_TTL = 30 * 60  # a game's DLC list is asked for again after half an hour (or after a DLC install)

    @Slot(str)
    @Slot(str, bool)
    def loadDlcs(self, key, fresh=False):
        g = self.model.find(key)
        if not g:
            return
        store = self.stores[g.store]
        hit = self._dlc_cache.get(key)
        if hit and not fresh and time.time() - hit[0] < self.DLC_TTL:
            self.dlcsReady.emit(key, hit[1], store.dlc_note)
            return

        def work():
            try:
                rows = self._demo_dlcs(g) if self.demo else (store.dlcs(g) or [])
            except StoreError as e:
                return lambda msg=str(e): self.dlcsReady.emit(key, [], msg)
            rank = {"installed": 0, "owned": 1, "missing": 2, "available": 3}
            rows.sort(key=lambda r: (rank.get(r["status"], 3), r["title"].lower()))

            def done():
                self._dlc_cache[key] = (time.time(), rows)
                self.dlcsReady.emit(key, rows, store.dlc_note)
            return done
        self._bg(work)

    @Slot(str, str)
    def installDlc(self, key, dlc_id):
        """Install one owned DLC; it runs as a job on the game, with progress like an install."""
        g, store = self._guard(key)
        if not g or key in self.procs:
            return
        try:
            with runner.using(self._options_for(g)):
                cmd = store.install_dlc(g, dlc_id)
        except StoreError as e:
            self.toast.emit(str(e))
            return
        self._dlc_cache.pop(key, None)
        self._start_job(g, "dlc", cmd)

    @staticmethod
    def _demo_dlcs(g):
        cdn = "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps"
        return [{"id": "1", "title": f"{g.title}: Expansion Pass", "status": "installed", "image": f"{cdn}/2778580/header.jpg",
                 "price": "", "url": "", "canInstall": False},
                {"id": "2", "title": f"{g.title}: Bonus Outfits", "status": "owned", "image": f"{cdn}/2778590/header.jpg",
                 "price": "", "url": "", "canInstall": True},
                {"id": "3", "title": f"{g.title}: Original Soundtrack", "status": "available", "image": f"{cdn}/3655690/header.jpg",
                 "price": "€9.99 (-30%)", "url": "https://store.steampowered.com", "canInstall": False}]

    def _options_for(self, g):
        # Battle.net games all run through the one launcher prefix, so they share its options.
        return game_options.get("battlenet:battlenet-app" if g.store == "battlenet" else g.key)

    @Slot(str, result="QVariantMap")
    def gameOptions(self, key):
        return game_options.get(key)

    @Slot(str)
    def verifyGame(self, key):
        g, store = self._guard(key)
        if not g or key in self.procs:
            return
        try:
            cmd = store.verify(g)
        except StoreError as e:
            self.toast.emit(str(e))
            return
        self._start_job(g, "verify", cmd)

    @Slot(str)
    def resetPrefix(self, key):
        """Put the game's Proton prefix aside (renamed, not deleted); the next start makes a new one."""
        g = self.model.find(key)
        if not g:
            return
        path = runner.prefix_path(g.store, "launcher" if g.store == "battlenet" else g.id)
        if not os.path.isdir(path):
            self.toast.emit(f"{g.title} has no Proton prefix yet")
            return
        aside = f"{path}.old-{time.strftime('%Y%m%d-%H%M%S')}"
        os.rename(path, aside)
        self.toast.emit(f"Fresh Proton prefix for {g.title}; the old one is at {aside}")

    @Slot(str)
    def openLog(self, key):
        log = LOG_DIR / (re.sub(r"[^A-Za-z0-9_.-]", "_", key) + ".log")
        if not log.exists():
            logs = sorted(LOG_DIR.glob(re.sub(r"[^A-Za-z0-9_.-]", "_", key) + ".*log"), key=lambda p: -p.stat().st_mtime)
            log = logs[0] if logs else None
        if log:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log)))
        else:
            self.toast.emit("No log yet: it is written when the game runs")

    @Slot(str, str, "QVariant")
    def setGameOption(self, key, name, value):
        if isinstance(value, str):
            value = value.strip()
            if name == "cover" and value.startswith("file://"):
                value = QUrl(value).toLocalFile()
        game_options.set(key, name, value)
        self._touch(key)

    def _proton_versions(self):
        versions = runner.proton_versions()
        current = settings.get("proton")
        if current not in [v["value"] for v in versions]:
            versions.append({"label": f"Custom: {current}", "value": current})
        return versions

    protonsChanged = Signal()
    protonVersions = Property("QVariantList", _proton_versions, notify=protonsChanged)
    geStatusChanged = Signal()

    def _ge_status(self):
        return self._ge

    geStatus = Property("QVariantMap", _ge_status, notify=geStatusChanged)

    def _set_ge(self, **values):
        self._ge = dict(self._ge, **values)
        self.geStatusChanged.emit()

    # Proton-CachyOS: the same as GE, from CachyOS's GitHub releases (v3 build on newer CPUs).
    cachyStatusChanged = Signal()
    _cachy = {"latest": "", "installed": "", "busy": False, "progress": 0.0, "error": "", "upToDate": False}
    cachyStatus = Property("QVariantMap", lambda s: s._cachy, notify=cachyStatusChanged)

    def _set_cachy(self, **values):
        self._cachy = dict(self._cachy, **values)
        self.cachyStatusChanged.emit()

    @Slot()
    def checkCachy(self):
        def work():
            try:
                tag, url, _ = proton.latest_cachyos()
            except Exception as e:
                return lambda msg=f"Could not check: {type(e).__name__}": self._set_cachy(error=msg)
            stem = os.path.basename(url).removesuffix(".tar.xz")
            have = proton.installed_cachyos()
            return lambda: self._set_cachy(latest=tag.replace("cachyos-", ""), installed=have[0] if have else "",
                                           error="", upToDate=stem in have)
        self._bg(work)

    @Slot()
    def downloadCachy(self):
        if self._cachy.get("busy"):
            return
        self._set_cachy(busy=True, progress=0.0, error="")

        def report(pct):
            self._after.emit(lambda: self._set_cachy(progress=pct))

        def work():
            try:
                name, fresh = proton.download_cachyos(report)
            except Exception as e:
                return lambda msg=str(e)[:160]: (self._set_cachy(busy=False, error=msg), self.toast.emit("Proton-CachyOS download failed"))

            def done():
                self._set_cachy(busy=False, installed=name, upToDate=True, progress=100.0)
                self.protonsChanged.emit()
                self.toast.emit(f"{name} installed: pick it under Proton version" if fresh else f"{name} is already the newest")
            return done
        self._bg(work)

    @Slot()
    def checkGe(self):
        """Look up the newest GE-Proton (one small GitHub request)."""
        def work():
            try:
                tag, _, _ = proton.latest_ge()
            except Exception as e:
                return lambda msg=f"Could not check: {type(e).__name__}": self._set_ge(error=msg)
            have = proton.installed_ge()
            return lambda: self._set_ge(latest=tag, installed=have[0] if have else "", error="",
                                        upToDate=bool(have) and have[0].startswith(tag))
        self._bg(work)

    @Slot()
    def downloadGe(self):
        if self._ge.get("busy"):
            return
        self._set_ge(busy=True, progress=0.0, error="")

        def report(pct):
            self._after.emit(lambda: self._set_ge(progress=pct))

        def work():
            try:
                name, fresh = proton.download_ge(report)
            except Exception as e:
                return lambda msg=str(e)[:160]: (self._set_ge(busy=False, error=msg), self.toast.emit("GE-Proton download failed"))

            def done():
                self._set_ge(busy=False, installed=name, upToDate=True, progress=100.0)
                self.protonsChanged.emit()
                self.toast.emit(f"{name} installed" if fresh else f"{name} is already the newest")
            return done
        self._bg(work)

    @Slot()
    def getSteamProton(self):
        """Ask Steam to install Proton Experimental; it then shows up in the list."""
        steam = self.stores["steam"]
        client = steam.client()
        if not client:
            self.toast.emit("Steam is not installed")
            return
        self._detach([*client, f"steam://install/{proton.PROTON_EXPERIMENTAL_APPID}"], {}, "", "steam-proton")
        self.toast.emit("Steam is installing Proton Experimental; it appears in this list when done")

    steamShortcutChanged = Signal()

    def _shortcut_status(self):
        return self._shortcut

    steamShortcut = Property("QVariantMap", _shortcut_status, notify=steamShortcutChanged)

    def _steam_candidates(self):
        return [g for g in self.model.games if steamgames.eligible(g)
                and not game_options.get(g.key).get("hidden")]

    def _set_shortcut(self, **values):
        self._shortcut = dict(self._shortcut, **values)
        self.steamShortcutChanged.emit()

    @Slot()
    def checkSteamShortcut(self):
        wanted = {g.key for g in self._steam_candidates()}

        def work():
            st = steamshortcut.status()
            have = steamgames.in_steam_keys()
            return lambda: self._set_shortcut(**st, games=len(wanted), gamesInSteam=len(wanted & have),
                                              inSync=bool(st["accounts"]) and have == wanted)
        self._bg(work)

    def _steam_job(self, fn, start_msg):
        """Run fn (which edits Steam's files) with Steam closed; reopen Steam if it was open."""
        if self.demo:
            self.toast.emit("Demo mode: Steam is not changed")
            return
        if steamshortcut.in_game_mode():
            self.toast.emit("Switch to Desktop Mode to change Steam's library")
            return
        self._set_shortcut(busy=True, progress="")
        self.toast.emit(("Closing Steam… " if steamshortcut.steam_running() else "") + start_msg)

        def work():
            was_running = steamshortcut.steam_running()
            try:
                if was_running and not steamshortcut.close_steam():
                    raise RuntimeError("Steam did not close; quit it yourself and try again")
                msg = fn()
            except Exception as e:
                msg = str(e)
            finally:
                if was_running:
                    steamshortcut.start_steam()
            return lambda: (self._set_shortcut(busy=False, progress=""), self.toast.emit(msg), self.checkSteamShortcut())
        self._bg(work)

    @Slot(str, result="QVariantMap")
    def steamProton(self, key):
        """{"choices", "current"} for a Steam game's Proton picker (Steam's own per-game setting)."""
        g = self.model.find(key)
        root = self.stores["steam"].root()
        if not g or g.store != "steam" or not root:
            return {"choices": [], "current": ""}
        return {"choices": steamcompat.choices(str(root)), "current": steamcompat.current(str(root), g.id)}

    @Slot(str, str)
    def setSteamProton(self, key, name):
        """Set which Proton Steam runs this game with ("" = Steam decides). Closes Steam meanwhile."""
        g = self.model.find(key)
        root = self.stores["steam"].root()
        if not g or g.store != "steam" or not root:
            return
        label = next((c["label"] for c in steamcompat.choices(str(root)) if c["value"] == name), name)

        def fn():
            steamcompat.set_tool(str(root), g.id, name)
            return (f"{g.title} now runs with {label}. Steam downloads it the first time if needed."
                    if name else f"{g.title} uses Steam's choice of Proton again")
        self._steam_job(fn, f"Setting {g.title} to {label or 'Steam default'}…")

    @Slot()
    def addGamesToSteam(self):
        """Add every installed (not hidden) Epic, GOG, Amazon and Battle.net game to Steam with artwork."""
        games = self._steam_candidates()

        def report(n, total):
            self._after.emit(lambda: self._set_shortcut(progress=f"{n} of {total}"))

        def fn():
            added, removed = steamgames.sync_games(games, progress=report)
            parts = [f"{added} games are in Steam with artwork"] + ([f"{removed} removed"] if removed else [])
            return ", ".join(parts) + ". Find them in Game Mode under Non-Steam."
        self._steam_job(fn, f"Adding {len(games)} games to Steam and fetching their artwork…")

    @Slot()
    def addToSteam(self):
        """Add Cornerplay itself (opens in TV mode)."""
        theme = dict(self._theme)
        self._steam_job(lambda: f"Cornerplay is in Steam ({steamshortcut.add(theme)} account(s))",
                        "Adding Cornerplay to Steam…")

    def _auto_steam(self):
        """With the setting on: bring Steam's list in line with installed games, only while Steam is closed."""
        if self.demo or not settings.get("steam_games") or self._shortcut.get("busy"):
            return
        games = self._steam_candidates()

        def work():
            if steamshortcut.steam_running() or steamshortcut.in_game_mode() or not steamshortcut.accounts():
                return None
            if steamgames.in_steam_keys() == {g.key for g in games}:
                return None
            try:
                added, removed = steamgames.sync_games(games)
            except Exception:
                return None
            return lambda: (self.toast.emit(f"Steam library updated ({added} games)"), self.checkSteamShortcut())
        self._bg(work)

    @Slot()
    def rescanProtons(self):
        self.protonsChanged.emit()

    @Slot(str)
    def play(self, key):
        self._play(key, "download")

    @Slot(str, str)
    def resolveConflict(self, key, choice):
        """After a save conflict: "cloud", "local", or "skip" (play without syncing)."""
        self._play(key, {"cloud": "force-download", "local": "force-upload"}.get(choice, "skip"))

    @Slot(str)
    def syncNow(self, key):
        g = self.model.find(key)
        if not g or self.demo:
            return

        def work():
            res = saves.sync(g, "both")
            if res["status"] == "conflict":
                return lambda: self.saveConflict.emit(key, res["local"], res["cloud"])
            return lambda: self.toast.emit(f"{g.title}: {res['message']}")
        self.toast.emit(f"Syncing saves for {g.title}…")
        self._bg(work)

    def _vulkan_warning(self, g):
        """Before a Proton game: say so when the GPU has no Vulkan driver (it would just crash)."""
        if g.store in ("epic", "gog", "amazon", "battlenet", "custom", "itch") and g.extra.get("platform") != "linux":
            msg = runner.vulkan_problem()
            if msg:
                self.toast.emit(msg)
                return True
        return False

    # The launch card in the window: "start" (getting ready), then "ok" or "fail"; "cancel" when a
    # save conflict needs an answer first.
    launching = Signal(str, str)
    _starting = {}  # key -> when its launch began (or succeeded): a second press then starts nothing
    START_GRACE = 12  # seconds a game gets to show its window before Play starts another copy

    def _launch_state(self, key, state):
        if state == "start" or state == "ok":
            self._starting[key] = time.monotonic()
        else:
            self._starting.pop(key, None)
        self.launching.emit(key, state)

    def _play(self, key, mode):
        g, store = self._guard(key)
        if not g:
            return
        began = self._starting.get(key)
        if began is not None and time.monotonic() - began < self.START_GRACE:
            self.toast.emit(f"{g.title} is already starting")
            return
        self._launch_state(key, "start")
        self._vulkan_warning(g)  # warn, but still try: the check should never stop a game that would run
        opts = self._options_for(g)
        sync = saves.enabled_for(g) and mode != "skip"
        if sync:
            self.toast.emit(f"Syncing saves for {g.title}…")

        def work():
            if sync:
                res = saves.sync(g, mode)
                if res["status"] == "conflict":
                    return lambda: (self._launch_state(key, "cancel"), self.saveConflict.emit(key, res["local"], res["cloud"]))
                if res["status"] == "error":
                    self._worker_toast.emit(f"{g.title}: {res['message']} (launching anyway)")
            if settings.get("save_backups") and g.id != "battlenet-app":
                try:  # never let a backup stop the game from starting
                    if savebackup.backup(g, _appid(g)):
                        self._worker_toast.emit(f"Saves of {g.title} backed up")
                except Exception:
                    pass
            try:
                with runner.using(opts):
                    cmd = store.launch(g)
            except Exception as e:  # a store said no (sign-in expired, files missing): say so at once
                msg = str(e) or type(e).__name__
                return lambda: (self._launch_state(key, "fail"), self.toast.emit(f"Could not start {g.title}: {msg}"))
            if opts.get("args") and g.store in ("epic", "gog", "amazon", "custom", "itch"):
                cmd.argv += shlex.split(opts["args"])
            return lambda: self._start(g, cmd, saves.enabled_for(g))
        self._bg(work)

    def _start(self, g, cmd, sync):
        log = str(LOG_DIR / (re.sub(r"[^A-Za-z0-9_.-]", "_", g.key) + ".log"))
        if g.store in saves.SUPPORTED or g.store in playtime.TIMED:
            job = CACHE_DIR / f"sessions/job-{os.getpid()}-{int(time.time() * 1000)}.json"
            write_json(job, {"game": g.to_dict(), "argv": cmd.argv, "env": cmd.env, "cwd": cmd.cwd,
                             "log": log, "sync": sync})
            pkg_root = str(Path(__file__).resolve().parent.parent)
            env = dict(cmd.env)
            env["PYTHONPATH"] = pkg_root + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
            ok = self._detach([sys.executable, "-m", "cornerplay.session", str(job)], env, "", g.key + ".session")
        else:
            ok = self._detach(cmd.argv, cmd.env, cmd.cwd, g.key)
        self._launch_state(g.key, "ok" if ok else "fail")
        if not ok:
            self.toast.emit(f"Could not start {g.title} (log: {LOG_DIR})")

    # --- now playing ------------------------------------------------------------
    nowPlayingChanged = Signal()
    _playing = {}  # key -> {"title", "since", "pid"}

    _steam_playing = {}  # "steam:<appid>" -> {"title", "since", "steam": True}
    _steam_checking = False

    def _now_playing(self):
        return [dict(v, key=k) for k, v in self._playing.items()] + \
               [dict(v, key=k) for k, v in self._steam_playing.items() if k not in self._playing]

    def _check_steam_running(self):
        if self._steam_checking or "steam" not in self.stores:
            return
        self._steam_checking = True

        def work():
            try:
                ids = steamrun.running()
            except Exception:
                ids = None

            def apply():
                self._steam_checking = False
                if ids is None:
                    return
                now = time.time()
                keys = {f"steam:{i}" for i in ids}
                changed = False
                for key in keys - set(self._steam_playing):
                    g = self.model.find(key)
                    self._steam_playing[key] = {"title": g.title if g else "A Steam game", "since": now, "steam": True}
                    changed = True
                for key in set(self._steam_playing) - keys:
                    info = self._steam_playing.pop(key)
                    changed = True
                    try:
                        playtime.record(key, info["since"], now, log_only=True)
                    except OSError:
                        pass
                    self._recap(key, now - info["since"])
                if changed:
                    self.nowPlayingChanged.emit()
            return apply
        self._bg(work)

    nowPlaying = Property("QVariantList", _now_playing, notify=nowPlayingChanged)

    # A game you played for a while just closed: the window shows a small recap card with
    # how long it was, the total, and quick ways to rate it, mark it finished or leave a note.
    sessionRecap = Signal(str, "QVariantMap")
    RECAP_MIN_SECONDS = 180

    def _recap(self, key, seconds):
        if not key or seconds < self.RECAP_MIN_SECONDS:
            return
        g = self.game(key)
        if not g:
            return
        self.sessionRecap.emit(key, {"title": g.get("title") or "", "minutes": int(seconds // 60),
                                     "total": float(g.get("playtime") or 0), "covers": g.get("covers") or [],
                                     "rating": int(g.get("rating") or 0), "status": g.get("status") or ""})

    @staticmethod
    def _alive(pid):
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, ValueError, TypeError):
            return False

    @Slot(str, bool)
    def quitGame(self, key, force):
        """Ask the game to close (SIGTERM to its process group), or end it now (SIGKILL)."""
        import signal
        if key in self._steam_playing and key not in self._playing:
            title = self._steam_playing[key].get("title", "the game")
            appid = key.split(":", 1)[1]

            def work():
                ok = steamrun.quit(appid, force)
                return lambda: (self.toast.emit(f"{'Closed' if force else 'Asked to close'} {title}" if ok
                                                else f"Could not close {title}: close it from the game or Steam"),
                                QTimer.singleShot(2000, self._check_steam_running))
            self._bg(work)
            return
        info = self._playing.get(key)
        if not info or not info.get("pid"):
            self.toast.emit("Cornerplay cannot reach this game: close it from the game itself")
            return
        try:
            os.killpg(int(info["pid"]), signal.SIGKILL if force else signal.SIGTERM)
            self.toast.emit(f"{'Closed' if force else 'Asked to close'} {info.get('title', 'the game')}")
        except (OSError, ValueError) as e:
            self.toast.emit(f"Could not close it: {e}")

    def _check_sessions(self):
        changed = False
        for f in session.SESSIONS.glob("*.json"):
            if f.name.startswith("job-"):
                continue
            data = read_json(f) or {}
            key = data.get("key")
            if key and data.get("state") == "playing" and (not data.get("pid") or self._alive(data["pid"])):
                if self._playing.get(key, {}).get("pid") != data.get("pid"):
                    self._playing[key] = {"title": data.get("title", ""), "since": data.get("since", 0),
                                          "pid": data.get("pid", 0)}
                    changed = True
            elif key in self._playing:
                self._playing.pop(key)
                self._starting.pop(key, None)  # it closed: Play may start it again
                changed = True
            stamp = (data.get("state"), data.get("since"))
            if self._sessions_seen.get(f.name) == stamp:
                continue
            self._sessions_seen[f.name] = stamp
            if data.get("state") == "uploading":
                self.toast.emit(f"Uploading saves for {data.get('title') or 'your game'}…")
            elif data.get("state") == "done":
                self._reload_playtime()
                self._after_session(data)
                self._recap(data.get("key", ""), (data.get("since") or 0) - (data.get("started") or data.get("since") or 0))
                res = data.get("sync") or {}
                title = data.get("title", "")
                if res.get("status") == "ok":
                    self.toast.emit(f"{title}: {res.get('message')}")
                elif res.get("status") in ("error", "conflict"):
                    self.toast.emit(f"{title}: saves not uploaded ({res.get('message')})")
                try:
                    f.unlink()
                except OSError:
                    pass
        for key, info in list(self._playing.items()):  # ended without Cornerplay seeing "done"
            if info.get("pid") and not self._alive(info["pid"]):
                self._playing.pop(key)
                self._starting.pop(key, None)  # it closed: Play may start it again
                changed = True
        if changed:
            self.nowPlayingChanged.emit()
        if self._playing:  # a game's end is also caught when the file watch misses it
            if not hasattr(self, "_play_timer"):
                self._play_timer = QTimer(self, singleShot=True, interval=5000)
                self._play_timer.timeout.connect(self._check_sessions)
            self._play_timer.start()  # restarts: one pending check at most

    diskWarning = Signal(str, "QVariantMap")   # key, {"title", "need", "free", "after", "suggest": [...]}

    @Slot(str)
    def install(self, key):
        """Install, after checking the drive will not run nearly full (diskWarning asks first)."""
        g, store = self._guard(key)
        if not g or key in self.procs or store.external_installs or g.extra.get("owned_only"):
            return self.installAnyway(key)
        target = str(settings.games_dir)

        def work():
            need = 0
            if g.store == "epic":
                try:
                    r = store_run([store.tool(), "info", g.id, "--json"], timeout=60)
                    info = json.loads(r.stdout or "{}")
                    need = int(((info.get("manifest") or {}).get("disk_size")) or 0)
                except (ValueError, StoreError, OSError):
                    need = 0
            probe = target if os.path.isdir(target) else str(Path.home())
            d = storage.drive(probe)
            if not d:
                return lambda: self.installAnyway(key)
            after = d["free"] - need
            if after >= 0.10 * d["total"] and after > 0:
                return lambda: self.installAnyway(key)
            suggest = self._space_suggestions(d["mount"])
            info = {"title": g.title, "need": storage.nice(need) if need else "", "free": storage.nice(d["free"]),
                    "after": storage.nice(max(0, after)), "drive": d["label"], "full": after <= 0,
                    "suggest": suggest}
            return lambda: self.diskWarning.emit(key, info)
        self._bg(work)

    def _space_suggestions(self, mount):
        """Big installed games on that drive not played for three months, biggest first."""
        now = time.time()
        rows = []
        for g in self.model.games:
            if not g.installed or not g.install_path or storage.mount_of(g.install_path) != mount:
                continue
            last = playtime.of(g, self.model.played)[1]
            if last and last > now - 90 * 86400:
                continue
            size = storage.size_of(g.install_path, g.extra.get("size", 0))
            if size > 2 * 1024 ** 3:
                rows.append((size, g.title))
        return [f"{t} ({storage.nice(b)})" for b, t in sorted(rows, reverse=True)[:4]]

    @Slot(str)
    def installAnyway(self, key):
        if key in self._paused:
            return self.resumeDownload(key)  # Install on a paused game carries on with it
        g, store = self._guard(key)
        if not g or key in self.procs:
            return
        try:
            with runner.using(self._options_for(g)):
                cmd = store.install(g)
        except StoreError as e:
            self.toast.emit(str(e))
            return
        if store.external_installs or g.extra.get("owned_only"):
            self._detach(cmd.argv, cmd.env, cmd.cwd, key)
            self.toast.emit(f"{store.name} is taking over the install of {g.title}")
        else:
            self._start_job(g, "install", cmd)

    @Slot(str)
    def update(self, key):
        g, store = self._guard(key)
        if not g or key in self.procs or not g.extra.get("update"):
            return
        try:
            with runner.using(self._options_for(g)):
                cmd = store.update(g)
        except StoreError as e:
            self.toast.emit(str(e))
            return
        self._start_job(g, "update", cmd)

    @Slot(str)
    def uninstall(self, key):
        g, store = self._guard(key)
        if not g or key in self.procs:
            return
        try:
            cmd = store.uninstall(g)
        except (StoreError, OSError) as e:
            self.toast.emit(str(e))
            return
        if cmd is None:
            self.toast.emit(f"Removed {g.title}")
            self.refresh(g.store)
        elif store.external_installs:
            self._detach(cmd.argv, cmd.env, cmd.cwd, key)
        else:
            self._start_job(g, "uninstall", cmd)

    @Slot(str)
    def cancel(self, key):
        if any(q[0].key == key for q in self._queue) or key in self._paused:  # not running: just leave the line
            self._queue = [q for q in self._queue if q[0].key != key]
            self._paused.pop(key, None)
            self.model.jobs.pop(key, None)
            self._touch(key)
            return
        p = self.procs.get(key)
        if p:
            p.setProperty("cancelled", True)
            th = self._throttles.pop(key, None)
            if th:
                th.stop()  # a frozen process would not see the request to end
            p.terminate()
            QTimer.singleShot(4000, lambda: p.state() != QProcess.NotRunning and p.kill())

    DOWNLOADS = ("install", "update", "dlc", "verify", "move", "fix")
    PAUSABLE = ("install", "update")  # the store tools carry on from where they stopped
    _queue = []  # [(game, kind, cmd)] waiting for the running download to finish
    _paused = {}  # key -> (game, kind, progress)
    _throttles = {}  # key -> throttle.Throttle (Settings > Library: download speed limit)
    downloadsChanged = Signal()

    def _downloads(self):
        rows = []
        for key in list(self.procs):
            job = self.model.jobs.get(key) or {}
            if job.get("kind") in self.DOWNLOADS:
                rows.append(self._download_row(key, job, "running"))
        for g, kind, _cmd in list(self._queue):
            rows.append(self._download_row(g.key, {"kind": kind, "progress": -1.0}, "queued", g))
        for key, (g, kind, progress) in list(self._paused.items()):
            rows.append(self._download_row(key, {"kind": kind, "progress": progress}, "paused", g))
        return rows

    def _download_row(self, key, job, state, g=None):
        g = g or self.model.find(key)
        eta = job.get("eta")
        if eta is not None and job.get("etaAt"):
            eta = max(0, eta - (time.monotonic() - job["etaAt"]))
        return {"key": key, "title": g.title if g else key, "kind": job.get("kind", ""), "state": state,
                "progress": float(job.get("progress", -1.0)), "speed": float(job.get("speed", 0.0)),
                "eta": int(eta) if eta is not None else -1, "cover": _cover(g) if g else "",
                "covers": _covers(g) if g else [], "pausable": job.get("kind") in self.PAUSABLE,
                "store": g.store if g else ""}

    downloads = Property("QVariantList", _downloads, notify=downloadsChanged)

    @Slot(str)
    def pauseDownload(self, key):
        """Stop a download and keep its place; Resume carries on from where it stopped."""
        for i, (g, kind, _cmd) in enumerate(self._queue):
            if g.key == key and kind in self.PAUSABLE:
                self._queue.pop(i)
                self._paused[key] = (g, kind, -1.0)
                self.model.jobs[key] = {"kind": "paused", "progress": -1.0}
                self._touch(key)
                return
        p = self.procs.get(key)
        job = self.model.jobs.get(key) or {}
        if p and job.get("kind") in self.PAUSABLE:
            p.setProperty("paused", True)
            th = self._throttles.pop(key, None)
            if th:
                th.stop()
            p.terminate()
            QTimer.singleShot(8000, lambda: p.state() != QProcess.NotRunning and p.kill())

    @Slot(str)
    def resumeDownload(self, key):
        item = self._paused.pop(key, None)
        if not item:
            return
        g, kind, _progress = item
        self.model.jobs.pop(key, None)
        store = self.stores.get(g.store)
        try:
            with runner.using(self._options_for(g)):
                cmd = store.update(g) if kind == "update" else store.install(g)
        except StoreError as e:
            self._paused[key] = item
            self.model.jobs[key] = {"kind": "paused", "progress": item[2]}
            self.toast.emit(str(e))
            self._touch(key)
            return
        self._start_job(g, kind, cmd)
        self._touch(key)

    @Slot(str, int)
    def moveDownload(self, key, step):
        """Move a waiting download up (-1) or down (+1) the line; -99 puts it first."""
        i = next((n for n, q in enumerate(self._queue) if q[0].key == key), -1)
        if i < 0:
            return
        j = 0 if step <= -99 else max(0, min(len(self._queue) - 1, i + step))
        self._queue.insert(j, self._queue.pop(i))
        self.downloadsChanged.emit()

    def _start_job(self, g, kind, cmd):
        """Downloads go one at a time (all at once only made each slower); the rest wait in line."""
        if kind in self.DOWNLOADS and any(j.get("kind") in self.DOWNLOADS for k, j in self.model.jobs.items()
                                          if k in self.procs):
            if not any(q[0].key == g.key for q in self._queue):
                self._queue.append((g, kind, cmd))
                self.model.jobs[g.key] = {"kind": "queued", "progress": -1.0}
                self._touch(g.key)
                self.toast.emit(f"{g.title} is queued: it starts when the current download finishes")
            return
        self._run_job(g, kind, cmd)

    def _next_in_queue(self):
        if self._queue and not any(j.get("kind") in self.DOWNLOADS for k, j in self.model.jobs.items()
                                   if k in self.procs):
            g, kind, cmd = self._queue.pop(0)
            self.model.jobs.pop(g.key, None)
            self._run_job(g, kind, cmd)

    def _run_job(self, g, kind, cmd):
        key = g.key
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.setProcessEnvironment(self._env(cmd.env))
        self.procs[key] = p
        self.logs[key] = []
        self.model.jobs[key] = {"kind": kind, "progress": -1.0}
        p.readyReadStandardOutput.connect(lambda: self._job_output(key))
        p.finished.connect(lambda code, status: self._job_done(g, kind, code))
        p.errorOccurred.connect(lambda err: err == QProcess.FailedToStart and self._job_done(g, kind, -1))
        self._touch(key)
        if kind in ("install", "update", "dlc"):
            p.started.connect(lambda: self._throttle(key, p))
        p.start(cmd.argv[0], cmd.argv[1:])

    def _throttle(self, key, p):
        from . import throttle
        if p.processId() > 0:
            self._throttles[key] = throttle.Throttle(
                p.processId(), lambda: max(0.0, float(settings.get("download_limit") or 0)) * 1_000_000, self)

    def _job_output(self, key):
        p = self.procs.get(key)
        if not p:
            return
        text = bytes(p.readAllStandardOutput()).decode("utf-8", "replace")
        lines = [l for l in re.split(r"[\r\n]+", text) if l.strip()]
        self.logs[key] = (self.logs[key] + lines)[-40:]
        job = self.model.jobs.get(key)
        if job is None:
            return
        now = time.monotonic()
        told_eta = False
        for line in lines:
            sp = SPEED.search(line)
            if sp and "/s" in line and "Disk" not in line:  # legendary also prints the disk's write speed
                job["speed"] = float(sp.group(1)) * _UNITS.get(sp.group(2).lower(), 1)
                th = self._throttles.get(key)
                if th:
                    th.reported(job["speed"])
            et = ETA.search(line)
            if et:
                h, mi, se = (int(x) for x in et.groups())
                job["eta"], job["etaAt"] = h * 3600 + mi * 60 + se, now
                told_eta = True
        for line in reversed(lines):
            m = PROGRESS.search(line)
            if m:
                pct = min(100.0, float(m.group(1)))
                job["progress"] = pct
                # No ETA from the tool: estimate it from the last minute or so of progress.
                if not told_eta and not job.get("etaFromTool"):
                    hist = [h for h in job.setdefault("hist", []) if now - h[0] < 90] + [(now, pct)]
                    job["hist"] = hist
                    t0, p0 = hist[0]
                    if now - t0 > 8 and pct > p0:
                        job["eta"], job["etaAt"] = (100 - pct) * (now - t0) / (pct - p0), now
                break
        if told_eta:
            job["etaFromTool"] = True
        self._touch(key)

    def _job_done(self, g, kind, code):
        key = g.key
        p = self.procs.pop(key, None)
        if p is None:
            return
        th = self._throttles.pop(key, None)
        if th:
            th.stop()
        last = (self.model.jobs.get(key) or {}).get("progress", -1.0)
        self.model.jobs.pop(key, None)
        lines = self.logs.pop(key, [])
        (LOG_DIR / (re.sub(r"[^A-Za-z0-9_.-]", "_", key) + f".{kind}.log")).write_text("\n".join(lines))
        if p.property("paused"):
            self._paused[key] = (g, kind, last)
            self.model.jobs[key] = {"kind": "paused", "progress": last}
            self.toast.emit(f"Paused: {g.title}")
        elif p.property("cancelled"):
            self._moves.pop(key, None)
            self.toast.emit(f"Cancelled: {g.title}")
        elif code == 0 and kind == "move":
            self.toast.emit(f"Moved {g.title}")
            self._after_move(g)
        elif code == 0:
            if kind == "update":
                g.extra.pop("update", None)  # the refresh below confirms it
            done = (f"Installed DLC for {g.title}" if kind == "dlc" else
                    f"{ {'install': 'Installed', 'update': 'Updated', 'verify': 'Repaired the files of'}.get(kind, 'Removed')} {g.title}")
            self.toast.emit(done)
            if kind in ("install", "update", "dlc"):
                self._notify(done, "Ready to play" if kind != "dlc" else "")
            if kind in ("dlc", "update", "install"):
                self._dlc_cache.pop(key, None)
        else:
            detail = next((l for l in reversed(lines) if "error" in l.lower()), lines[-1] if lines else "")
            self.toast.emit(f"{kind.capitalize()} failed for {g.title}: {detail[-160:]}".rstrip(": "))
        p.deleteLater()
        self._touch(key)
        self.refresh(g.store)
        QTimer.singleShot(0, self._next_in_queue)

    def _touch(self, key):
        self.model.touch(key)
        self.gameChanged.emit(key)
        self.downloadsChanged.emit()

    def _notify(self, title, body=""):
        """A desktop notification, only while Cornerplay is not in front (a game, another app)."""
        if QGuiApplication.applicationState() == Qt.ApplicationActive:
            return
        import shutil
        if shutil.which("notify-send"):
            QProcess.startDetached("notify-send", ["--app-name=Cornerplay", "--icon=cornerplay", title, body])

    # --- settings and helpers --------------------------------------------
    settingsMap = Property("QVariantMap", lambda s: s._per_settings.setdefault("map", {k: settings.get(k) for k in DEFAULTS})
                           if "map" not in s._per_settings else s._per_settings["map"], notify=settingsChanged)

    @Slot(str, str)
    def setShelfBackground(self, shelf, path):
        """A collection's own background picture ("" clears it)."""
        path = QUrl(path).toLocalFile() if path.startswith("file:") else path
        bgs = dict(settings.get("shelf_backgrounds") or {})
        if path and os.path.isfile(path):
            bgs[shelf] = path
        else:
            bgs.pop(shelf, None)
        settings.set("shelf_backgrounds", bgs)
        self.settingsChanged.emit()

    @Slot(str)
    def setBackgroundPicture(self, path):
        path = QUrl(path).toLocalFile() if path.startswith("file:") else path
        if path and os.path.isfile(path):
            settings.set("bg_picture", path)
            settings.set("bg_mode", "picture")
            self.settingsChanged.emit()

    @Slot(str, "QVariant")
    def setSetting(self, key, value):
        if key not in DEFAULTS:
            return
        kind = type(DEFAULTS[key])
        try:
            value = kind(round(value)) if kind is int else kind(value)
        except (TypeError, ValueError):
            return
        if settings.get(key) != value:
            settings.set(key, value)
            self.settingsChanged.emit()
            if key.startswith("theme_"):
                self._scheme_dark = None
                self._load_theme()
            if key == "evening_warmth":
                self._load_theme()
            if key == "wallpaper_backdrop":
                self._find_wallpaper()
            if key == "steam_games" and value:
                self._auto_steam()
            if key == "merge_duplicates":
                self.model.set_games(self.model.games)
                self.storesChanged.emit()

    SAFE_SCHEMES = ("https", "http", "steam")

    @Slot(str)
    def openUrl(self, url):
        """Open a link in the browser (or the Steam client). Links come from store data and web
        pages, so only web and steam:// links are opened: never file://, never other apps' schemes."""
        u = QUrl(url)
        if u.isValid() and u.scheme().lower() in self.SAFE_SCHEMES:
            QDesktopServices.openUrl(u)

    @Slot(str)
    def openFolder(self, path):
        if path and os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @Slot(str)
    def copy(self, text):
        QGuiApplication.clipboard().setText(text)

    def shutdown(self):
        self._quitting = True  # stops the background details fetch
        for th in list(self._throttles.values()):
            th.stop()  # a download frozen by the speed limit would not see the request to end
        for p in list(self.procs.values()):
            p.terminate()
            p.waitForFinished(3000)
        self.pool.shutdown(wait=False, cancel_futures=True)

    # --- demo ------------------------------------------------------------
    def _load_demo(self):
        cdn = "https://cdn.cloudflare.steamstatic.com/steam/apps"
        rows = [("steam", "1245620", "Elden Ring", True), ("steam", "1091500", "Cyberpunk 2077", True),
                ("steam", "413150", "Stardew Valley", False), ("steam", "367520", "Hollow Knight", True),
                ("epic", "1145360", "Hades", True), ("epic", "292030", "The Witcher 3: Wild Hunt", False),
                ("epic", "504230", "Celeste", False), ("gog", "1174180", "Red Dead Redemption 2", False),
                ("gog", "588650", "Dead Cells", True), ("gog", "646570", "Slay the Spire", False),
                ("amazon", "268910", "Cuphead", True), ("amazon", "105600", "Terraria", False),
                ("battlenet", "battlenet-app", "Battle.net", True), ("battlenet", "pro", "Overwatch 2", True),
                ("battlenet", "fenris", "Diablo IV", True)]
        rows += [("gog", "1091500", "Cyberpunk 2077", True), ("epic", "1091500", "Cyberpunk 2077", False),
                 ("gog", "292030", "The Witcher 3: Wild Hunt", True)]
        games = []
        for store, appid, title, inst in rows:
            art = (LAUNCHER_COVER if appid == "battlenet-app" else
                   "" if store == "battlenet" else f"{cdn}/{appid}/library_600x900.jpg")
            games.append(Game(store=store, id=appid, title=title, cover=art,
                              cover_fallback=art and appid.isdigit() and f"{cdn}/{appid}/header.jpg" or "", installed=inst))
        hints = {"pro": 2357570, "fenris": 2344520}
        for g in games:
            if g.id in hints:
                g.extra["steam_appid"] = hints[g.id]
        for g in games:
            if g.key in ("epic:1145360", "gog:588650"):
                g.extra["update"] = True
        now = int(time.time())
        self.model.played = {"epic:1145360": {"seconds": 41 * 3600, "last": now - 3 * 3600},
                             "steam:1245620": {"seconds": 120 * 3600, "last": now - 2 * 86400},
                             "gog:588650": {"seconds": 9 * 3600, "last": now - 26 * 3600},
                             "battlenet:pro": {"seconds": 1800, "last": now - 20 * 86400}}
        self.model.set_games(games)
        self.pool.submit(lambda: (covers.fill_all(games), protondb.refresh(_appid(g) for g in games),
                                  self._after.emit(lambda: (self.model.touch(), self.storesChanged.emit()))))
        self.model.jobs["gog:646570"] = {"kind": "install", "progress": 42.0, "speed": 18.4e6, "eta": 260, "etaAt": time.monotonic()}

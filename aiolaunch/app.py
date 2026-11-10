"""Qt side of AIO Launch: the library model, background jobs and the object QML talks to."""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QByteArray, QFileSystemWatcher, QModelIndex, QObject,
                            QProcess, QProcessEnvironment, QSortFilterProxyModel, Qt, QTimer, QUrl,
                            Property, Signal, Slot)
from PySide6.QtGui import QDesktopServices, QGuiApplication

import shlex

import sys

from . import covers, gamecolour, playtime, proton, runner, saves, session, steamgames, steamshortcut, theme as themes
from .config import CACHE_DIR, DEFAULTS, LOG_DIR, game_options, read_json, settings, write_json
from .runner import StoreError
from .stores.amazon import Amazon
from .stores.base import Game, PartialResult
from .stores.battlenet import BattleNet
from .stores.epic import Epic
from .stores.gog import Gog
from .stores.steam import Steam

LIBRARY_CACHE = CACHE_DIR / "library.json"
PALETTE = themes.RYOKU_PALETTE
PROGRESS = re.compile(r"Progress:\s*([\d.]+)")

ROLES = ["key", "store", "storeName", "storeColor", "title", "cover", "coverFallback",
         "installed", "job", "progress", "external", "installPath", "copies",
         "update", "playtime", "lastPlayed", "covers", "heroes", "logos"]
GROUP_ROLES = ("copies", "playtime", "lastPlayed")
SORTS = ("name", "recent", "playtime")
RECENT_ROW = 8  # games in the "Continue playing" row  # worked out over every store's copy of a game


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


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
    return custom or g.cover


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
    "installed": lambda m, g: g.installed,
    "job": lambda m, g: _job(m, g).get("kind", ""),
    "progress": lambda m, g: _job(m, g).get("progress", 0.0),
    "external": lambda m, g: m.stores[g.store].external_installs,
    "installPath": lambda m, g: g.install_path,
    "copies": lambda m, g: 1,
    "update": lambda m, g: bool(g.installed and g.extra.get("update")),
    "playtime": lambda m, g: playtime.of(g, m.played)[0],
    "lastPlayed": lambda m, g: playtime.of(g, m.played)[1],
    "covers": lambda m, g: _covers(g),
    "heroes": lambda m, g: _heroes(g),
    "logos": lambda m, g: _logos(g),
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
        self.played = playtime.load()    # AIO Launch's own playtime record

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

    def is_hidden(self, group):
        return any(game_options.get(g.key).get("hidden") for g in group)

    def group_of(self, key):
        return next((grp for grp in self.groups if any(g.key == key for g in grp)), [])

    def rep(self, group):
        """The copy a row stands for: focused store, running job, user's pick, installed."""
        prefer = game_options.get(self.group_id(group[0])).get("prefer", "")
        return min(group, key=lambda g: (g.store != self.focus_store, g.key not in self.jobs,
                                         g.key != prefer, not g.installed))

    # --- data ------------------------------------------------------------
    def value(self, g: Game, role: str):
        """One field of one game; only the asked-for field is worked out (the grid asks a lot)."""
        return _FIELDS[role](self, g)

    def group_value(self, group, role):
        """Row-level values: a game owned on several stores counts the time played on each."""
        if role == "copies":
            return len(group)
        times = [playtime.of(g, self.played) for g in group]
        return sum(t[0] for t in times) if role == "playtime" else max(t[1] for t in times)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.groups):
            return None
        group = self.groups[index.row()]
        g = self.rep(group)
        if role == Qt.DisplayRole:
            return g.title
        i = role - Qt.UserRole
        if not 0 <= i < len(ROLES):
            return None
        role = ROLES[i]
        return self.group_value(group, role) if role in GROUP_ROLES else self.value(g, role)

    def find(self, key):
        for g in self.games:
            if g.key == key:
                return g
        return None

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
        d["hidden"] = self.is_hidden(group or [g])
        d["playtime"] = self.group_value(group or [g], "playtime")
        d["lastPlayed"] = self.group_value(group or [g], "lastPlayed")
        return d

    def set_games(self, games):
        self.beginResetModel()
        self.games = list(games)
        self.regroup()
        self.endResetModel()

    def replace_store(self, store_id, games):
        self.set_games([g for g in self.games if g.store != store_id] + list(games))

    def touch(self, key=None):
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
        self._sort = settings.get("sort") if settings.get("sort") in SORTS else "name"
        self.setSourceModel(model)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.setDynamicSortFilter(True)
        self.sort(0)

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        group = model.groups[row]
        if model.is_hidden(group) != self._hidden:
            return False
        if self._store:
            group = [g for g in group if g.store == self._store]
        if self._installed:
            group = [g for g in group if g.installed]
        return bool(group) and (not self._search or any(self._search in g.title.lower() for g in group))

    def lessThan(self, left, right):
        model = self.sourceModel()
        a, b = model.groups[left.row()], model.groups[right.row()]
        if self._sort != "name":
            role = "lastPlayed" if self._sort == "recent" else "playtime"
            va, vb = model.group_value(a, role), model.group_value(b, role)
            if va != vb:
                return va > vb  # most recent / most played first; never-played games fall to the end
        return model.rep(a).title.lower() < model.rep(b).title.lower()

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

    _fetched = Signal(str, object, str)
    _worker_toast = Signal(str)
    _after = Signal(object)

    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.stores = {s.id: s for s in (Steam(), Epic(), Gog(), Amazon(), BattleNet())}
        self.model = LibraryModel(self.stores)
        self.proxy = LibraryProxy(self.model)
        self.pool = ThreadPoolExecutor(min(4, os.cpu_count() or 2))
        self.procs: dict[str, QProcess] = {}
        self.logs: dict[str, list] = {}
        self._pending = set()
        self._updates_seen = set()
        self._colour_pending = set()
        self._last_local = 0.0
        self._fetched.connect(self._on_fetched)
        self._worker_toast.connect(self.toast)
        self._after.connect(lambda fn: fn())

        self._theme = themes.current()
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
        self._wall_pending.timeout.connect(lambda: settings.get("theme_mode") == "ryoku" and self._load_theme())
        self._wall_files = [p for p in wallpaper.watch_paths() if not os.path.isdir(p)]
        self._wall_watch.fileChanged.connect(lambda _: self._wall_changed())
        self._wall_watch.directoryChanged.connect(lambda _: self._wall_changed())

        session.SESSIONS.mkdir(parents=True, exist_ok=True)
        self._sessions = QFileSystemWatcher([str(session.SESSIONS)], self)
        self._sessions.directoryChanged.connect(lambda _: QTimer.singleShot(300, self._check_sessions))
        self._sessions_seen = {}
        self._check_sessions()

        if demo:
            self._load_demo()
        else:
            cached = read_json(LIBRARY_CACHE) or []
            self.model.set_games(Game.from_dict(d) for d in cached if d.get("store") in self.stores)
            QTimer.singleShot(0, self.refresh)

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
        new = themes.current()
        if new != self._theme:
            self._theme = new
            self.themeChanged.emit()

    theme = Property("QVariantMap", lambda s: s._theme, notify=themeChanged)
    themePresets = Property("QVariantList", lambda s: list(themes.PRESETS), constant=True)
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
    def _stores_info(self):
        out = []
        for s in self.stores.values():
            mine = [g for g in self.model.games if g.store == s.id
                    and not game_options.get(g.key).get("hidden")]
            try:
                logged, account, problem = s.logged_in(), s.account(), s.problem()
            except Exception as e:  # a broken config file must not take the UI down
                logged, account, problem = False, "", str(e)
            out.append({"id": s.id, "name": s.name, "color": s.color, "count": len(mine),
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

    gameColourReady = Signal(str, str)  # key, accent ("" = no clear colour)

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
        """The "Continue playing" row: installed games, most recently played first."""
        m = self.model
        rows = []
        for group in m.groups:
            last = m.group_value(group, "lastPlayed")
            if last and not m.is_hidden(group) and any(g.installed for g in group):
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

    recentGames = Property("QVariantList", _recent_games, notify=storesChanged)
    updateCount = Property(int, lambda s: sum(1 for g in s.model.games if g.installed and g.extra.get("update")),
                           notify=storesChanged)

    @Slot("QVariant", "QVariant", result=str)
    def playedText(self, seconds, last):
        """ "12 h played · last played 3 days ago", or "" for a game never played."""
        seconds, last = int(seconds or 0), int(last or 0)
        parts = []
        if seconds >= 3600:
            parts.append(f"{seconds / 3600:.1f}".rstrip("0").rstrip(".") + " h played")
        elif seconds >= 60:
            parts.append(f"{seconds // 60} min played")
        if last:
            days = (time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)) - last) / 86400
            when = ("today" if days < 0 else "yesterday" if days < 1
                    else f"{int(days) + 1} days ago" if days < 6
                    else _short_date(last, with_year=days > 300))
            parts.append("last played " + when)
        text = " · ".join(parts)
        return text[:1].upper() + text[1:]

    def _reload_playtime(self):
        self.model.played = playtime.load()
        self.model.touch()
        self.storesChanged.emit()
    refreshing = Property(bool, lambda s: bool(s._pending), notify=refreshingChanged)
    totalCount = Property(int, lambda s: len(s.model.groups) - s._hidden_count(), notify=storesChanged)

    @Slot()
    @Slot(str)
    def refresh(self, store_id=""):
        if self.demo:
            return
        for s in ([self.stores[store_id]] if store_id else self.stores.values()):
            if s.id in self._pending:
                continue
            self._pending.add(s.id)
            self.pool.submit(self._fetch, s)
        self.refreshingChanged.emit()
        self.storesChanged.emit()

    @Slot()
    def windowActivated(self):
        """Cheap catch-up when the window gets focus: wallpaper (for desktops without a watched file)."""
        if settings.get("theme_mode") == "ryoku":
            self._wall_pending.start()
        self.refreshLocal()

    @Slot()
    def refreshLocal(self):
        """Cheap rescan when the window regains focus (Steam / Battle.net change outside AIO Launch)."""
        if time.time() - self._last_local > 30 and not self._pending:
            self._last_local = time.time()
            self.refresh("steam")
            self.refresh("battlenet")

    def _fetch(self, store):
        games, error = None, ""
        try:
            if store.id in ("epic", "amazon") and store.problem():
                games = []
            else:
                games = store.fetch()
        except PartialResult as e:
            games, error = e.games, str(e)
        except StoreError as e:
            error = f"{store.name}: {e}"
        except Exception as e:
            error = f"{store.name}: {type(e).__name__}: {e}"
        if games:
            try:
                error = error or covers.fill_all(games)
            except Exception as e:  # cover art is never worth failing a refresh
                error = error or f"Cover lookup: {type(e).__name__}: {e}"
        self._fetched.emit(store.id, games, error)

    def _on_fetched(self, store_id, games, error):
        self._pending.discard(store_id)
        if games is not None:
            self.model.replace_store(store_id, games)
            write_json(LIBRARY_CACHE, [g.to_dict() for g in self.model.games])
        if error:
            self.toast.emit(error)
        self.refreshingChanged.emit()
        self.storesChanged.emit()
        self.gameChanged.emit("")
        if not self._pending:
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

    light = Property(bool, _light, notify=settingsChanged)

    def _guard(self, key):
        g = self.model.find(key)
        if not g:
            return None, None
        if self.demo:
            self.toast.emit("Demo mode: nothing is really launched or installed")
            return None, None
        return g, self.stores[g.store]

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
            game_options.set(g.key, "hidden", True if hidden else None)
        self.proxy.refilter()
        self.storesChanged.emit()
        self.gameChanged.emit(key)
        title = group[0].title if group else "Game"
        self.toast.emit(f"{title} hidden. Find it under Hidden games." if hidden else f"{title} is back in your library")

    def _hidden_count(self):
        return sum(1 for grp in self.model.groups if self.model.is_hidden(grp))

    hiddenCount = Property(int, _hidden_count, notify=storesChanged)

    @Slot(str)
    def preferCopy(self, key):
        g = self.model.find(key)
        if g and len(self.model.group_of(key)) > 1:
            game_options.set(self.model.group_id(g), "prefer", key)
            self._touch(key)

    @Slot(str)
    def loadDlcs(self, key):
        g = self.model.find(key)
        if not g:
            return
        store = self.stores[g.store]

        def work():
            try:
                rows = ([{"title": f"{g.title}: Expansion Pass", "status": "owned", "url": ""},
                         {"title": f"{g.title}: Soundtrack", "status": "available", "url": "https://example.org"}]
                        if self.demo else (store.dlcs(g) or []))
            except StoreError as e:
                return lambda msg=str(e): self.dlcsReady.emit(key, [], msg)
            rank = {"installed": 0, "owned": 1, "available": 2}
            rows.sort(key=lambda r: (rank.get(r["status"], 3), r["title"].lower()))
            return lambda: self.dlcsReady.emit(key, rows, store.dlc_note)
        self._bg(work)

    def _options_for(self, g):
        # Battle.net games all run through the one launcher prefix, so they share its options.
        return game_options.get("battlenet:battlenet-app" if g.store == "battlenet" else g.key)

    @Slot(str, result="QVariantMap")
    def gameOptions(self, key):
        return game_options.get(key)

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

    @Slot()
    def checkGe(self):
        """Look up the newest GE-Proton (one small GitHub request)."""
        def work():
            try:
                tag, _, _ = proton.latest_ge()
            except Exception as e:
                return lambda: self._set_ge(error=f"Could not check: {type(e).__name__}")
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
                return lambda: (self._set_ge(busy=False, error=str(e)[:160]), self.toast.emit("GE-Proton download failed"))

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
        """Add AIO Launch itself (opens in TV mode)."""
        theme = dict(self._theme)
        self._steam_job(lambda: f"AIO Launch is in Steam ({steamshortcut.add(theme)} account(s))",
                        "Adding AIO Launch to Steam…")

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

    def _play(self, key, mode):
        g, store = self._guard(key)
        if not g:
            return
        opts = self._options_for(g)
        sync = saves.enabled_for(g) and mode != "skip"
        if sync:
            self.toast.emit(f"Syncing saves for {g.title}…")

        def work():
            if sync:
                res = saves.sync(g, mode)
                if res["status"] == "conflict":
                    return lambda: self.saveConflict.emit(key, res["local"], res["cloud"])
                if res["status"] == "error":
                    self._worker_toast.emit(f"{g.title}: {res['message']} (launching anyway)")
            with runner.using(opts):
                cmd = store.launch(g)
            if opts.get("args") and g.store in ("epic", "gog", "amazon"):
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
            ok = self._detach([sys.executable, "-m", "aiolaunch.session", str(job)], env, "", g.key + ".session")
        else:
            ok = self._detach(cmd.argv, cmd.env, cmd.cwd, g.key)
        self.toast.emit(f"Launching {g.title}" if ok else f"Could not start {g.title} (log: {LOG_DIR})")

    def _check_sessions(self):
        for f in session.SESSIONS.glob("*.json"):
            if f.name.startswith("job-"):
                continue
            data = read_json(f) or {}
            stamp = (data.get("state"), data.get("since"))
            if self._sessions_seen.get(f.name) == stamp:
                continue
            self._sessions_seen[f.name] = stamp
            if data.get("state") == "uploading":
                self.toast.emit(f"Uploading saves for {data.get('title') or 'your game'}…")
            elif data.get("state") == "done":
                self._reload_playtime()
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

    @Slot(str)
    def install(self, key):
        g, store = self._guard(key)
        if not g or key in self.procs:
            return
        try:
            with runner.using(self._options_for(g)):
                cmd = store.install(g)
        except StoreError as e:
            self.toast.emit(str(e))
            return
        if store.external_installs:
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
        p = self.procs.get(key)
        if p:
            p.setProperty("cancelled", True)
            p.terminate()
            QTimer.singleShot(4000, lambda: p.state() != QProcess.NotRunning and p.kill())

    def _start_job(self, g, kind, cmd):
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
        p.start(cmd.argv[0], cmd.argv[1:])

    def _job_output(self, key):
        p = self.procs.get(key)
        if not p:
            return
        text = bytes(p.readAllStandardOutput()).decode("utf-8", "replace")
        lines = [l for l in re.split(r"[\r\n]+", text) if l.strip()]
        self.logs[key] = (self.logs[key] + lines)[-40:]
        for line in reversed(lines):
            m = PROGRESS.search(line)
            if m:
                self.model.jobs[key]["progress"] = min(100.0, float(m.group(1)))
                self._touch(key)
                break

    def _job_done(self, g, kind, code):
        key = g.key
        p = self.procs.pop(key, None)
        if p is None:
            return
        self.model.jobs.pop(key, None)
        lines = self.logs.pop(key, [])
        (LOG_DIR / (re.sub(r"[^A-Za-z0-9_.-]", "_", key) + f".{kind}.log")).write_text("\n".join(lines))
        if p.property("cancelled"):
            self.toast.emit(f"Cancelled: {g.title}")
        elif code == 0:
            if kind == "update":
                g.extra.pop("update", None)  # the refresh below confirms it
            self.toast.emit(f"{ {'install': 'Installed', 'update': 'Updated'}.get(kind, 'Removed')} {g.title}")
        else:
            detail = next((l for l in reversed(lines) if "error" in l.lower()), lines[-1] if lines else "")
            self.toast.emit(f"{kind.capitalize()} failed for {g.title}: {detail[-160:]}".rstrip(": "))
        p.deleteLater()
        self._touch(key)
        self.refresh(g.store)

    def _touch(self, key):
        self.model.touch(key)
        self.gameChanged.emit(key)

    # --- settings and helpers --------------------------------------------
    settingsMap = Property("QVariantMap", lambda s: {k: settings.get(k) for k in DEFAULTS}, notify=settingsChanged)

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
                self._load_theme()
            if key == "steam_games" and value:
                self._auto_steam()
            if key == "merge_duplicates":
                self.model.set_games(self.model.games)
                self.storesChanged.emit()

    @Slot(str)
    def openUrl(self, url):
        QDesktopServices.openUrl(QUrl(url))

    @Slot(str)
    def openFolder(self, path):
        if path and os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @Slot(str)
    def copy(self, text):
        QGuiApplication.clipboard().setText(text)

    def shutdown(self):
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
            art = "" if store == "battlenet" else f"{cdn}/{appid}/library_600x900.jpg"
            games.append(Game(store=store, id=appid, title=title, cover=art,
                              cover_fallback=art and f"{cdn}/{appid}/header.jpg", installed=inst))
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
        self.pool.submit(lambda: (covers.fill_all(games), self._after.emit(lambda: (self.model.touch(), self.storesChanged.emit()))))
        self.model.jobs["gog:646570"] = {"kind": "install", "progress": 42.0}

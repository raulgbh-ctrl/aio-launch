"""Qt side of Kura: the library model, background jobs and the object QML talks to."""
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

from . import covers, runner, theme as themes
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
         "installed", "job", "progress", "external", "installPath", "copies"]


def _cover(g):
    custom = game_options.get(g.key).get("cover", "")
    if custom.startswith("/"):
        return "file://" + custom
    return custom or g.cover


class LibraryModel(QAbstractListModel):
    """One row per game; copies of the same game on several stores share a row."""

    def __init__(self, stores):
        super().__init__()
        self.stores = stores
        self.games: list[Game] = []
        self.groups: list[list[Game]] = []
        self.jobs: dict[str, dict] = {}  # key -> {"kind": str, "progress": float}
        self.focus_store = ""            # the sidebar's store filter decides which copy is shown

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

    def group_of(self, key):
        return next((grp for grp in self.groups if any(g.key == key for g in grp)), [])

    def rep(self, group):
        """The copy a row stands for: focused store, running job, user's pick, installed."""
        prefer = game_options.get(self.group_id(group[0])).get("prefer", "")
        return min(group, key=lambda g: (g.store != self.focus_store, g.key not in self.jobs,
                                         g.key != prefer, not g.installed))

    # --- data ------------------------------------------------------------
    def value(self, g: Game, role: str):
        store = self.stores[g.store]
        job = self.jobs.get(g.key)
        return {
            "key": g.key, "store": g.store, "storeName": store.name, "storeColor": store.color,
            "title": g.title, "cover": _cover(g), "coverFallback": g.cover_fallback,
            "installed": g.installed, "job": job["kind"] if job else "",
            "progress": job["progress"] if job else 0.0,
            "external": store.external_installs, "installPath": g.install_path, "copies": 1,
        }[role]

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
        return len(group) if ROLES[i] == "copies" else self.value(g, ROLES[i])

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
        self._store, self._installed, self._search = "", False, ""
        self.setSourceModel(model)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.setDynamicSortFilter(True)
        self.sort(0)

    def filterAcceptsRow(self, row, parent):
        group = self.sourceModel().groups[row]
        if self._store:
            group = [g for g in group if g.store == self._store]
        if self._installed:
            group = [g for g in group if g.installed]
        return bool(group) and (not self._search or any(self._search in g.title.lower() for g in group))

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

    @Slot(int, result=str)
    def keyAt(self, row):
        idx = self.mapToSource(self.index(row, 0))
        model = self.sourceModel()
        return model.rep(model.groups[idx.row()]).key if idx.isValid() else ""


class Kura(QObject):
    storesChanged = Signal()
    refreshingChanged = Signal()
    themeChanged = Signal()
    settingsChanged = Signal()
    toast = Signal(str)
    gameChanged = Signal(str)
    loginReady = Signal(str, str, str)   # store, url, prompt
    loginDone = Signal(str, bool, str)   # store, ok, message
    dlcsReady = Signal(str, "QVariantList", str)  # key, rows, note

    _fetched = Signal(str, object, str)
    _worker_toast = Signal(str)
    _after = Signal(object)

    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.stores = {s.id: s for s in (Steam(), Epic(), Gog(), Amazon(), BattleNet())}
        self.model = LibraryModel(self.stores)
        self.proxy = LibraryProxy(self.model)
        self.pool = ThreadPoolExecutor(6)
        self.procs: dict[str, QProcess] = {}
        self.logs: dict[str, list] = {}
        self._pending = set()
        self._last_local = 0.0
        self._fetched.connect(self._on_fetched)
        self._worker_toast.connect(self.toast)
        self._after.connect(lambda fn: fn())

        self._theme = themes.current()
        self._watch = QFileSystemWatcher(self)
        if PALETTE.parent.is_dir():
            self._watch.addPath(str(PALETTE.parent))
            self._watch.directoryChanged.connect(lambda _: QTimer.singleShot(200, self._load_theme))

        if demo:
            self._load_demo()
        else:
            cached = read_json(LIBRARY_CACHE) or []
            self.model.set_games(Game.from_dict(d) for d in cached if d.get("store") in self.stores)
            QTimer.singleShot(0, self.refresh)

    # --- theme -----------------------------------------------------------
    def _load_theme(self):
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
            mine = [g for g in self.model.games if g.store == s.id]
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
    refreshing = Property(bool, lambda s: bool(s._pending), notify=refreshingChanged)
    totalCount = Property(int, lambda s: len(s.model.groups), notify=storesChanged)

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
    def refreshLocal(self):
        """Cheap rescan when the window regains focus (Steam / Battle.net change outside Kura)."""
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
                error = error or covers.fill(games)
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

    @Slot(str)
    def loginBegin(self, store_id):
        store = self.stores[store_id]

        def work():
            info = store.login_begin()
            if "command" in info:
                def start():
                    self._detach(info["command"], info.get("env", {}), "", f"{store_id}-client")
                    self.toast.emit(f"Opening {store.name}; sign in there, then press Refresh")
                return start
            return lambda: self.loginReady.emit(store_id, info["url"], info["prompt"])
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

    protonVersions = Property("QVariantList", _proton_versions, notify=settingsChanged)

    @Slot(str)
    def play(self, key):
        g, store = self._guard(key)
        if not g:
            return
        opts = self._options_for(g)
        try:
            with runner.using(opts):
                cmd = store.launch(g)
            if opts.get("args") and g.store in ("epic", "gog", "amazon"):
                cmd.argv += shlex.split(opts["args"])
        except (StoreError, ValueError) as e:
            self.toast.emit(str(e))
            return
        if self._detach(cmd.argv, cmd.env, cmd.cwd, key):
            self.toast.emit(f"Launching {g.title}")
        else:
            self.toast.emit(f"Could not start {g.title} (log: {LOG_DIR})")

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
            self.toast.emit(f"{'Installed' if kind == 'install' else 'Removed'} {g.title}")
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
        self.model.set_games(games)
        self.pool.submit(lambda: (covers.fill(games), self._after.emit(self.model.touch)))
        self.model.jobs["gog:646570"] = {"kind": "install", "progress": 42.0}

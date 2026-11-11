"""Cornerplay: one library for Steam, Epic, GOG, Amazon and Battle.net."""
import argparse
import os
import signal
import sys
from pathlib import Path


def load_fonts(app):
    """Use the bundled fonts (OFL, cornerplay/fonts) so the app looks the same on every desktop:
    Nunito, rounded like the logo's letters (the desktop's own font if it cannot load)."""
    from PySide6.QtGui import QFont, QFontDatabase
    ok = [QFontDatabase.addApplicationFont(str(f)) >= 0
          for f in sorted((Path(__file__).parent / "fonts").glob("*.ttf"))]
    if any(ok) and "Nunito" in QFontDatabase.families():
        font = QFont("Nunito")
        font.setPointSizeF(app.font().pointSizeF())
        font.setHintingPreference(QFont.PreferNoHinting)
        app.setFont(font)


def auto_scale():
    """A big screen the desktop does not scale (a 4K monitor or TV at 100%): grow the interface
    so it is not tiny. Desktops that scale already (most do; Qt picks that up) are left alone."""
    import shutil
    import subprocess
    width, desk = 0, 1.0
    try:
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
            import json
            mons = json.loads(subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True,
                                             text=True, timeout=3).stdout or "[]")
            mon = next((m for m in mons if m.get("focused")), mons[0] if mons else {})
            width, desk = int(mon.get("width", 0)), float(mon.get("scale", 1.0))
        elif os.environ.get("XDG_SESSION_TYPE") == "x11" and shutil.which("xrandr"):
            import re
            out = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, timeout=3).stdout
            m = re.search(r" connected primary (\d+)x\d+", out) or re.search(r" connected (\d+)x\d+", out)
            width = int(m.group(1)) if m else 0
    except (OSError, ValueError, subprocess.SubprocessError):
        return 1.0
    if desk > 1.01 or width < 3200:
        return 1.0
    return min(2.5, round(width / 1920 * 4) / 4)  # 3840 wide -> 2x


def _note_screen_size(app):
    """Remember the main screen's size in pixels: gamescope draws games at it, also when a game
    starts from Steam through --play (no window to ask then)."""
    from .config import settings
    screen = app.primaryScreen()
    if not screen or app.platformName() == "offscreen":  # tests and headless runs have no real screen
        return
    size = screen.size() * screen.devicePixelRatio()
    wh = [int(size.width()), int(size.height())]
    if wh[0] > 0 and wh[1] > 0 and settings.get("screen_size") != wh:
        settings.set("screen_size", wh)


def check_qml():
    """Compile every QML file (catches syntax and reserved-word mistakes before a restart)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    try:
        from PySide6.QtWebEngineQuick import QtWebEngineQuick
        QtWebEngineQuick.initialize()
    except ImportError:
        pass
    app = QGuiApplication(["cornerplay"])
    engine = QQmlEngine()
    bad = 0
    for qml in sorted((Path(__file__).parent / "qml").glob("*.qml")):
        c = QQmlComponent(engine, QUrl.fromLocalFile(str(qml)), QQmlComponent.PreferSynchronous)
        errors = [e.toString() for e in c.errors()]
        if errors and "QtWebEngine" in " ".join(errors) and "is not installed" in " ".join(errors):
            print(f"skip  {qml.name} (Qt WebEngine not installed)")
            continue
        print(("ok    " if not errors else "FAIL  ") + qml.name)
        for e in errors:
            print("      " + e)
        bad += bool(errors)
    del app
    return 1 if bad else 0


def fetch_backends():
    """Download the legendary / gogdl / nile release binaries into Cornerplay's data dir,
    each checked against the SHA-256 GitHub lists for it."""
    from .config import BACKEND_REPOS, BIN_DIR, find_tool
    from .host import BUNDLED_BIN
    from .net import download_checked, github_asset
    failed = 0
    for name, repo in BACKEND_REPOS.items():
        existing = find_tool(name)
        if existing and not existing.startswith((str(BIN_DIR), BUNDLED_BIN)):
            print(f"{name}: already available at {existing}")
            continue
        try:
            tag, url, sha = github_asset(repo, lambda n, name=name: n == f"{name}_linux_x86_64")
            print(f"{name} {tag}: downloading {url}" + ("" if sha else " (no checksum published)"))
            print(f"{name}: installed to {download_checked(url, BIN_DIR / name, sha, mode=0o755)}")
        except Exception as e:
            print(f"{name}: not downloaded: {e}")
            failed += 1
    return 1 if failed else 0


def status():
    from .stores import all_stores
    for s in all_stores():
        if s.id == "custom":
            continue
        if s.problem():
            state = s.problem()
        elif s.id == "battlenet":
            state = s.account() or "ready; install the Battle.net app from its tile"
        else:
            state = ("signed in" + (f" as {s.account()}" if s.account() else "")) if s.logged_in() else "ready, not signed in"
        print(f"{s.name:14} {state}")
    return 0


def play(key):
    """Start one game in the foreground: download saves, run it, upload saves.
    Steam (and Game Mode) treat the game as running for as long as this process lives."""
    import shlex
    from . import runner, saves, session
    from .config import CACHE_DIR, LOG_DIR, game_options, read_json
    from .stores import all_stores
    from .stores.base import Game
    stores = {s.id: s for s in all_stores() if s.id != "steam"}
    cached = {d["store"] + ":" + d["id"]: d for d in read_json(CACHE_DIR / "library.json") or []}
    if key not in cached or cached[key]["store"] not in stores:
        session.notify("Cornerplay", f"Game not found: {key}. Open Cornerplay once to refresh the library.")
        return 1
    game = Game.from_dict(cached[key])
    store = stores[game.store]
    opts = game_options.get("battlenet:battlenet-app" if game.store == "battlenet" else key)
    sync = saves.enabled_for(game)
    if sync:
        res = saves.sync(game, "download")
        if res["status"] == "conflict":
            sync = False  # never overwrite either side without asking; the app asks next time
            session.notify(f"{game.title}: saves not synced",
                           "Cloud and local saves both changed. Open Cornerplay to choose which to keep.")
    try:
        with runner.using(opts):
            cmd = store.launch(game)
    except Exception as e:
        session.notify(f"{game.title} did not start", str(e))
        return 1
    if opts.get("args"):
        cmd.argv += shlex.split(opts["args"])
    log = str(LOG_DIR / (key.replace(":", "_") + ".log"))
    return session.run(game, cmd.argv, cmd.env, cmd.cwd, log, sync)


def main():
    ap = argparse.ArgumentParser(prog="cornerplay", description=__doc__)
    ap.add_argument("--fetch-backends", action="store_true",
                    help="download the legendary, gogdl and nile CLIs into ~/.local/share/cornerplay/bin")
    ap.add_argument("--status", action="store_true", help="print what each store backend needs and exit")
    ap.add_argument("--tv", action="store_true", help="start full screen in TV mode (controller friendly)")
    ap.add_argument("--play", metavar="GAME",
                    help="start a game and wait for it to close (used by the shortcuts added to Steam)")
    ap.add_argument("--add-to-steam", action="store_true",
                    help="add Cornerplay to Steam (Game Mode) with artwork; closes and reopens Steam if needed")
    ap.add_argument("--demo", action="store_true", help="open with sample games (nothing is launched)")
    ap.add_argument("--check", action="store_true", help="compile every QML file and report errors, then exit")
    args = ap.parse_args()
    if args.fetch_backends:
        return fetch_backends()
    if args.check:
        return check_qml()
    if args.status:
        return status()
    if args.play:
        return play(args.play)
    if args.add_to_steam:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtGui import QGuiApplication
        _app = QGuiApplication(sys.argv[:1])  # needed to draw the artwork
        load_fonts(_app)
        from . import steamshortcut, theme
        try:
            n = steamshortcut.add_with_restart(theme.current())
        except Exception as e:
            print(f"Not added: {e}")
            return 1
        print(f"Added Cornerplay to Steam for {n} account(s). It opens in TV mode from Game Mode.")
        return 0

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache
    from PySide6.QtQml import QQmlApplicationEngine, QQmlNetworkAccessManagerFactory

    from .app import AioLaunch
    from .config import CACHE_DIR
    from .gamepad import Gamepad

    class CachingFactory(QQmlNetworkAccessManagerFactory):
        """Gives QML images an on-disk HTTP cache so covers load once."""

        def create(self, parent):
            nam = QNetworkAccessManager(parent)
            cache = QNetworkDiskCache(nam)
            cache.setCacheDirectory(str(CACHE_DIR / "covers"))
            cache.setMaximumCacheSize(1 << 30)
            nam.setCache(cache)
            return nam

    # The built-in sign-in window needs Qt's web engine. Importing it here would load
    # Chromium on every start (~35 MB, ~0.1 s), so only set the two options it needs
    # before the app object exists; QML loads the engine when the sign-in window opens.
    from PySide6.QtCore import QLibraryInfo
    qml_dir = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.QmlImportsPath))
    web_login = (qml_dir / "QtWebEngine" / "qmldir").is_file()
    if web_login:
        from PySide6.QtCore import QCoreApplication, Qt
        from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
        QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        QQuickWindow.setGraphicsApi(QSGRendererInterface.OpenGL)

    # Interface size (Settings > Appearance): Qt scales everything; a QT_SCALE_FACTOR already set wins.
    try:
        from .config import settings as _settings
        scale = float(_settings.get("ui_scale") or 0.0)
    except (TypeError, ValueError):
        scale = 0.0
    if scale <= 0:
        scale = auto_scale()
    if abs(scale - 1.0) > 0.01 and "QT_SCALE_FACTOR" not in os.environ:
        os.environ["QT_SCALE_FACTOR"] = f"{scale:.2f}"
    # The window class must say "cornerplay" so desktops (KDE on the Steam Deck, X11 docks)
    # match the window to cornerplay.desktop and show its icon. Qt builds the class from
    # argv[0] and the application name; started as "python3 -m cornerplay" both were wrong.
    app = QGuiApplication(["cornerplay"])
    _note_screen_size(app)
    app.setApplicationName("cornerplay")
    app.setApplicationDisplayName("Cornerplay")
    from .host import FLATPAK_ID
    app.setDesktopFileName(FLATPAK_ID or "cornerplay")  # the Wayland app id: matches the .desktop file
    load_fonts(app)
    here = Path(__file__).parent
    icon = QIcon(str(here / "cornerplay.svg"))
    for png in sorted((here / "icons" / "app").glob("cornerplay-*.png")):
        icon.addFile(str(png))
    app.setWindowIcon(icon)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    cornerplay = AioLaunch(demo=args.demo)
    cornerplay.web_login = web_login
    engine = QQmlApplicationEngine()
    factory = CachingFactory()
    engine.setNetworkAccessManagerFactory(factory)
    ctx = engine.rootContext()
    ctx.setContextProperty("app", cornerplay)
    ctx.setContextProperty("library", cornerplay.proxy)
    ctx.setContextProperty("tvLibrary", cornerplay.tvProxy)
    ctx.setContextProperty("tvNextLibrary", cornerplay.tvNextProxy)
    gamepad = Gamepad(app)
    ctx.setContextProperty("pad", gamepad)
    cornerplay.gamepad_available = gamepad.available
    ctx.setContextProperty("startTv", args.tv)
    ctx.setContextProperty("webLogin", web_login)
    # TV-mode trailers need Qt Multimedia's QML module; without it they are simply left out.
    ctx.setContextProperty("canPlayVideo", (qml_dir / "QtMultimedia" / "qmldir").is_file())
    # Say why when the window cannot be built (a QML error), instead of quitting silently.
    engine.warnings.connect(lambda ws: [print("QML:", w.toString(), file=sys.stderr) for w in ws])
    engine.load(QUrl.fromLocalFile(str(here / "qml" / "Main.qml")))
    if not engine.rootObjects():
        print("Cornerplay could not open its window (see the QML errors above).", file=sys.stderr)
        return 1
    app.aboutToQuit.connect(cornerplay.shutdown)
    code = app.exec()
    del engine
    return code


if __name__ == "__main__":
    sys.exit(main())

"""Cornerplay: one library for Steam, Epic, GOG, Amazon and Battle.net."""
import argparse
import os
import signal
import sys
from pathlib import Path


def load_fonts(app):
    """Use the bundled Inter font (OFL, cornerplay/fonts) so the app looks the same on every desktop."""
    from PySide6.QtGui import QFont, QFontDatabase
    ok = [QFontDatabase.addApplicationFont(str(f)) >= 0
          for f in sorted((Path(__file__).parent / "fonts").glob("*.ttf"))]
    if any(ok):
        font = QFont("Inter")
        font.setPointSizeF(app.font().pointSizeF())
        font.setHintingPreference(QFont.PreferNoHinting)
        app.setFont(font)


def fetch_backends():
    """Download the legendary / gogdl / nile release binaries into Cornerplay's data dir."""
    import requests
    from .config import BACKEND_URLS, BIN_DIR, find_tool
    for name, url in BACKEND_URLS.items():
        existing = find_tool(name)
        if existing and not existing.startswith(str(BIN_DIR)):
            print(f"{name}: already available at {existing}")
            continue
        dest = BIN_DIR / name
        print(f"{name}: downloading {url}")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        os.chmod(tmp, 0o755)
        tmp.replace(dest)
        print(f"{name}: installed to {dest}")
    return 0


def status():
    from .app import AioLaunch  # noqa: F401  (imports every store)
    from .stores.amazon import Amazon
    from .stores.battlenet import BattleNet
    from .stores.epic import Epic
    from .stores.gog import Gog
    from .stores.steam import Steam
    for s in (Steam(), Epic(), Gog(), Amazon(), BattleNet()):
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
    from .stores.amazon import Amazon
    from .stores.base import Game
    from .stores.battlenet import BattleNet
    from .stores.epic import Epic
    from .stores.gog import Gog
    stores = {s.id: s for s in (Epic(), Gog(), Amazon(), BattleNet())}
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
    args = ap.parse_args()
    if args.fetch_backends:
        return fetch_backends()
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

    # The window class must say "cornerplay" so desktops (KDE on the Steam Deck, X11 docks)
    # match the window to cornerplay.desktop and show its icon. Qt builds the class from
    # argv[0] and the application name; started as "python3 -m cornerplay" both were wrong.
    app = QGuiApplication(["cornerplay"])
    app.setApplicationName("cornerplay")
    app.setApplicationDisplayName("Cornerplay")
    app.setDesktopFileName("cornerplay")  # the Wayland app id
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
    gamepad = Gamepad(app)
    ctx.setContextProperty("pad", gamepad)
    ctx.setContextProperty("startTv", args.tv)
    ctx.setContextProperty("webLogin", web_login)
    # TV-mode trailers need Qt Multimedia's QML module; without it they are simply left out.
    ctx.setContextProperty("canPlayVideo", (qml_dir / "QtMultimedia" / "qmldir").is_file())
    engine.load(QUrl.fromLocalFile(str(here / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    app.aboutToQuit.connect(cornerplay.shutdown)
    code = app.exec()
    del engine
    return code


if __name__ == "__main__":
    sys.exit(main())

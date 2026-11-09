"""Kura: one library for Steam, Epic, GOG, Amazon and Battle.net."""
import argparse
import os
import signal
import sys
from pathlib import Path


def fetch_backends():
    """Download the legendary / gogdl / nile release binaries into Kura's data dir."""
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
    from .app import Kura  # noqa: F401  (imports every store)
    from .stores.amazon import Amazon
    from .stores.battlenet import BattleNet
    from .stores.epic import Epic
    from .stores.gog import Gog
    from .stores.steam import Steam
    for s in (Steam(), Epic(), Gog(), Amazon(), BattleNet()):
        state = s.problem() or ("signed in" + (f" as {s.account()}" if s.account() else "")
                                if s.logged_in() else "ready, not signed in")
        print(f"{s.name:14} {state}")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="kura", description=__doc__)
    ap.add_argument("--fetch-backends", action="store_true",
                    help="download the legendary, gogdl and nile CLIs into ~/.local/share/kura/bin")
    ap.add_argument("--status", action="store_true", help="print what each store backend needs and exit")
    ap.add_argument("--tv", action="store_true", help="start full screen in TV mode (controller friendly)")
    ap.add_argument("--demo", action="store_true", help="open with sample games (nothing is launched)")
    args = ap.parse_args()
    if args.fetch_backends:
        return fetch_backends()
    if args.status:
        return status()

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache
    from PySide6.QtQml import QQmlApplicationEngine, QQmlNetworkAccessManagerFactory

    from .app import Kura
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

    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("Kura")
    app.setDesktopFileName("kura")
    here = Path(__file__).parent
    app.setWindowIcon(QIcon(str(here / "kura.svg")))
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    kura = Kura(demo=args.demo)
    engine = QQmlApplicationEngine()
    factory = CachingFactory()
    engine.setNetworkAccessManagerFactory(factory)
    ctx = engine.rootContext()
    ctx.setContextProperty("app", kura)
    ctx.setContextProperty("library", kura.proxy)
    gamepad = Gamepad(app)
    ctx.setContextProperty("pad", gamepad)
    ctx.setContextProperty("startTv", args.tv)
    engine.load(QUrl.fromLocalFile(str(here / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    app.aboutToQuit.connect(kura.shutdown)
    code = app.exec()
    del engine
    return code


if __name__ == "__main__":
    sys.exit(main())

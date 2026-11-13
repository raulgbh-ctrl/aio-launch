"""Screenshots of Cornerplay's demo library, with no window on screen (for docs and design checks).

    python3 tools/shoot.py OUTDIR [actions...]

Actions run one after another, 0.6 s apart after a 2.5 s start:
    wait:MS       wait longer          shot:NAME     save OUTDIR/NAME.png
    key:Name      a key (Qt.Key_Name)  ctrl:X        Ctrl+X (ctrl:Comma for Ctrl+,)
    type:text     type text            click:x,y     a click
    size:WxH      resize the window    recap:KEY     show the after-session card for a demo game
    tv            start in TV mode
Environment: SHOT_CFG='{"view": "list"}' runs with these settings in a throwaway copy of your
config; SHOT_SEEN=key1,key2 marks demo games as bought an hour ago (the NEW ribbon);
SHOT_BACKEND=software renders without a GPU.
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", os.environ.get("SHOT_BACKEND", ""))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = sys.argv[1]; acts = sys.argv[2:]
import json, tempfile, shutil
cfg = os.environ.get("SHOT_CFG", "{}")  # always a throwaway copy: your own settings are never written
if cfg is not None:
    d = tempfile.mkdtemp(prefix="cpcfg")
    src = os.path.expanduser("~/.config/cornerplay")
    if os.path.isdir(src):
        shutil.copytree(src, d + "/cornerplay", ignore=shutil.ignore_patterns("*.lock"))
    os.makedirs(d + "/cornerplay", exist_ok=True)
    try:
        st = json.load(open(d + "/cornerplay/settings.json"))
    except (OSError, ValueError):
        st = {}
    st.update(json.loads(cfg or "{}"))
    json.dump(st, open(d + "/cornerplay/settings.json", "w"))
    os.environ["XDG_CONFIG_HOME"] = d
    if os.environ.get("SHOT_SEEN"):
        import time
        seen = {"stores": ["steam", "epic", "gog", "amazon", "battlenet"], "keys": {k: int(time.time()) - 3600 for k in os.environ["SHOT_SEEN"].split(",")}}
        json.dump(seen, open(d + "/cornerplay/first_seen.json", "w"))
sys.argv = ["cornerplay", "--demo"] + (["--tv"] if "tv" in acts else [])
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt, QPointF, QEvent
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
import cornerplay.__main__ as m
import cornerplay.app as A
_oi = A.AioLaunch.__init__
def _ni(self, *a, **k):
    _oi(self, *a, **k); A._shot_instance = self
A.AioLaunch.__init__ = _ni
orig = QApplication.exec
def run(*_):
    win = [w for w in QGuiApplication.topLevelWindows() if w.isVisible() or True][0]
    W, H = map(int, os.environ.get("SHOT_SIZE", "1600x960").split("x")); win.resize(W, H); win.show()
    t = 2500
    for a in acts:
        if a == "tv": continue
        k, _, v = a.partition(":")
        if k == "wait": t += int(v); continue
        def do(k=k, v=v):
            w = [x for x in QGuiApplication.topLevelWindows() if x.isVisible()][0]
            if k == "shot":
                w.grabWindow().save(f"{out}/{v}.png"); print("saved", v, flush=True)
            elif k == "key":
                code = getattr(Qt, "Key_" + v)
                for typ in (QEvent.KeyPress, QEvent.KeyRelease):
                    QGuiApplication.sendEvent(w, QKeyEvent(typ, code, Qt.NoModifier))
            elif k == "type":
                for ch in v:
                    for typ in (QEvent.KeyPress, QEvent.KeyRelease):
                        QGuiApplication.sendEvent(w, QKeyEvent(typ, 0, Qt.NoModifier, ch))
            elif k == "ctrl":
                code = getattr(Qt, "Key_" + v) if len(v) > 1 else ord(v.upper())
                for typ in (QEvent.KeyPress, QEvent.KeyRelease):
                    QGuiApplication.sendEvent(w, QKeyEvent(typ, code, Qt.ControlModifier))
            elif k == "recap":
                import cornerplay.app as A
                inst = A._shot_instance
                inst._recap(v, 4380)
            elif k == "size":
                W, H = map(int, v.split("x")); w.setMinimumSize(w.minimumSize().boundedTo(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(W, H))); w.resize(W, H)
            elif k == "click":
                x, y = map(float, v.split(","))
                for typ in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                    QGuiApplication.sendEvent(w, QMouseEvent(typ, QPointF(x, y), QPointF(x, y), Qt.LeftButton, Qt.LeftButton if typ == QEvent.MouseButtonPress else Qt.NoButton, Qt.NoModifier))
        QTimer.singleShot(t, do); t += 600
    QTimer.singleShot(t + 500, QApplication.quit)
    return orig()
QApplication.exec = run
m.main()

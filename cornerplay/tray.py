"""The tray icon, one Cornerplay at a time, and starting with the PC.

- Tray: while a game runs the window steps aside into the tray (Settings > General, on by
  default) and comes back when the game closes. With "Keep running in the tray" closing the
  window leaves Cornerplay in the tray. The tray menu opens the window, quits a running game,
  starts a recent one, or quits Cornerplay. Without a tray (Steam's Game Mode, a bar without
  one) the window simply stays.
- One at a time: starting Cornerplay again shows the window that is already running (it may be
  in the tray) instead of opening a second copy. The socket sits in XDG_RUNTIME_DIR, which
  the Flatpak's instances share too (app/<id>/).
- Start with the PC: an autostart entry (~/.config/autostart) that opens Cornerplay in the
  tray; in the Flatpak the Background portal makes it.
"""
import os
import shlex
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from . import host
from .config import XDG_CONFIG, settings

AUTOSTART = XDG_CONFIG / "autostart" / "cornerplay.desktop"


# --- one Cornerplay at a time ----------------------------------------------------------
def _socket_path():
    run = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/cornerplay-{os.getuid()}"
    base = Path(run) / "app" / host.FLATPAK_ID if host.IN_FLATPAK else Path(run)
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "cornerplay.sock")


def hand_over(message: str) -> bool:
    """True when another Cornerplay is running and took the message ("show", "tv", "overlay")."""
    s = QLocalSocket()
    s.connectToServer(_socket_path())
    if not s.waitForConnected(500):
        return False
    s.write(message.encode() + b"\n")
    s.flush()
    s.waitForBytesWritten(500)
    s.disconnectFromServer()
    return True


class Instance(QObject):
    """Listens for later starts and passes their message on."""

    def __init__(self, on_message, parent=None):
        super().__init__(parent)
        self._on_message = on_message
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        path = _socket_path()
        if not self.server.listen(path):
            QLocalServer.removeServer(path)  # left over from a copy that crashed
            self.server.listen(path)
        self.server.newConnection.connect(self._accept)

    def _accept(self):
        while self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            conn.readyRead.connect(lambda c=conn: self._read(c))

    def _read(self, conn):
        for line in bytes(conn.readAll()).decode("utf-8", "replace").splitlines():
            if line.strip() in ("show", "tv", "overlay"):
                self._on_message(line.strip())
        conn.disconnectFromServer()


# --- start with the PC -----------------------------------------------------------------
def _launcher():
    exe = shutil.which("cornerplay") or str(Path.home() / ".local/bin/cornerplay")
    if os.path.exists(exe):
        return [exe]
    return [sys.executable, "-m", "cornerplay"]


def set_autostart(on: bool) -> str:
    """Make or remove the autostart entry. Returns "" or what went wrong."""
    if host.IN_FLATPAK:
        err = _portal_autostart(on)
        # Not every desktop's portal has Background (Hyprland's and wlroots' do not): then the
        # entry is written on the host, the same file the portal would have made.
        return _host_autostart(on) if err else ""
    try:
        if not on:
            AUTOSTART.unlink(missing_ok=True)
            return ""
        AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
        cmd = " ".join(shlex.quote(a) for a in _launcher() + ["--background"])
        AUTOSTART.write_text(
            "[Desktop Entry]\nType=Application\nName=Cornerplay\nComment=Your game library, in the tray\n"
            f"Exec={cmd}\nIcon=cornerplay\nTerminal=false\nX-GNOME-Autostart-enabled=true\n"
            "X-KDE-autostart-after=panel\n")
        return ""
    except OSError as e:
        return str(e)


def _host_autostart(on: bool) -> str:
    import subprocess
    name = f"{host.FLATPAK_ID}.desktop"
    entry = ("[Desktop Entry]\nType=Application\nName=Cornerplay\nComment=Your game library, in the tray\n"
             f"Exec=flatpak run {host.FLATPAK_ID} --background\nIcon={host.FLATPAK_ID}\nTerminal=false\n"
             f"X-Flatpak={host.FLATPAK_ID}\nX-GNOME-Autostart-enabled=true\n")
    script = ('d="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"; '
              + ('mkdir -p "$d" && printf "%s" "$2" > "$d/$1"' if on else 'rm -f "$d/$1"'))
    try:
        r = subprocess.run(host.argv(["sh", "-c", script, "sh", name, entry]), capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    return "" if r.returncode == 0 else (r.stderr.strip() or "could not write the autostart entry")


def autostart_on() -> bool:
    if host.IN_FLATPAK:
        return bool(settings.get("start_with_pc"))
    return AUTOSTART.is_file()


def _portal_autostart(on: bool) -> str:
    """The Background portal writes the autostart entry for a Flatpak (it may ask the user)."""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusMessage
    except ImportError:
        return "Qt's D-Bus module is missing"
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return "no session bus"
    msg = QDBusMessage.createMethodCall("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                                        "org.freedesktop.portal.Background", "RequestBackground")
    options = {"reason": "Start Cornerplay in the tray when you log in", "autostart": bool(on),
               "commandline": ["cornerplay", "--background"], "dbus-activatable": False}
    msg.setArguments(["", options])
    reply = bus.call(msg, timeout=10000)
    if reply.type() == QDBusMessage.ErrorMessage:
        return reply.errorMessage() or "the portal said no"
    return ""


# --- the tray icon ---------------------------------------------------------------------
class Tray(QObject):
    def __init__(self, qapp, window, cornerplay, start_hidden=False):
        super().__init__(qapp)
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon
        self.app, self.win, self.cp = qapp, window, cornerplay
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self._hidden_for_game = False
        self.icon = QSystemTrayIcon(qapp.windowIcon(), self)
        self.icon.setToolTip("Cornerplay")
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._fill_menu)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        window.visibleChanged.connect(lambda _v: self._update_icon())
        cornerplay.nowPlayingChanged.connect(self._playing_changed)
        cornerplay.settingsChanged.connect(self._update_icon)
        cornerplay.tray = self
        qapp.setQuitOnLastWindowClosed(False)  # the window may be in the tray; Main.qml quits on close
        if start_hidden and not self.available:
            window.setProperty("hiddenAtStart", False)  # no tray to sit in: a normal start
        self._update_icon()

    def keep_on_close(self) -> bool:
        return self.available and bool(settings.get("close_to_tray"))

    def _update_icon(self):
        want = self.available and (not self.win.isVisible() or bool(settings.get("close_to_tray"))
                                   or self._hidden_for_game)
        self.icon.setVisible(want)

    def show_window(self, tv=False):
        self._hidden_for_game = False
        self.win.setProperty("hiddenAtStart", False)
        if tv:
            self.win.setProperty("tv", True)
        if self.win.property("tv"):
            self.win.showFullScreen()
        else:
            self.win.show()
        self.win.raise_()
        self.win.requestActivate()
        self._update_icon()

    def _activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.win.isVisible() and not self._hidden_for_game:
                self.win.hide()
            else:
                self.show_window()

    def _playing_changed(self):
        playing = self.cp._now_playing()
        if playing and self.available and settings.get("tray_while_playing") and self.win.isVisible() \
                and not self.win.property("tv"):
            self._hidden_for_game = True
            self.win.hide()
        elif not playing and self._hidden_for_game:
            QTimer.singleShot(1500, self._back_after_game)  # let the game's window go first
        self._update_icon()

    def _back_after_game(self):
        if self._hidden_for_game and not self.cp._now_playing():
            self.show_window()

    def _fill_menu(self):
        m = self.menu
        m.clear()
        m.addAction("Open Cornerplay").triggered.connect(lambda: self.show_window())
        playing = self.cp._now_playing()
        if playing:
            m.addSeparator()
            for p in playing:
                sub = m.addMenu(f"Playing {p['title']}")
                sub.addAction("Quit game").triggered.connect(lambda _=False, k=p["key"]: self.cp.quitGame(k, False))
                sub.addAction("Force close").triggered.connect(lambda _=False, k=p["key"]: self.cp.quitGame(k, True))
        recent = [r for r in self.cp._recent_games() if self.cp.launchTarget(r["key"])][:6]
        if recent:
            m.addSeparator()
            sub = m.addMenu("Play")
            for r in recent:
                sub.addAction(r["title"]).triggered.connect(
                    lambda _=False, k=r["key"]: self.cp.play(self.cp.launchTarget(k)))
        m.addSeparator()
        m.addAction("Quit Cornerplay").triggered.connect(self.app.quit)

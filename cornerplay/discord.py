"""Discord Rich Presence: "Playing <game>" on your Discord profile while a game started from
Cornerplay runs. Discord sees Steam games by itself, but not Epic, GOG or Amazon games under
Proton, so the play session (session.py) tells it.

Off unless switched on (Settings > Advanced) and given a Discord application id: make a free
application named "Cornerplay" at https://discord.com/developers/applications and paste its
Application ID. Talks to the desktop Discord app over its local socket (also Flatpak and Snap
Discord); nothing goes over the network from here, and nothing happens when Discord is closed.
"""
import json
import os
import socket
import struct
import threading
import uuid

from .config import settings

HANDSHAKE, FRAME, CLOSE = 0, 1, 2


def _sockets():
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    dirs = [base, os.path.join(base, "app/com.discordapp.Discord"), os.path.join(base, "app/dev.vencord.Vesktop"),
            os.path.join(base, "snap.discord"), os.environ.get("TMPDIR", "/tmp")]
    return [os.path.join(d, f"discord-ipc-{i}") for d in dirs for i in range(10)]


def enabled() -> bool:
    return bool(settings.get("discord_presence") and app_id())


def app_id() -> str:
    v = str(settings.get("discord_app_id") or "").strip()
    return v if v.isdigit() else ""


class Presence:
    """One game's presence for as long as it runs: show(), then clear() when it closes.
    Waits for Discord in the background if it is not open yet."""

    def __init__(self, client_id):
        self.client_id = client_id
        self.sock = None
        self.activity = None
        self.stop = threading.Event()
        self.thread = None

    # -- wire format: little-endian op and length, then JSON
    def _send(self, op, payload):
        data = json.dumps(payload).encode()
        self.sock.sendall(struct.pack("<ii", op, len(data)) + data)

    def _recv(self):
        head = self._exact(8)
        op, length = struct.unpack("<ii", head)
        if not 0 <= length <= 1 << 20:
            raise OSError("bad frame from Discord")
        return op, json.loads(self._exact(length) or b"{}")

    def _exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise OSError("Discord closed the connection")
            buf += chunk
        return buf

    def _connect(self):
        for path in _sockets():
            if not os.path.exists(path):
                continue
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(5)
            try:
                s.connect(path)
                self.sock = s
                self._send(HANDSHAKE, {"v": 1, "client_id": self.client_id})
                op, reply = self._recv()
                if op == FRAME and reply.get("evt") == "READY":
                    return True
            except (OSError, ValueError):
                pass
            s.close()
            self.sock = None
        return False

    def _set(self, activity):
        self._send(FRAME, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": activity},
                           "nonce": str(uuid.uuid4())})
        self._recv()

    def _loop(self):
        while not self.stop.is_set():
            try:
                if self.sock is None and not self._connect():
                    self.stop.wait(20)  # Discord not open (yet): look again now and then
                    continue
                self._set(self.activity)
                self.stop.wait()       # keep the connection: Discord drops the presence when it closes
            except (OSError, ValueError):
                self._drop()
                self.stop.wait(20)
        if self.sock:
            try:
                self._set(None)
                self._send(CLOSE, {})
            except (OSError, ValueError):
                pass
            self._drop()

    def _drop(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def show(self, activity):
        self.activity = activity
        self.thread = threading.Thread(target=self._loop, daemon=True, name="discord-presence")
        self.thread.start()

    def clear(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=6)


STORE_NAMES = {"epic": "Epic Games", "gog": "GOG", "amazon": "Amazon Games", "battlenet": "Battle.net",
               "custom": "", "steam": "Steam", "itch": "itch.io", "retro": "Retro games"}


def activity_for(game, started):
    """The presence for a game: its title, its store, the time it started and (when the cover
    is a web address) its cover."""
    act = {"type": 0, "details": game.title[:128], "timestamps": {"start": int(started)},
           "assets": {"large_text": game.title[:128]}}
    store = STORE_NAMES.get(game.store, "")
    act["state"] = f"via Cornerplay · {store}" if store else "via Cornerplay"
    cover = game.cover or ""
    if cover.startswith("https://"):
        act["assets"]["large_image"] = cover
    return act


def start(game, started):
    """Show the game on Discord if switched on; returns something to clear() later, or None."""
    if not enabled():
        return None
    p = Presence(app_id())
    p.show(activity_for(game, started))
    return p

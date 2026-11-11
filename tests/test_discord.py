import json
import os
import socket
import struct
import threading

from cornerplay import discord
from cornerplay.config import settings
from cornerplay.stores.base import Game


def test_off_unless_switched_on(monkeypatch):
    monkeypatch.setitem(settings.data, "discord_presence", True)
    monkeypatch.setitem(settings.data, "discord_app_id", "not-a-number")
    assert discord.start(Game("epic", "x", "X"), 0) is None


def test_activity():
    g = Game("gog", "1", "Gwent", cover="https://images.gog.com/x.jpg")
    a = discord.activity_for(g, 1000.5)
    assert a["details"] == "Gwent" and a["state"] == "via Cornerplay · GOG"
    assert a["timestamps"]["start"] == 1000 and a["assets"]["large_image"].startswith("https://")
    assert "large_image" not in discord.activity_for(Game("custom", "1", "X", cover="file:///home/x.png"), 0)["assets"]


def test_talks_to_a_fake_discord(tmp_path, monkeypatch):
    """A stand-in Discord socket: handshake, then SET_ACTIVITY with the game, then a clear on exit."""
    path = str(tmp_path / "discord-ipc-0")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(1)
    got = []

    def serve():
        c, _ = srv.accept()

        def read():
            op, n = struct.unpack("<ii", c.recv(8))
            return op, json.loads(c.recv(n))

        def reply(obj):
            data = json.dumps(obj).encode()
            c.sendall(struct.pack("<ii", 1, len(data)) + data)
        got.append(read())
        reply({"evt": "READY"})
        for _ in range(2):
            got.append(read())
            reply({"evt": None})
        c.close()
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setitem(settings.data, "discord_presence", True)
    monkeypatch.setitem(settings.data, "discord_app_id", "123")
    p = discord.start(Game("epic", "a", "Hades"), 50)
    for _ in range(50):
        if len(got) >= 2:
            break
        threading.Event().wait(0.05)
    p.clear()
    t.join(3)
    assert got[0] == (0, {"v": 1, "client_id": "123"})
    assert got[1][1]["args"]["activity"]["details"] == "Hades"
    assert got[2][1]["args"]["activity"] is None  # cleared when the game closed
    os.unlink(path)

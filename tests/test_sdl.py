import hashlib
import io
import zipfile

import pytest

from cornerplay import sdl


def _wheel(payload=b"\x7fELF fake sdl"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(sdl.MEMBER, payload)
        z.writestr("sdl2dll/dll/libSDL2_ttf-2.0.so", b"not needed")
    return buf.getvalue()


class Resp:
    def __init__(self, content): self.content = content
    def raise_for_status(self): pass


def test_fetch_checks_and_extracts_only_sdl(tmp_path, monkeypatch):
    monkeypatch.setattr(sdl, "PRIVATE", tmp_path / "lib" / "libSDL2-2.0.so.0")
    wheel = _wheel()
    monkeypatch.setattr(sdl, "WHEEL_SHA256", hashlib.sha256(wheel).hexdigest())
    from cornerplay import net
    monkeypatch.setattr(net.requests, "get", lambda *a, **k: Resp(wheel), raising=False)
    path = sdl.fetch()
    assert open(path, "rb").read() == b"\x7fELF fake sdl"
    assert sorted(p.name for p in (tmp_path / "lib").iterdir()) == ["libSDL2-2.0.so.0"]
    assert sdl.candidates()[-1] == str(sdl.PRIVATE)  # the system's copy is always tried first


def test_fetch_refuses_a_changed_download(tmp_path, monkeypatch):
    monkeypatch.setattr(sdl, "PRIVATE", tmp_path / "libSDL2-2.0.so.0")
    from cornerplay import net
    monkeypatch.setattr(net.requests, "get", lambda *a, **k: Resp(_wheel(b"tampered")), raising=False)
    with pytest.raises(RuntimeError):
        sdl.fetch()
    assert not sdl.PRIVATE.exists()

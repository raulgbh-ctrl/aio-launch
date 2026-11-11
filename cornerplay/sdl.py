"""SDL2, which Cornerplay reads controllers through, always there: the system's copy when it
has one, otherwise a private copy downloaded into ~/.local/share/cornerplay/lib (no root).

The private copy is the libSDL2 from the pysdl2-dll package on PyPI (a manylinux build that
runs on any distribution), pinned to one release and checked against its SHA-256 before use.
The installer fetches it when the system has no SDL2 (`cornerplay --fetch-sdl`), and the app
fetches it by itself in the background if it is missing at start-up.
"""
import ctypes
import ctypes.util
import io
import os
import zipfile

from .config import DATA_DIR

PRIVATE = DATA_DIR / "lib" / "libSDL2-2.0.so.0"
WHEEL_URL = ("https://files.pythonhosted.org/packages/5d/6e/07ec92ba241b2aa941abf478e96c1474f2c5975b61d84303fbcb2ba1dcc9/"
             "pysdl2_dll-2.32.10-py2.py3-none-manylinux2014_x86_64.whl")
WHEEL_SHA256 = "12b136c38114ae0f8a85453a879795ba5d61663d98673ba19c36c3008ff00353"
MEMBER = "sdl2dll/dll/libSDL2-2.0.so"


def candidates():
    """Where to load SDL2 from, in order: the system's, then the private copy."""
    out = ["libSDL2-2.0.so.0"]  # direct; find_library runs ldconfig (~25 ms), so only after
    found = ctypes.util.find_library("SDL2")
    if found:
        out.append(found)
    out.append(str(PRIVATE))
    return out


def system_has_it() -> bool:
    if ctypes.util.find_library("SDL2"):
        return True
    return any(os.path.exists(p) for p in ("/usr/lib/libSDL2-2.0.so.0", "/usr/lib64/libSDL2-2.0.so.0",
                                           "/usr/lib/x86_64-linux-gnu/libSDL2-2.0.so.0"))


def available() -> bool:
    return system_has_it() or PRIVATE.is_file()


def can_fetch() -> bool:
    return os.uname().machine == "x86_64"


def fetch() -> str:
    """Download the pinned SDL2 build, check it, put libSDL2 in place. Returns its path."""
    import hashlib
    from .net import requests
    if not can_fetch():
        raise RuntimeError("A private SDL2 is only available for x86_64; install your distribution's SDL2")
    r = requests.get(WHEEL_URL, timeout=120)
    r.raise_for_status()
    if hashlib.sha256(r.content).hexdigest() != WHEEL_SHA256:
        raise RuntimeError("The SDL2 download was damaged or changed (checksum mismatch)")
    data = zipfile.ZipFile(io.BytesIO(r.content)).read(MEMBER)
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PRIVATE.with_suffix(".part")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o755)
    os.replace(tmp, PRIVATE)
    return str(PRIVATE)

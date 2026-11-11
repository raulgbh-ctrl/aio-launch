"""Download and unpack one itch.io game: python3 -m cornerplay.itchdl <game id> <key id> <folder> <linux|windows>.

Prints "Progress: NN.N" and the speed, the way legendary and gogdl do, so Cornerplay shows
an install like any other. Picks the game's own download for the platform (not soundtracks,
books or demos of other platforms), unpacks zip and tar archives into the folder (never
outside it), and notes which program starts the game in <folder>/.cornerplay-itch.json.
"""
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import zipfile

from .net import requests
from .stores.itch import API, AUTH_FILE, MANIFEST
from .config import read_json, write_json

SKIP_EXE = ("unins", "setup", "redist", "vc_redist", "dxsetup", "crashhandler", "crashreport", "unitycrashhandler",
            "dotnet", "directx", "physx", "oalinst", "ue4prereq", "vcredist")


def _api(path, **params):
    key = (read_json(AUTH_FILE) or {}).get("api_key", "")
    r = requests.get(API + path, params=params, timeout=30, headers={"Authorization": f"Bearer {key}"})
    r.raise_for_status()
    return r.json()


def pick(uploads, want):
    """The upload to install: the game's own build for `want`, else for the other platform."""
    def ok(u, platform):
        return u.get("type", "default") == "default" and f"p_{platform}" in (u.get("traits") or []) \
            and not u.get("demo") and "demo" not in (u.get("traits") or [])
    for platform in (want, "windows" if want == "linux" else "linux"):
        cands = [u for u in uploads if ok(u, platform)]
        if cands:
            return max(cands, key=lambda u: u.get("size") or 0), platform
    raise SystemExit("This game has no download for Linux or Windows")


def _safe_extract(archive, dest):
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            root = os.path.realpath(dest)
            for info in z.infolist():
                target = os.path.realpath(os.path.join(dest, info.filename))
                if not target.startswith(root + os.sep) and target != root:
                    continue  # never outside the game's folder
                z.extract(info, dest)
                mode = (info.external_attr >> 16) & 0o777
                if mode and not info.is_dir():
                    os.chmod(target, mode | stat.S_IRUSR)
        return True
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as t:
            t.extractall(dest, filter="data")
        return True
    return False


def _is_program(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError:
        return False
    return head == b"\x7fELF" or head[:2] == b"#!"


def find_program(folder, platform):
    """The file that starts the game, relative to folder (shallowest first, then biggest)."""
    found = []
    for base, dirs, files in os.walk(folder):
        depth = os.path.relpath(base, folder).count(os.sep)
        if depth > 3:
            dirs[:] = []
            continue
        for f in files:
            p = os.path.join(base, f)
            low = f.lower()
            if any(s in low for s in SKIP_EXE) or f == MANIFEST:
                continue
            if platform == "windows":
                good = low.endswith(".exe")
            else:
                library = ".so" in low or low.endswith((".py", ".dll", ".dylib"))
                good = not library and (low.endswith((".x86_64", ".x86", ".appimage", ".sh")) or _is_program(p))
            if good:
                pref = 0 if low.endswith((".x86_64", ".appimage", ".exe")) else 1
                found.append((depth, pref, -os.path.getsize(p), os.path.relpath(p, folder)))
    if not found:
        return ""
    return sorted(found)[0][3]


def main(game_id, key_id, folder, want):
    uploads = _api(f"/games/{game_id}/uploads", download_key_id=key_id).get("uploads") or []
    upload, platform = pick(uploads, want)
    os.makedirs(os.path.dirname(folder), exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.dirname(folder), prefix=".itch-") as tmp:
        name = os.path.basename(upload.get("filename") or "download")
        path = os.path.join(tmp, name)
        key = (read_json(AUTH_FILE) or {}).get("api_key", "")
        with requests.get(f"{API}/uploads/{upload['id']}/download", params={"download_key_id": key_id},
                          headers={"Authorization": f"Bearer {key}"}, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or upload.get("size") or 0)
            done, t0, last = 0, time.time(), 0.0
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    if total and now - last > 0.5:
                        last = now
                        speed = done / max(0.1, now - t0) / 1024 ** 2
                        print(f"Progress: {done * 95 / total:.1f}  + Download - {speed:.1f} MiB/s", flush=True)
        staging = os.path.join(tmp, "game")
        os.makedirs(staging)
        if not _safe_extract(path, staging):
            shutil.move(path, os.path.join(staging, name))  # a single program: an AppImage, an .exe, a script
            if platform == "linux":
                os.chmod(os.path.join(staging, name), 0o755)
        print("Progress: 97.0", flush=True)
        exe = find_program(staging, platform)
        if not exe:
            raise SystemExit("Downloaded, but no program to start was found in it")
        if platform == "linux":
            p = os.path.join(staging, exe)
            os.chmod(p, os.stat(p).st_mode | 0o755)
        write_json(os.path.join(staging, MANIFEST), {"upload": upload.get("id"), "build": upload.get("build_id"),
                                                     "platform": platform, "exe": exe, "file": name})
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        os.replace(staging, folder)
    print("Progress: 100.0", flush=True)
    print(f"Installed {platform} version: {exe}")


if __name__ == "__main__":
    try:
        main(*sys.argv[1:5])
    except SystemExit:
        raise
    except Exception as e:
        print(f"Install failed: {type(e).__name__}: {e}")
        sys.exit(1)

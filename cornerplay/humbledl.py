"""Download and install one Humble Bundle game:
python3 -m cornerplay.humbledl <machine name> <gamekey> <folder> <linux|windows>

Prints "Progress: NN.N" and the speed like the other stores' tools. The download links are
asked for fresh (they are signed and expire). What happens with the file:
- zip / tar archives are unpacked into the folder (never outside it);
- a Linux .sh installer made with MojoSetup is a zip archive inside: its data/ folder is the
  game, taken out without running anything; a makeself .sh is unpacked with --noexec;
- an AppImage or single Linux program is kept as it is;
- a Windows .exe installer runs once through Proton (its own window: click through it), and the
  game it installed inside the game's Proton prefix is found afterwards.
The program that starts the game is noted in <folder>/.cornerplay-humble.json.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

from .config import write_json
from .unpack import _safe_extract, find_program
from .net import requests
from .stores.humble import MANIFEST, downloads, get

NOT_GAMES = (".deb", ".rpm", ".dmg", ".pkg", ".apk")


def pick(files, platform):
    """The file to install for a platform: the 64-bit build when there are several, archives
    before installers on Windows (no clicking through), never distro packages."""
    files = [f for f in files if not f["name"].lower().endswith(NOT_GAMES) and not f["url"].split("?")[0].lower().endswith(NOT_GAMES)]
    if not files:
        return None

    def rank(f):
        name = (f["name"] + " " + f["url"].split("?")[0]).lower()
        bits = 0 if ("64" in name and "32" not in name) else 1 if not any(x in name for x in ("32", "i386", "i686", "x86 ")) else 2
        kind = 0 if name.endswith((".zip", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2")) else 1
        return (bits, kind if platform == "windows" else 0, -f["size"])
    return sorted(files, key=rank)[0]


def _download(f, path):
    with requests.get(f["url"], stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or f["size"] or 0)
        done, t0, last = 0, time.time(), 0.0
        md5 = hashlib.md5()
        with open(path, "wb") as out:
            for chunk in r.iter_content(1 << 20):
                out.write(chunk)
                md5.update(chunk)
                done += len(chunk)
                now = time.time()
                if total and now - last > 0.5:
                    last = now
                    speed = done / max(0.1, now - t0) / 1024 ** 2
                    print(f"Progress: {done * 90 / total:.1f}  + Download - {speed:.1f} MiB/s", flush=True)
    if f["md5"] and md5.hexdigest() != f["md5"]:
        raise SystemExit("The download is damaged (its checksum does not match): try again")


def _unpack_linux(path, staging):
    name = os.path.basename(path)
    if name.lower().endswith(".sh"):
        if zipfile.is_zipfile(path):        # MojoSetup: a shell stub with a zip after it
            raw = os.path.join(staging, ".mojo")
            os.makedirs(raw)
            _safe_extract(path, raw)
            data = next((os.path.join(raw, d) for d in ("data/noarch", "data") if os.path.isdir(os.path.join(raw, d))), raw)
            for entry in os.listdir(data):
                shutil.move(os.path.join(data, entry), os.path.join(staging, entry))
            shutil.rmtree(raw, ignore_errors=True)
            return
        target = os.path.join(staging, "game")
        r = subprocess.run(["sh", path, "--noexec", "--target", target], capture_output=True, timeout=1800)
        if r.returncode == 0 and os.path.isdir(target):
            return                          # makeself
        shutil.move(path, os.path.join(staging, name))  # something else: keep it, it starts the game
        os.chmod(os.path.join(staging, name), 0o755)
        return
    if not _safe_extract(path, staging):
        shutil.move(path, os.path.join(staging, name))  # an AppImage or a single program
        os.chmod(os.path.join(staging, name), 0o755)


def _run_windows_installer(path, machine):
    """Run a Windows installer through Proton in the game's prefix; returns the game's program
    (an absolute path inside the prefix) or "" when none was found."""
    from .runner import wine_env, wrapper_argv
    env = dict(os.environ, **wine_env("humble", machine))
    drive_c = os.path.join(env["WINEPREFIX"], "drive_c")
    before = time.time() - 5
    print("Progress: 92.0  (the game's installer is open: click through it)", flush=True)
    subprocess.run([*wrapper_argv(gamescope=False), path], env=env, cwd=os.path.dirname(path), timeout=6 * 3600)
    places = []
    for root in ("Program Files", "Program Files (x86)", "GOG Games", "Games", "Humble"):
        base = os.path.join(drive_c, root)
        if os.path.isdir(base):
            places += [os.path.join(base, d) for d in os.listdir(base)
                       if d not in ("Common Files", "Internet Explorer", "Windows Media Player", "Windows NT", "WindowsPowerShell")]
    new = sorted((p for p in places if os.path.isdir(p) and os.path.getmtime(p) >= before), key=os.path.getmtime, reverse=True)
    for folder in new:
        exe = find_program(folder, "windows")
        if exe:
            return os.path.join(folder, exe)
    return ""


def main(machine, gamekey, folder, want):
    order = get(f"/order/{gamekey}")
    sub = next((s for s in order.get("subproducts") or [] if s.get("machine_name") == machine), None)
    if not sub:
        raise SystemExit("This game is no longer in that Humble order")
    files = downloads(sub)
    platform, f = None, None
    for p in (want, "windows" if want == "linux" else "linux"):
        f = pick(files.get(p) or [], p)
        if f:
            platform = p
            break
    if not f:
        raise SystemExit("This game has no download for Linux or Windows")
    os.makedirs(os.path.dirname(folder), exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.dirname(folder), prefix=".humble-") as tmp:
        name = os.path.basename(f["url"].split("?")[0]) or f["name"] or "download"
        path = os.path.join(tmp, name)
        _download(f, path)
        staging = os.path.join(tmp, "game")
        os.makedirs(staging)
        exe = ""
        if platform == "linux":
            _unpack_linux(path, staging)
            print("Progress: 96.0", flush=True)
            exe = find_program(staging, "linux")
            if exe:
                p = os.path.join(staging, exe)
                os.chmod(p, os.stat(p).st_mode | 0o755)
        elif _safe_extract(path, staging):
            print("Progress: 96.0", flush=True)
            exe = find_program(staging, "windows")
        else:                                   # a Windows installer
            exe = _run_windows_installer(path, machine)
        if not exe:
            raise SystemExit("Downloaded, but no program to start the game was found in it")
        write_json(os.path.join(staging, MANIFEST), {"platform": platform, "exe": exe, "file": name,
                                                     "md5": f["md5"], "gamekey": gamekey})
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

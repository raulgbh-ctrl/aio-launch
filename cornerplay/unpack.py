"""Unpacking a downloaded game and finding the program that starts it (used by humbledl).

Archives are unpacked into the game's folder and never outside it.
"""
import os
import stat
import tarfile
import zipfile

SKIP_EXE = ("unins", "setup", "redist", "vc_redist", "dxsetup", "crashhandler", "crashreport", "unitycrashhandler",
            "dotnet", "directx", "physx", "oalinst", "ue4prereq", "vcredist")


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
            if any(s in low for s in SKIP_EXE) or f.startswith(".cornerplay-"):
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

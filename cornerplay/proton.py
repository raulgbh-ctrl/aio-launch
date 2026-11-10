"""Proton builds: list what is installed (GE, Steam's own, others) and fetch the newest GE-Proton."""
import hashlib
import os
import shutil
import tarfile
import tempfile

from .net import requests

from .config import HOME

GE_API = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"
# Where GE builds go: Steam and umu-launcher both look here.
TOOLS_DIR = HOME / ".local/share/Steam/compatibilitytools.d"
PROTON_EXPERIMENTAL_APPID = "1493710"


def latest_ge():
    """(tag, tarball url, checksum url) of the newest GE-Proton for this CPU."""
    r = requests.get(GE_API, timeout=20, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    data = r.json()
    arch = "aarch64" if os.uname().machine in ("aarch64", "arm64") else "x86_64"
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    tar = next((u for n, u in assets.items() if n.endswith(f"{arch}.tar.gz")), None) \
        or next((u for n, u in assets.items() if n.endswith(".tar.gz")), None)
    if not tar:
        raise RuntimeError("The latest GE-Proton release has no download for this PC")
    sha = next((u for n, u in assets.items() if n.endswith(".sha512sum") and arch in n), None)
    return data["tag_name"], tar, sha


def installed_ge():
    """Names of GE-Proton folders already in compatibilitytools.d, newest first."""
    try:
        names = [n for n in os.listdir(TOOLS_DIR) if n.startswith("GE-Proton")
                 and os.path.isfile(TOOLS_DIR / n / "proton")]
    except OSError:
        return []

    def version(name):
        digits = [int(x) for x in name.replace("GE-Proton", "").split("-")[0:2] if x.isdigit()]
        return digits or [0]
    return sorted(names, key=version, reverse=True)


def download_ge(progress=None):
    """Download and unpack the newest GE-Proton. progress(percent) is called as it goes.
    Returns the installed folder name (unchanged if it was already there)."""
    tag, url, sha_url = latest_ge()
    have = [n for n in installed_ge() if n == tag or n.startswith(tag + "-")]
    if have:
        return have[0], False
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    expected = None
    if sha_url:
        expected = requests.get(sha_url, timeout=20).text.split()[0].lower()
    with tempfile.TemporaryDirectory(dir=TOOLS_DIR, prefix=".download-") as tmp:
        archive = os.path.join(tmp, "ge.tar.gz")
        digest = hashlib.sha512()
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0)) or None
            done = 0
            with open(archive, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress and total:
                        progress(min(99.0, done * 100 / total))
        if expected and digest.hexdigest() != expected:
            raise RuntimeError("The GE-Proton download was damaged (checksum mismatch); try again")
        with tarfile.open(archive) as tar:
            top = {m.name.split("/", 1)[0] for m in tar.getmembers()}
            if len(top) != 1:
                raise RuntimeError("Unexpected GE-Proton archive layout")
            tar.extractall(tmp, filter="data")
        name = top.pop()
        target = TOOLS_DIR / name
        if target.exists():
            shutil.rmtree(target)
        os.replace(os.path.join(tmp, name), target)
    if progress:
        progress(100.0)
    return name, True

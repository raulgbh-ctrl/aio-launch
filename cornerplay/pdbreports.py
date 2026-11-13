"""What players with a PC like yours did to run a game (a game's page, under "Will it run").

ProtonDB publishes every report as an open data dump (github.com/bdefore/protondb-data, ODbL),
one archive a month (~70 MB). Once a month, in the background and not on a metered connection,
Cornerplay reads the newest one as it downloads and keeps only the reports for games in your
library (~/.cache/cornerplay/protondb_reports.json): the reporter's graphics card, the Proton
they used, their launch options and their notes. Nothing about you is sent anywhere.

On a game's page, the reports from graphics cards closest to yours (same card first, then the
same maker and similar power, the newest first) show what worked, with "Use these settings":
their Proton (when this PC has that build, or GE-Proton for GE builds), their environment
variables and their launch arguments, into the game's Options. Steam games get the launch
options to paste into Steam's Properties.
"""
import codecs
import json
import re
import shlex
import tarfile
import tempfile
import time

from . import compat
from .config import CACHE_DIR, read_json, write_json
from .net import requests

FILE = CACHE_DIR / "protondb_reports.json"
INDEX = "https://api.github.com/repos/bdefore/protondb-data/contents/reports"
RAW = "https://raw.githubusercontent.com/bdefore/protondb-data/master/reports/"
MAX_AGE = 30 * 86400
KEEP = 30  # newest reports kept per game, plus up to MATCHES from graphics cards like this PC's
MATCHES = 40
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()


def newest_dump():
    """The name of the newest monthly archive ("reports_nov1_2026.tar.gz")."""
    files = requests.get(INDEX, timeout=30, headers={"Accept": "application/vnd.github+json"}).json()

    def when(name):
        m = re.match(r"reports_([a-z]+)(\d+)_(\d+)\.tar\.gz$", name)
        return (int(m[3]), MONTHS.index(m[1]), int(m[2])) if m and m[1] in MONTHS else (0, 0, 0)
    names = [f.get("name", "") for f in files if isinstance(f, dict)]
    best = max(names, key=when, default="")
    return best if when(best) > (0, 0, 0) else ""


def _text(v, n):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def compact(r):
    """The parts of one report worth keeping."""
    resp = r.get("responses") or {}
    sysinfo = r.get("systemInfo") or {}
    notes = resp.get("notes") if isinstance(resp.get("notes"), dict) else {}
    note = resp.get("concludingNotes") or notes.get("verdict") or notes.get("customizationsUsed") \
        or notes.get("concludingNotes") or ""
    flags = resp.get("launchFlagsUsed") if isinstance(resp.get("launchFlagsUsed"), dict) else {}
    gpu = re.sub(r"\s*\(.*$", "", str(sysinfo.get("gpu") or ""))  # "AMD Radeon RX 570 (radeonsi, polaris10, ...)"
    return {"t": int(r.get("timestamp") or 0), "gpu": _text(gpu, 80), "driver": _text(sysinfo.get("gpuDriver"), 40),
            "works": resp.get("verdict") == "yes", "perf": resp.get("performanceFaults") == "no",
            "proton": _text(resp.get("customProtonVersion") or resp.get("protonVersion") or "", 40),
            "variant": _text(resp.get("variant"), 20), "options": _text(resp.get("launchOptions"), 300),
            "flags": [k for k, v in flags.items() if v][:8], "note": _text(note, 320)}


def _objects(stream):
    """Each report in the archive's JSON array, decoded as it streams in (the file is ~500 MB)."""
    dec = json.JSONDecoder()
    text = codecs.getincrementaldecoder("utf-8")("replace")
    buf, pos, started = "", 0, False
    while True:
        chunk = text.decode(stream.read(1 << 20), final=False)
        buf = buf[pos:] + chunk
        pos = 0
        if not started:
            i = buf.find("[")
            if i < 0:
                if not chunk:
                    return
                continue
            buf, started = buf[i + 1:], True
        while True:
            while pos < len(buf) and buf[pos] in " \n\r\t,":
                pos += 1
            if pos >= len(buf) or buf[pos] == "]":
                break
            try:
                obj, end = dec.raw_decode(buf, pos)
            except ValueError:
                break  # the rest of this object is in the next chunk
            pos = end
            if isinstance(obj, dict):
                yield obj
        if not chunk:
            return


def build(archive, appids, my_gpu=""):
    """{appid: [report, ...newest first]} for the wanted apps, from a downloaded archive: the
    newest few, and the working ones from graphics cards like my_gpu."""
    want = {str(a) for a in appids}
    out = {}
    with tarfile.open(archive, "r|gz") as tf:
        for member in tf:
            if not member.name.endswith(".json"):
                continue
            for r in _objects(tf.extractfile(member)):
                app = str(((r.get("app") or {}).get("steam") or {}).get("appId") or "")
                if app in want:
                    out.setdefault(app, []).append(compact(r))
    me = _me(my_gpu)
    for app, rows in out.items():
        rows.sort(key=lambda x: -x["t"])
        like = [r for r in rows[KEEP:] if r["works"] and _match(r, me)][:MATCHES]
        out[app] = rows[:KEEP] + like
    return out


def refresh(appids, force=False):
    """Blocking (worker thread). Fetch the newest dump when the kept one is a month old (or games
    were added since). Returns True when the reports changed."""
    data = read_json(FILE, {}) or {}
    have = set(data.get("asked") or [])
    wanted = {str(a) for a in appids if a}
    if not force and time.time() - data.get("t", 0) < MAX_AGE and wanted <= have:
        return False
    name = newest_dump()
    if not name:
        return False
    with tempfile.NamedTemporaryFile(dir=CACHE_DIR, prefix=".protondb-", suffix=".tar.gz") as tmp:
        with requests.get(RAW + name, stream=True, timeout=60) as r:
            r.raise_for_status()
            for chunk in r.iter_content(1 << 20):
                tmp.write(chunk)
        tmp.flush()
        apps = build(tmp.name, wanted, compat.system().get("gpu", ""))
    write_json(FILE, {"t": time.time(), "dump": name, "asked": sorted(wanted), "apps": apps})
    return True


def _norm_gpu(name):
    return compat._norm(name or "")


def _vendor(name):
    n = (name or "").lower()
    return "nvidia" if any(x in n for x in ("nvidia", "geforce", "rtx", "gtx", "quadro")) \
        else "amd" if any(x in n for x in ("amd", "radeon", "rx ", "vega", "navi")) \
        else "intel" if any(x in n for x in ("intel", "arc ", "uhd", "iris")) else ""


def _me(gpu):
    return (_norm_gpu(gpu), compat.gpu_score(gpu or ""), _vendor(gpu))


def _match(r, me):
    """"same" (this graphics card), "similar" (same maker, about as strong) or ""."""
    mine, my_score, my_vendor = me
    if not r.get("gpu"):
        return ""
    if mine and _norm_gpu(r["gpu"]) == mine:
        return "same"
    theirs = compat.gpu_score(r["gpu"])
    if my_vendor and _vendor(r["gpu"]) == my_vendor and my_score and theirs and 0.7 <= theirs / my_score <= 1.45:
        return "similar"
    return ""


def similar(appid, my_gpu, limit=3):
    """The reports from graphics cards most like this PC's that got the game working."""
    rows = ((read_json(FILE, {}) or {}).get("apps") or {}).get(str(appid)) or []
    me = _me(my_gpu)
    scored, seen = [], set()
    for r in rows:
        m = _match(r, me) if r.get("works") else ""
        if not m or (r["gpu"], r.get("options"), r.get("proton")) in seen:
            continue
        seen.add((r["gpu"], r.get("options"), r.get("proton")))
        has_tips = bool(r.get("options") or r.get("proton"))
        scored.append((m == "same", has_tips, bool(r.get("perf")), r["t"], dict(r, match=m)))
    scored.sort(key=lambda x: x[:4], reverse=True)
    return [x[4] for x in scored[:limit]]


def settings_from(report):
    """{"env": "K=V ...", "args": "...", "proton": name} from a report's launch options and Proton."""
    opts = report.get("options") or ""
    env, args = [], []
    try:
        words = shlex.split(opts)
    except ValueError:
        words = opts.split()
    side = env if "%command%" in opts else None
    for w in words:
        if w == "%command%":
            side = args
            continue
        if side is env and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
            env.append(w)
        elif side is args:
            args.append(w)
        elif side is None and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
            env.append(w)  # options written without %command%: keep the variables
    pre = opts.split("%command%")[0].lower() if "%command%" in opts else ""
    proton = report.get("proton") or ("GE-Proton" if report.get("variant") == "ge" else "")
    return {"env": " ".join(env), "args": " ".join(shlex.quote(a) for a in args), "proton": proton, "raw": opts,
            "gamemode": "gamemoderun" in pre, "mangohud": "mangohud" in pre}

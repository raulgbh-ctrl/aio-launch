"""Will it run on this PC? A game's system requirements (from Steam's store) against this PC,
plus what players report about Linux (ProtonDB) and anti-cheat (AreWeAntiCheatYet).

The comparison is a rough guide, not a benchmark: graphics cards are placed on one relative
scale (GTX 1060 = 100) and processors on a coarser one; RAM, video memory and disk space are
compared as numbers. Anything that cannot be read is left out rather than guessed.
"""
import glob
import os
import re
import shutil
import subprocess
import time

from .config import CACHE_DIR, read_json, settings, write_json
from .net import requests

REQ_CACHE = CACHE_DIR / "requirements.json"
AWACY_CACHE = CACHE_DIR / "anticheat.json"
AWACY_URL = "https://raw.githubusercontent.com/AreWeAntiCheatYet/AreWeAntiCheatYet/master/games.json"

# Relative graphics performance, GTX 1060 6GB = 100 (rough averages from public benchmarks).
GPUS = {
    # NVIDIA
    "gt 710": 8, "gt 730": 12, "gt 1030": 28, "gtx 650": 20, "gtx 660": 35, "gtx 670": 45, "gtx 680": 50,
    "gtx 750": 30, "gtx 750 ti": 35, "gtx 760": 45, "gtx 770": 55, "gtx 780": 65, "gtx 780 ti": 75,
    "gtx 950": 45, "gtx 960": 55, "gtx 970": 85, "gtx 980": 100, "gtx 980 ti": 130,
    "gtx 1050": 45, "gtx 1050 ti": 55, "gtx 1060": 100, "gtx 1070": 135, "gtx 1070 ti": 150, "gtx 1080": 165,
    "gtx 1080 ti": 215, "gtx 1650": 70, "gtx 1650 super": 90, "gtx 1660": 110, "gtx 1660 super": 125,
    "gtx 1660 ti": 125, "rtx 2060": 140, "rtx 2060 super": 165, "rtx 2070": 175, "rtx 2070 super": 195,
    "rtx 2080": 210, "rtx 2080 super": 220, "rtx 2080 ti": 265, "rtx 3050": 120, "rtx 3060": 170,
    "rtx 3060 ti": 215, "rtx 3070": 245, "rtx 3070 ti": 260, "rtx 3080": 310, "rtx 3080 ti": 345,
    "rtx 3090": 355, "rtx 3090 ti": 385, "rtx 4060": 200, "rtx 4060 ti": 235, "rtx 4070": 300,
    "rtx 4070 super": 335, "rtx 4070 ti": 360, "rtx 4070 ti super": 385, "rtx 4080": 430, "rtx 4080 super": 440,
    "rtx 4090": 550, "rtx 5060": 240, "rtx 5060 ti": 270, "rtx 5070": 360, "rtx 5070 ti": 440, "rtx 5080": 480,
    "rtx 5090": 650,
    # AMD
    "hd 7750": 25, "hd 7770": 30, "hd 7850": 45, "hd 7870": 52, "hd 7950": 60, "hd 7970": 70,
    "r7 260x": 35, "r7 370": 45, "r9 270x": 52, "r9 280x": 70, "r9 290": 85, "r9 290x": 90, "r9 380": 65,
    "r9 390": 90, "r9 fury": 115, "rx 460": 40, "rx 470": 80, "rx 480": 90, "rx 550": 25, "rx 560": 42,
    "rx 570": 82, "rx 580": 92, "rx 590": 100, "vega 56": 125, "vega 64": 140, "radeon vii": 165,
    "rx 5500 xt": 85, "rx 5600 xt": 130, "rx 5700": 150, "rx 5700 xt": 165, "rx 6400": 60, "rx 6500 xt": 70,
    "rx 6600": 155, "rx 6600 xt": 175, "rx 6650 xt": 185, "rx 6700": 200, "rx 6700 xt": 220, "rx 6750 xt": 235,
    "rx 6800": 280, "rx 6800 xt": 320, "rx 6900 xt": 345, "rx 6950 xt": 365, "rx 7600": 190, "rx 7600 xt": 200,
    "rx 7700 xt": 280, "rx 7800 xt": 330, "rx 7900 gre": 360, "rx 7900 xt": 420, "rx 7900 xtx": 480,
    "rx 9060 xt": 270, "rx 9070": 420, "rx 9070 xt": 470,
    # integrated and handheld
    "vangogh": 40, "custom gpu 0405": 40, "steam deck": 40, "radeon 680m": 55, "radeon 760m": 55,
    "radeon 780m": 65, "radeon 880m": 70, "radeon 890m": 80, "radeon 8060s": 160, "vega 8": 22, "vega 11": 28,
    "uhd 620": 10, "uhd 630": 12, "uhd": 10, "hd 4000": 6, "hd 520": 9, "hd 620": 10, "iris xe": 25,
    "iris plus": 18, "arc a380": 70, "arc a580": 135, "arc a750": 150, "arc a770": 165, "arc b570": 170,
    "arc b580": 190,
    # laptop and Mac chips, and the chip code names lspci often shows instead of a model
    "pro 5300m": 70, "pro 5500m": 80, "pro 5600m": 120, "rx 5500m": 75, "rx 5600m": 120, "rx 5700m": 135,
    "rx 6600m": 140, "rx 6700m": 170, "rx 6800m": 200, "rx 7600m": 160, "pro 560x": 45, "pro 555x": 40,
    "navi 10": 150, "navi 14": 70, "navi 21": 300, "navi 22": 210, "navi 23": 155, "navi 24": 60,
    "navi 31": 450, "navi 32": 320, "navi 33": 185, "navi 44": 260, "navi 48": 440, "polaris 10": 90,
    "ellesmere": 90, "baffin": 40, "lexa": 25, "vega 10": 125, "cezanne": 25, "renoir": 25, "rembrandt": 55,
    "phoenix": 65, "strix point": 80,
}


def _norm(text):
    t = (text or "").lower()
    t = re.sub(r"\(tm\)|\(r\)|™|®|nvidia|geforce|amd|radeon(?! (vii|\d{3}m|8060s))|intel|graphics card|graphics|series", " ", t)
    t = re.sub(r"(\d)(ti|xt|xtx|gre|super)\b", r"\1 \2", t)    # 1660ti -> 1660 ti
    t = re.sub(r"\b(rx|gtx|rtx|gt|r9|r7|hd)\s*(\d)", r"\1 \2", t)
    return re.sub(r"\s+", " ", t)


def gpu_score(name):
    """Relative performance of a graphics card named in free text (the best match), or 0.
    A laptop version of a desktop card ("Laptop GPU", "Max-Q", "Mobile") counts about 80 %."""
    t = " " + _norm(name) + " "
    best = ""
    for k in GPUS:
        if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t) and len(k) > len(best):
            best = k
    score = GPUS.get(best, 0)
    if score and best.split()[0] in ("gtx", "rtx", "rx") and re.search(r"laptop|max-q|mobile", t):
        score = round(score * 0.8)
    return score


def gpus_in(text):
    """Every graphics card a requirement line names ("GTX 1060 / RX 580"): their scores."""
    out = []
    for part in re.split(r"\bor\b|/|,|\|", text or "", flags=re.I):
        s = gpu_score(part)
        if s:
            out.append(s)
    return out


def cpu_score(name):
    """A coarse processor score from its model name (Core i5-4460, Ryzen 5 3600, ...), or 0."""
    t = (name or "").lower()
    m = re.search(r"\bi([3579])[- ]?(\d{4,5})", t)
    if m:
        model = m.group(2)
        gen = int(model[:2]) if len(model) == 5 else int(model[0])
        return {"3": 40, "5": 55, "7": 65, "9": 75}[m.group(1)] + gen * 7
    m = re.search(r"core\s*ultra\s*([579])", t)
    if m:
        return {"5": 150, "7": 165, "9": 180}[m.group(1)]
    m = re.search(r"ryzen\s*([3579])\s*(?:pro\s*)?(\d)(\d{3})", t)
    if m:
        return {"3": 45, "5": 60, "7": 70, "9": 80}[m.group(1)] + int(m.group(2)) * 10
    if re.search(r"custom apu 0405|steam deck", t):
        return 85
    m = re.search(r"\bfx[- ]?(\d)(\d{3})", t)
    if m:
        return 25 + int(m.group(1)) * 3
    if "core 2" in t or "phenom" in t or "athlon" in t or "pentium" in t or "celeron" in t:
        return 20
    return 0


def _num(pattern, text):
    m = re.search(pattern, text or "", re.I)
    if not m:
        return 0.0
    v = float(m.group(1).replace(",", "."))
    return v / 1024 if (m.group(2) or "").lower().startswith("m") else v


def tidy(text):
    """'NVIDIA GEFORCE GTX 1070 8 GB' -> 'NVIDIA GeForce GTX 1070 8 GB' (Steam's shouting, softened)."""
    letters = [w for w in (text or "").split() if any(c.isalpha() for c in w)]
    if not letters or sum(w == w.upper() for w in letters) / len(letters) < 0.7:
        return text
    keep = {"NVIDIA", "AMD", "GTX", "RTX", "RX", "GT", "HD", "XT", "XTX", "GB", "MB", "GHZ", "CPU", "GPU", "OR", "VRAM", "APU"}
    special = {"GEFORCE": "GeForce", "RADEON": "Radeon", "GHZ": "GHz", "OR": "or", "RYZEN": "Ryzen", "INTEL": "Intel"}
    out = []
    for w in text.split(" "):
        core = w.strip(",/()")
        if core in special:
            out.append(w.replace(core, special[core]))
        elif core in keep or any(c.isdigit() for c in core) or len(core) <= 2:
            out.append(w)
        else:
            out.append(w.capitalize())
    return re.sub(r"\bI([3579])-", r"i\1-", " ".join(out))


def parse(text):
    """One requirements block (Steam's HTML, cleaned to lines) as numbers and scores."""
    lines = {}
    for ln in re.split(r"\n|<br\s*/?>|</li>", text or "", flags=re.I):
        ln = re.sub(r"<[^>]+>", "", ln).strip()
        m = re.match(r"(Processor|CPU|Memory|Graphics|Video Card|Video|Storage|Hard Drive|Hard Disk Space|Disk Space|VRAM)\s*:\s*(.+)", ln, re.I)
        if m:
            key = m.group(1).lower()
            key = {"cpu": "processor", "video card": "graphics", "video": "graphics", "hard drive": "storage",
                   "hard disk space": "storage", "disk space": "storage"}.get(key, key)
            lines[key] = m.group(2).strip()
    gpu_line = lines.get("graphics", "")
    gpus = gpus_in(gpu_line)
    return {
        "processor": lines.get("processor", ""), "cpu": min((s for s in (cpu_score(p) for p in re.split(r"\bor\b|/|,", lines.get("processor", ""), flags=re.I)) if s), default=0),
        "graphics": gpu_line, "gpu": min(gpus) if gpus else 0,
        "vram": _num(r"(\d+(?:[.,]\d+)?)\s*(gb|mb)\s*(?:of\s*)?(?:vram|video|dedicated|gddr)", gpu_line + " " + lines.get("vram", ""))
                or min((float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*GB", gpu_line, re.I) if 1 <= float(x) <= 32), default=0.0),
        "ram": _num(r"(\d+(?:[.,]\d+)?)\s*(gb|mb)", lines.get("memory", "")),
        "storage": _num(r"(\d+(?:[.,]\d+)?)\s*(gb|mb)", lines.get("storage", "")),
    }


# --- this PC -------------------------------------------------------------------------------------
_system = None


def _run(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=8).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def system():
    """This PC: graphics card, video memory, RAM, processor (cached for the session)."""
    global _system
    if _system is not None:
        return _system
    gpu = ""
    if shutil.which("vulkaninfo"):
        names = re.findall(r"deviceName\s*=\s*(.+)", _run(["vulkaninfo", "--summary"]))
        names = [n.strip() for n in names if "llvmpipe" not in n.lower()]
        gpu = max(names, key=gpu_score, default="")
    if not gpu:
        for ln in _run(["lspci", "-mm"]).splitlines():
            if not re.search(r"VGA|3D|Display", ln):
                continue
            vendor = "AMD " if re.search(r"AMD|ATI", ln) else "NVIDIA " if "NVIDIA" in ln else "Intel " if "Intel" in ln else ""
            # The bracketed names, most specific last (the subsystem often names the exact model:
            # "MacBookPro16,1 [Radeon Pro 5300M]"); the first one lspci gives a score to wins from the end.
            names = [n for n in re.findall(r"\[([^\]]+)\]", ln) if n not in ("AMD/ATI",)]
            cand = next((vendor + n for n in reversed(names) if gpu_score(n)), "")
            if not cand:
                device = re.findall(r'"([^"]*)"', ln)
                cand = vendor + (names[0] if names else device[2] if len(device) > 2 else ln)
            if gpu_score(cand) >= gpu_score(gpu):
                gpu = cand
    vram = 0.0
    for f in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
        try:
            vram = max(vram, int(open(f).read()) / 1024 ** 3)
        except (OSError, ValueError):
            pass
    if not vram and shutil.which("nvidia-smi"):
        out = _run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"]).split()
        vram = float(out[0]) / 1024 if out and out[0].isdigit() else 0.0
    ram, cpu, threads = 0.0, "", os.cpu_count() or 0
    try:
        ram = int(re.search(r"MemTotal:\s*(\d+)", open("/proc/meminfo").read()).group(1)) / 1024 ** 2
        cpu = re.search(r"model name\s*:\s*(.+)", open("/proc/cpuinfo").read()).group(1).strip()
    except (OSError, AttributeError):
        pass
    try:
        free = shutil.disk_usage(settings.games_dir if settings.games_dir.exists() else os.path.expanduser("~")).free / 1024 ** 3
    except OSError:
        free = 0.0
    _system = {"gpu": re.sub(r"\s*\(.*?\)\s*", " ", gpu).strip(), "gpuScore": gpu_score(gpu), "vram": round(vram, 1),
               "ram": round(ram, 1), "cpu": re.sub(r"\s+", " ", cpu), "cpuScore": cpu_score(cpu) or threads * 6,
               "threads": threads, "free": round(free, 1)}
    return _system


# --- requirements and anti-cheat, cached ---------------------------------------------------------
def requirements(appid):
    """Steam's minimum and recommended PC requirements for an app, parsed; {} when unknown.
    Blocking (worker thread); cached for a month."""
    cache = read_json(REQ_CACHE, {}) or {}
    hit = cache.get(str(appid))
    if hit and time.time() - hit.get("t", 0) < 30 * 86400 and "drm" in hit:
        return hit.get("req") or {}
    req, drm = {}, ""
    try:
        r = requests.get("https://store.steampowered.com/api/appdetails", timeout=15,
                         params={"appids": appid, "l": "english", "cc": "us", "filters": "basic"})
        data = ((r.json() or {}).get(str(appid)) or {}).get("data") or {}
        pc = data.get("pc_requirements") or {}
        if isinstance(pc, dict):
            req = {k: parse(pc.get(k, "")) for k in ("minimum", "recommended") if pc.get(k)}
        drm = re.sub(r"<[^>]+>", " ", str(data.get("drm_notice") or "")).strip()[:200]
    except (requests.RequestException, ValueError):
        return hit.get("req") if hit else {}
    cache[str(appid)] = {"t": time.time(), "req": req, "drm": drm}
    write_json(REQ_CACHE, cache)
    return req


def drm_notice(appid):
    """Steam's DRM notice for an app ("Denuvo Anti-Tampering"), from the cache only (requirements()
    fills it); "" when there is none or it was never asked."""
    return ((read_json(REQ_CACHE, {}) or {}).get(str(appid)) or {}).get("drm", "")


def denuvo(appid):
    """Denuvo can take a change of Proton version for a new PC, and it allows only a few a day."""
    return "denuvo" in drm_notice(appid).lower()


def anticheat(appid):
    """AreWeAntiCheatYet's entry for a Steam app: {"status": "Running"|"Supported"|"Broken"|"Denied"|..., "anticheats": [...]}, or {}."""
    data = read_json(AWACY_CACHE, {}) or {}
    if time.time() - data.get("t", 0) > 7 * 86400:
        try:
            games = requests.get(AWACY_URL, timeout=20).json()
            by_app = {}
            for g in games if isinstance(games, list) else []:
                sid = str(((g.get("storeIds") or {}).get("steam")) or "")
                if sid:
                    by_app[sid] = {"status": g.get("status", ""), "anticheats": g.get("anticheats") or []}
            data = {"t": time.time(), "apps": by_app}
            write_json(AWACY_CACHE, data)
        except (requests.RequestException, ValueError):
            pass
    return (data.get("apps") or {}).get(str(appid)) or {}


# --- the verdict ---------------------------------------------------------------------------------
RANK = {"great": 3, "ok": 2, "borderline": 1, "low": 0}


def _rate(have, need_min, need_rec, slack=0.75):
    if not have or not need_min:
        return ""
    if need_rec and have >= need_rec:
        return "great"
    if have >= need_min:
        return "ok"
    return "borderline" if have >= need_min * slack else "low"


def verdict(req, me, protondb="", ac=None, size_gb=0.0, installed=False):
    """{"level": "great"|"ok"|"borderline"|"low"|"unknown"|"no", "rows": [...], "linux": [...]}."""
    mn, rec = req.get("minimum") or {}, req.get("recommended") or {}
    rows = []

    def row(part, have_text, have, need_min, need_rec, need_text, slack=0.75):
        level = _rate(have, need_min, need_rec, slack)
        if level:
            rows.append({"part": part, "have": have_text, "needs": need_text, "level": level})

    row("Graphics", me.get("gpu") or "", me.get("gpuScore", 0), mn.get("gpu", 0), rec.get("gpu", 0),
        tidy(rec.get("graphics") or mn.get("graphics") or "")[:90])
    row("Video memory", f"{me.get('vram', 0):g} GB", me.get("vram", 0), mn.get("vram", 0), rec.get("vram", 0),
        f"{round(rec.get('vram') or mn.get('vram') or 0, 1):g} GB", slack=0.6)
    row("Processor", me.get("cpu") or "", me.get("cpuScore", 0), mn.get("cpu", 0), rec.get("cpu", 0),
        tidy(rec.get("processor") or mn.get("processor") or "")[:90])
    row("Memory", f"{me.get('ram', 0):g} GB", me.get("ram", 0) + 0.6, mn.get("ram", 0), rec.get("ram", 0),
        f"{round(rec.get('ram') or mn.get('ram') or 0, 1):g} GB")
    need_disk = size_gb or mn.get("storage", 0)
    if need_disk and not installed:
        rows.append({"part": "Free space", "have": f"{me.get('free', 0):g} GB", "needs": f"{max(0.1, round(need_disk, 1)):g} GB",
                     "level": "ok" if me.get("free", 0) >= need_disk * 1.1 else "low"})
    linux = []
    tier = (protondb or "").lower()
    if tier:
        linux.append({"text": "ProtonDB: " + tier.capitalize(), "level":
                      {"platinum": "great", "native": "great", "gold": "great", "silver": "ok", "bronze": "borderline"}.get(tier, "low")})
    ac = ac or {}
    if ac.get("status"):
        st = ac["status"]
        names = ", ".join(ac.get("anticheats") or [])
        good = st in ("Supported", "Running")
        linux.append({"text": ("Anti-cheat works on Linux" if good else "Online play is blocked on Linux by its anti-cheat"
                               if st in ("Denied", "Broken") else "Anti-cheat on Linux: " + st.lower()) + (f" ({names})" if names else ""),
                      "level": "great" if good else "low" if st in ("Denied", "Broken") else "borderline"})
    known = [r["level"] for r in rows if r["part"] != "Free space" or r["level"] == "low"]
    if tier == "borked" or (ac.get("status") in ("Denied", "Broken")):
        level = "no"
    elif not known:
        level = "unknown"
    else:
        level = min(known, key=lambda x: RANK[x])
        if level == "great" and len(rows) < 2:
            level = "ok"
    return {"level": level, "rows": rows, "linux": linux}


# --- tweaks: one-click settings that often fix things ---------------------------------------------
TWEAKS = [
    {"id": "ge", "label": "Use GE-Proton", "env": None, "proton": "GE-Proton",
     "why": "Has fixes and video codecs Valve's Proton lacks; the usual first try when a game misbehaves."},
    {"id": "nvapi", "label": "NVIDIA DLSS and Reflex", "env": {"PROTON_ENABLE_NVAPI": "1"},
     "why": "Lets games see your NVIDIA card's DLSS and Reflex (NVIDIA only)."},
    {"id": "wined3d", "label": "Old DirectX through OpenGL", "env": {"PROTON_USE_WINED3D": "1"},
     "why": "For old DirectX 9 games that crash or draw wrong with the default (DXVK)."},
    {"id": "nosync", "label": "Turn off fsync and esync", "env": {"PROTON_NO_FSYNC": "1", "PROTON_NO_ESYNC": "1"},
     "why": "Helps some games that hang, stutter or crash at random."},
    {"id": "laa", "label": "More memory for 32-bit games", "env": {"PROTON_FORCE_LARGE_ADDRESS_AWARE": "1"},
     "why": "Old 32-bit games that run out of memory (crashes after a while, often with mods)."},
    {"id": "hidenv", "label": "Hide the NVIDIA card from the game", "env": {"PROTON_HIDE_NVIDIA_GPU": "1"},
     "why": "A few games crash on NVIDIA-specific paths; this makes them treat the card as generic."},
]


def parse_env(text):
    out = {}
    for part in (text or "").split():
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


def env_string(env):
    return " ".join(f"{k}={v}" for k, v in env.items())


def tweak_on(t, opts):
    if t.get("proton"):
        return (opts.get("proton") or "").startswith(t["proton"])
    env = parse_env(opts.get("env", ""))
    return all(env.get(k) == v for k, v in t["env"].items())


def suggest(me, protondb="", problem="", req_level=""):
    """Tweak ids worth trying for this game on this PC, best first."""
    out = []
    tier = (protondb or "").lower()
    if tier in ("bronze", "borked", "silver") or problem:
        out.append("ge")
    if "nvidia" in (me.get("gpu") or "").lower() or "rtx" in (me.get("gpu") or "").lower():
        out.append("nvapi")
    if problem in ("crash", "proton"):
        out.append("nosync")
    if problem == "memory":
        out.append("laa")
    return out

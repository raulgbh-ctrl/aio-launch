"""How a game ran: MangoHud's log of each session, boiled down (Settings > Games & Proton >
Record performance, or per game under Options).

While a game started from Cornerplay runs, MangoHud logs frame times and temperatures into
~/.cache/cornerplay/perf/<game>/ (the overlay stays hidden unless you asked for it). When the
session ends the log becomes a few numbers kept in ~/.local/share/cornerplay/perf.json: average
FPS, the 1 % low, how many stutters (frames over 2.5x the usual frame time), the hottest the CPU
and GPU got, and which Proton ran it, so two Proton versions can be compared on the same game.
"""
import csv
import os
import re
import statistics
import time

from .config import CACHE_DIR, DATA_DIR, read_json, write_json

STORE = DATA_DIR / "perf.json"
KEEP = 20  # sessions kept per game


def log_dir(store, game_id):
    d = CACHE_DIR / "perf" / re.sub(r"[^A-Za-z0-9_.-]", "_", f"{store}_{game_id}")
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def hud_options(store, game_id, visible):
    """MangoHud options that log the session; the overlay is hidden unless visible."""
    out = [f"output_folder={log_dir(store, game_id)}", "autostart_log=1", "log_interval=100"]
    if not visible:
        # Fully transparent rather than no_display: MangoHud does not log while its HUD is off.
        out += ["alpha=0", "background_alpha=0"]
    return out


def summarize(path):
    """One MangoHud log (CSV) as numbers, or None when it holds too little to say anything."""
    rows, header = [], None
    try:
        with open(path, newline="", errors="replace") as f:
            for line in csv.reader(f):
                if header is None:
                    if "fps" in line and "frametime" in line:
                        header = line
                    continue
                if len(line) == len(header):
                    rows.append(dict(zip(header, line)))
    except OSError:
        return None

    def col(name):
        out = []
        for r in rows:
            try:
                out.append(float(r.get(name) or "nan"))
            except ValueError:
                pass
        return [x for x in out if x == x]
    fps, ft = col("fps"), [x for x in col("frametime") if x > 0]
    if len(fps) < 20 or len(ft) < 20:
        return None
    ft_sorted = sorted(ft)
    p99 = ft_sorted[min(len(ft_sorted) - 1, int(len(ft_sorted) * 0.99))]
    med = statistics.median(ft)
    cpu_t, gpu_t = col("cpu_temp"), col("gpu_temp")
    return {"avgFps": round(statistics.fmean(fps), 1), "low1": round(1000 / p99, 1) if p99 else 0,
            "stutters": sum(1 for x in ft if x > med * 2.5 and x > 25),
            "cpuTemp": round(max(cpu_t)) if cpu_t else 0, "gpuTemp": round(max(gpu_t)) if gpu_t else 0,
            "samples": len(fps)}


def record(key, store, game_id, started, ended, proton=""):
    """After a session: the newest log written during it, summed up and kept. Returns the entry."""
    folder = log_dir(store, game_id)
    logs = [os.path.join(folder, f) for f in os.listdir(folder)
            if f.endswith(".csv") and not f.endswith("_summary.csv")]
    logs = [p for p in logs if os.path.getmtime(p) >= started - 5]
    if not logs:
        return None
    entry = summarize(max(logs, key=os.path.getmtime))
    for p in logs:  # the numbers are kept; the raw logs would only fill the disk
        try:
            os.remove(p)
            summary = p[:-4] + "_summary.csv"
            if os.path.exists(summary):
                os.remove(summary)
        except OSError:
            pass
    if not entry:
        return None
    entry.update(t=int(ended), minutes=max(1, int((ended - started) // 60)), proton=proton or "default")
    data = read_json(STORE, {}) or {}
    data[key] = ((data.get(key) or []) + [entry])[-KEEP:]
    write_json(STORE, data)
    return entry


def history(key):
    """A game's sessions with numbers (newest first) and the average per Proton version."""
    runs = list(reversed((read_json(STORE, {}) or {}).get(key) or []))
    by_proton = {}
    for r in runs:
        by_proton.setdefault(r.get("proton") or "default", []).append(r)
    compare = [{"proton": p, "sessions": len(rs), "avgFps": round(statistics.fmean(r["avgFps"] for r in rs), 1),
                "low1": round(statistics.fmean(r["low1"] for r in rs), 1),
                "stutters": round(statistics.fmean(r["stutters"] for r in rs), 1)}
               for p, rs in by_proton.items()]
    compare.sort(key=lambda c: -c["avgFps"])
    return {"runs": runs[:8], "compare": compare if len(compare) > 1 else [], "t": time.time()}

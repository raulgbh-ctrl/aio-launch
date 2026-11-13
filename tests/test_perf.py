import os
import time

from cornerplay import perf


def _log(path, frametimes, temps=(60, 70)):
    with open(path, "w") as f:
        f.write("os,cpu,gpu,ram,kernel,driver,cpuscheduler\nArch,x,y,16,6.x,mesa,\n")
        f.write("fps,frametime,cpu_load,gpu_load,cpu_temp,gpu_temp,gpu_core_clock,gpu_mem_clock,gpu_vram_used,gpu_power,ram_used,swap_used,process_rss,elapsed\n")
        for i, ft in enumerate(frametimes):
            f.write(f"{1000 / ft:.1f},{ft},50,90,{temps[0]},{temps[1]},1800,1000,4,120,8,0,2,{i}\n")


def test_summarize_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr(perf, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(perf, "STORE", tmp_path / "perf.json")
    folder = perf.log_dir("humble", "celeste")
    start = time.time() - 600
    _log(os.path.join(folder, "Celeste_2026.csv"), [16.7] * 500 + [60.0] * 4)
    e = perf.record("humble:celeste", "humble", "celeste", start, time.time(), "GE-Proton10-1")
    assert 55 < e["avgFps"] < 61 and e["stutters"] == 4 and e["gpuTemp"] == 70 and e["low1"] < 60
    assert not os.listdir(folder)                  # raw logs removed, numbers kept
    _log(os.path.join(folder, "Celeste_2026b.csv"), [12.0] * 500)
    perf.record("humble:celeste", "humble", "celeste", start, time.time(), "proton-cachyos")
    h = perf.history("humble:celeste")
    assert len(h["runs"]) == 2 and h["compare"][0]["proton"] == "proton-cachyos"


def test_hud_options_hidden_overlay(tmp_path, monkeypatch):
    monkeypatch.setattr(perf, "CACHE_DIR", tmp_path)
    opts = perf.hud_options("gog", "1", visible=False)
    assert "autostart_log=1" in opts and "alpha=0" in opts and "no_display" not in opts  # no_display stops the log
    assert any(o.startswith("output_folder=") for o in opts)

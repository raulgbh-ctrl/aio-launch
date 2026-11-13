from cornerplay import compat


def test_gpu_scores_and_names():
    assert compat.gpus_in("NVIDIA GeForce GTX 1060 3GB / AMD Radeon RX 580 4GB") == [100, 92]
    assert compat.gpu_score("GeForce GTX1660Ti") == 125
    assert compat.gpu_score("NVIDIA GeForce RTX 3060 Laptop GPU") == 136      # laptop: ~80 %
    assert compat.gpu_score("AMD Radeon Pro 5300M") == 70
    assert compat.gpu_score("Intel UHD Graphics 630") == 12


def test_cpu_scores():
    assert compat.cpu_score("Intel Core i5-4460") < compat.cpu_score("Intel Core i5-12400") < compat.cpu_score("Intel Core i7-12700K")
    assert compat.cpu_score("AMD Ryzen 5 3600") < compat.cpu_score("AMD Ryzen 5 7600")


def test_parse_steam_requirements():
    html = ('<strong>Minimum:</strong><br><ul class="bb_ul"><li><strong>Processor:</strong> INTEL CORE I5-8400 or AMD RYZEN 3 3300X<br></li>'
            '<li><strong>Memory:</strong> 12 GB RAM<br></li><li><strong>Graphics:</strong> NVIDIA GEFORCE GTX 1060 3 GB or AMD RADEON RX 580 4 GB<br></li>'
            '<li><strong>Storage:</strong> 60 GB available space<br></li></ul>')
    r = compat.parse(html)
    assert r["ram"] == 12 and r["storage"] == 60 and r["gpu"] == 92 and r["vram"] == 3 and r["cpu"] > 0


def test_verdict_levels():
    req = {"minimum": {"gpu": 100, "ram": 8, "cpu": 60, "vram": 4}, "recommended": {"gpu": 160, "ram": 16, "cpu": 80, "vram": 6}}
    strong = {"gpu": "RTX 3070", "gpuScore": 245, "ram": 32, "cpu": "x", "cpuScore": 120, "vram": 8, "free": 500}
    weak = dict(strong, gpuScore=40, vram=2)
    assert compat.verdict(req, strong)["level"] == "great"
    assert compat.verdict(req, weak)["level"] == "low"
    assert compat.verdict(req, strong, "borked")["level"] == "no"
    assert compat.verdict(req, strong, "", {"status": "Denied", "anticheats": ["EAC"]})["level"] == "no"
    assert compat.verdict({}, strong)["level"] == "unknown"


def test_tweaks_env_roundtrip():
    t = next(x for x in compat.TWEAKS if x["id"] == "nosync")
    opts = {"env": "DXVK_HUD=fps PROTON_NO_FSYNC=1 PROTON_NO_ESYNC=1"}
    assert compat.tweak_on(t, opts)
    assert compat.parse_env(compat.env_string({"A": "1", "B": "x=y"})) == {"A": "1", "B": "x=y"}


def test_denuvo_from_steam_drm_notice(tmp_path, monkeypatch):
    from cornerplay import compat
    monkeypatch.setattr(compat, "REQ_CACHE", tmp_path / "req.json")
    compat.write_json(compat.REQ_CACHE, {"990080": {"t": 0, "req": {}, "drm": "Denuvo Anti-Tampering"},
                                          "1245620": {"t": 0, "req": {}, "drm": ""}})
    assert compat.denuvo("990080") and not compat.denuvo("1245620") and not compat.denuvo("1")

import io
import json
import tarfile

from cornerplay import pdbreports as p


def _archive(tmp_path, reports):
    data = json.dumps(reports).encode()
    path = tmp_path / "r.tar.gz"
    with tarfile.open(path, "w:gz") as tf:
        info = tarfile.TarInfo("reports_piiremoved.json")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return path


def _r(app, gpu, verdict="yes", opts="", proton="", t=1):
    return {"app": {"steam": {"appId": app}}, "timestamp": t, "systemInfo": {"gpu": gpu},
            "responses": {"verdict": verdict, "launchOptions": opts, "customProtonVersion": proton,
                          "performanceFaults": "no", "notes": {"verdict": "fine"}}}


def test_build_keeps_only_library_games_and_cleans_gpu(tmp_path):
    arc = _archive(tmp_path, [_r("1", "AMD Radeon RX 570 (radeonsi, polaris10)"), _r("2", "NVIDIA GeForce RTX 3060")])
    apps = p.build(arc, ["1"], "AMD Radeon Pro 5300M")
    assert list(apps) == ["1"] and apps["1"][0]["gpu"] == "AMD Radeon RX 570"


def test_similar_prefers_same_card_and_skips_other_makers(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "FILE", tmp_path / "idx.json")
    rows = [p.compact(x) for x in (_r("1", "NVIDIA GeForce GTX 1060", opts="X=1 %command%", t=5),
                                   _r("1", "AMD Radeon RX 570", opts="DXVK_ASYNC=1 %command% -windowed", t=3),
                                   _r("1", "AMD Radeon Pro 5300M", proton="GE-Proton9-20", t=2),
                                   _r("1", "AMD Radeon Pro 5300M", verdict="no", t=9))]
    p.write_json(p.FILE, {"apps": {"1": rows}})
    got = p.similar("1", "AMD Radeon Pro 5300M")
    assert [g["gpu"] for g in got] == ["AMD Radeon Pro 5300M", "AMD Radeon RX 570"]
    s = p.settings_from(got[1])
    assert s["env"] == "DXVK_ASYNC=1" and s["args"] == "-windowed"


def test_wrappers_become_options():
    s = p.settings_from({"options": "VKD3D_FEATURE_LEVEL=12_0 gamemoderun mangohud %command%"})
    assert s["env"] == "VKD3D_FEATURE_LEVEL=12_0" and s["gamemode"] and s["mangohud"]


def test_default_proton_is_no_setting():
    assert p.settings_from({"proton": "Default", "options": ""})["proton"] == ""

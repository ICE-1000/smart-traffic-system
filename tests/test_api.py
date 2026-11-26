import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("VISION_ENABLED", "false")  # API tests don't need the YOLO model

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402
from cameras.configuration import mask_credentials  # noqa: E402


def test_endpoints_and_websocket():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        cams = c.get("/api/cameras").json()
        assert len(cams) == 4
        cam1 = next(x for x in cams if x["id"] == "CAM-01")
        assert cam1["is_sample"] and cam1["has_regions"]  # first start: labelled sample video so the AI runs at once
        assert all(x["status"] == "not_configured" for x in cams if x["id"] != "CAM-01")

        cur = c.get("/api/traffic/current").json()
        assert cur["source"] == "demo"
        assert set(cur["approaches"]) == {"north", "south", "east", "west"}
        assert "reason" in c.get("/api/priority").json()
        assert "colours" in c.get("/api/simulation/state").json()
        assert "approaches" in c.get("/api/congestion").json()
        assert "buckets" in c.get("/api/traffic/history?minutes=5&bucket_s=5").json()

        with c.websocket_connect("/ws/live") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "snapshot" and "totals" in msg


def test_camera_validation_and_masking():
    with TestClient(app) as c:
        bad = c.post("/api/cameras", json={"id": "CAM-01", "name": "x", "approach": "north", "stream_url": "ftp://nope"})
        assert bad.status_code == 422
        ok = c.post("/api/cameras", json={"id": "CAM-01", "name": "North", "approach": "north",
                                          "stream_url": "rtsp://admin:secret@192.168.137.20:8554/live"})
        assert ok.status_code == 201
        assert "secret" not in ok.text
        cam = next(x for x in c.get("/api/cameras").json() if x["id"] == "CAM-01")
        assert cam["status"] in ("connecting", "offline")  # unreachable address: never reported online
        assert c.get("/api/cameras/CAM-01/snapshot.jpg").status_code == 404
        # echoing the masked URL back keeps the stored one
        c.post("/api/cameras", json={**cam, "stream_url": cam["stream_url"]})
        assert "***" in next(x for x in c.get("/api/cameras").json() if x["id"] == "CAM-01")["stream_url"]


def test_simulation_config_validation():
    with TestClient(app) as c:
        r = c.post("/api/simulation/config", json={"min_green_s": 30, "max_green_s": 10, "yellow_s": 3, "clearance_s": 2})
        assert r.status_code == 422
        r = c.post("/api/simulation/config", json={"min_green_s": 8, "max_green_s": 40, "yellow_s": 3, "clearance_s": 2})
        assert r.status_code == 200


def test_mask_credentials():
    assert mask_credentials("rtsp://u:p@1.2.3.4/x") == "rtsp://u:***@1.2.3.4/x"
    assert mask_credentials("rtsp://1.2.3.4/x") == "rtsp://1.2.3.4/x"


def test_one_enabled_camera_per_approach():
    with TestClient(app) as c:
        r = c.post("/api/cameras", json={"id": "CAM-09", "name": "dup", "approach": "east", "enabled": True})
        assert r.status_code == 409


def test_regions_roundtrip_and_validation():
    with TestClient(app) as c:
        assert c.get("/api/cameras/CAM-03/regions").json()["configured"] is False
        bad = c.put("/api/cameras/CAM-03/regions", json={"approach": [[0, 0], [1, 1]], "queue": [[0, 0], [1, 0], [1, 1]]})
        assert bad.status_code == 422
        body = {"approach": [[0, 0], [1, 0], [1, 1], [0, 1]], "queue": [[0, 0.5], [1, 0.5], [1, 1], [0, 1]],
                "stop_line": [[0, 0.95], [1, 0.95]], "queue_length_m": 40}
        assert c.put("/api/cameras/CAM-03/regions", json=body).status_code == 200
        got = c.get("/api/cameras/CAM-03/regions").json()
        assert got["configured"] and got["queue_length_m"] == 40


def test_data_source_modes_and_no_data():
    with TestClient(app) as c:
        assert c.post("/api/system/config", json={"data_source": "vision"}).status_code == 200
        snap = c.get("/api/traffic/current").json()
        # the runtime ticks once per second; wait for a tick in the new mode
        import time as _t
        for _ in range(30):
            snap = c.get("/api/traffic/current").json()
            if snap["data_source_mode"] == "vision" and snap["approaches"]["east"]["measurement"]["source"] == "none":
                break
            _t.sleep(0.2)
        assert snap["approaches"]["east"]["measurement"]["source"] == "none"  # no camera → no fabricated data
        assert snap["totals"]["no_data_approaches"] >= 3
        assert c.post("/api/system/config", json={"data_source": "nonsense"}).status_code == 422
        c.post("/api/system/config", json={"data_source": "auto"})


def test_vision_config_and_csv():
    with TestClient(app) as c:
        cfg = c.get("/api/vision/config").json()
        assert cfg["model"]
        r = c.post("/api/vision/config", json={**{k: cfg[k] for k in ("model", "imgsz", "device")}, "enabled": False, "conf": 0.4})
        assert r.status_code == 200 and r.json()["conf"] == 0.4
        assert c.post("/api/vision/config", json={"conf": 2}).status_code == 422
        csv = c.get("/api/traffic/history.csv?minutes=5&bucket_s=5")
        assert csv.status_code == 200 and csv.text.startswith("time_utc")


# ------------------------------------------------------------ proposal-alignment features
def test_study_sites_seeded_and_switchable():
    with TestClient(app) as c:
        sites = {s["id"]: s for s in c.get("/api/sites").json()}
        assert {"CBD-01", "CBD-02", "CBD-03"} <= set(sites)
        assert sites["CBD-01"]["name"] == "Kafue Roundabout" and sites["CBD-01"]["node_type"] == "roundabout"
        assert sites["CBD-03"]["node_type"] == "unconfirmed"
        assert c.post("/api/sites/active", json={"id": "CBD-02"}).json()["name"] == "Hybrid Roundabout"
        assert c.get("/api/traffic/current").json()["site"]["id"] in ("CBD-02", sites["CBD-02"]["id"])
        assert c.post("/api/sites/active", json={"id": "NOPE"}).status_code == 404
        assert c.post("/api/sites", json={"id": "bad id!", "name": "x", "node_type": "signalised"}).status_code == 422
        c.post("/api/sites/active", json={"id": "INT-001"})


def test_evaluation_endpoints():
    with TestClient(app) as c:
        ev = c.get("/api/evaluation").json()
        for k in ("adaptive", "fixed", "improvement_pct", "fixed_plan", "inputs"):
            assert k in ev
        assert set(ev["adaptive"]) == {"arrived", "departed", "throughput_vph", "mean_delay_s", "vehicle_hours_delay",
                                       "queued_now", "max_queue", "stop_rate", "per_approach_mean_delay_s"}
        assert c.post("/api/evaluation/config", json={"green_s": {"north": 1}}).status_code == 422
        r = c.post("/api/evaluation/config", json={"green_s": {"north": 30}, "saturation_vps": 0.55})
        assert r.status_code == 200 and r.json()["plan"]["green_s"]["north"] == 30
        assert c.get("/api/evaluation").json()["elapsed_s"] <= 2  # tuning change starts a fresh run
        snap = c.get("/api/traffic/current").json()
        assert "evaluation" in snap and "indices" in snap["approaches"]["north"]


def test_surveys_validation_and_analytics():
    import time as _t
    with TestClient(app) as c:
        r = c.post("/api/surveys/moving-car", json={"corridor": "Cairo Road", "direction": "N", "run_time": _t.time(),
                                                     "distance_km": 1, "tw_min": 3, "ta_min": 1.5, "x": 35, "y": 10,
                                                     "free_flow_kmh": 40})
        assert r.status_code == 201 and r.json()["result"]["flow_vph"] == 600.0
        assert c.post("/api/surveys/moving-car", json={"corridor": "c", "direction": "d", "run_time": _t.time(),
                                                        "distance_km": 1, "tw_min": 1, "ta_min": 1, "x": 0, "y": 0}).status_code == 422
        summary = c.get("/api/surveys/moving-car").json()["summary"]
        assert summary and summary[0]["mean_ci"] == pytest.approx(0.33, abs=0.01)
        assert c.get("/api/surveys/moving-car.csv").text.startswith("site,corridor")
        v = c.post("/api/surveys/validation", json={"camera_id": "CAM-01", "start_ts": _t.time() - 600, "end_ts": _t.time() - 1,
                                                    "manual_count": 10})
        assert v.status_code == 201 and v.json()["system_count"] == 0 and v.json()["error_pct"] == -100.0
        assert c.post("/api/surveys/validation", json={"camera_id": "CAM-01", "start_ts": 10, "end_ts": 5,
                                                       "manual_count": 1}).status_code == 422
        p = c.get("/api/analytics/periods?days=1").json()
        assert p["timezone"] in ("Africa/Lusaka", "local") and "rows" in p
        assert "approaches" in c.get("/api/analytics/forecast").json()


def test_incidents_preemption_and_indices_config():
    with TestClient(app) as c:
        inc = c.get("/api/incidents").json()
        assert {"active", "history", "config"} <= set(inc)
        assert c.post("/api/incidents/config", json={"stall_s": -1}).status_code == 422
        r = c.post("/api/simulation/preempt", json={"approach": "west", "hold_s": 10, "reason": "Ambulance"})
        assert r.status_code == 200 and r.json()["preemption"]["approach"] == "west"
        assert c.post("/api/simulation/preempt", json={"approach": "up"}).status_code == 422
        assert c.delete("/api/simulation/preempt").json()["preemption"] is None
        assert c.post("/api/indices/config", json={"free_flow_kmh": 500}).status_code == 422
        assert c.post("/api/indices/config", json={"free_flow_kmh": 45, "default_section_m": 120, "window_s": 300}).json()["free_flow_kmh"] == 45


def test_migration_upgrades_existing_phase_data(tmp_path):
    """0001 → 0002 must keep existing rows (no data loss on upgrade)."""
    import sqlite3

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    from backend.app.core.config import ROOT

    url = f"sqlite:///{tmp_path}/m.db"
    eng = create_engine(url)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "database" / "migrations"))
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001")
    con = sqlite3.connect(f"{tmp_path}/m.db")
    con.execute("insert into intersections values ('X','Old','Lusaka')")
    con.commit()
    con.close()
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    con = sqlite3.connect(f"{tmp_path}/m.db")
    assert con.execute("select id, node_type from intersections").fetchall() == [("X", "signalised")]
    assert {r[0] for r in con.execute("select name from sqlite_master where type='table'")} >= {
        "incidents", "evaluation_snapshots", "survey_runs", "validation_counts"}


def test_ai_selftest_endpoints():
    with TestClient(app) as c:
        st = c.get("/api/vision/selftest").json()
        assert "status" in st
        assert c.get("/api/system/config").status_code == 200


def test_fallback_tracker_used_when_bytetrack_unavailable():
    """If ByteTrack cannot run (e.g. 'lap' missing on Windows), detection continues with the IoU tracker."""
    pytest.importorskip("ultralytics")
    import cv2

    from backend.app.core.config import ROOT
    from vision.detection.detector import YoloTracker

    trk = YoloTracker("yolo26n.pt")

    def broken(*a, **k):
        raise ModuleNotFoundError("No module named 'lap'")

    trk.model.track = broken
    img = cv2.imread(str(ROOT / "samples" / "test_image.jpg"))
    for _ in range(3):
        dets = trk.track(img)
    assert trk.mode == "iou" and "lap" in trk.fallback_reason
    assert any(d.track_id is not None for d in dets)

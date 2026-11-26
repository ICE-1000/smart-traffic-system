"""Camera receiver / manager behaviour with real OpenCV, no phones needed."""
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from cameras.configuration import CameraConfig, file_url_to_path, is_sample, mask_credentials
from cameras.manager import CameraManager


@pytest.fixture(scope="module")
def tiny_video(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("vid") / "tiny.mp4"
    vw = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 90))
    for i in range(20):
        img = np.full((90, 160, 3), i * 10, np.uint8)
        vw.write(img)
    vw.release()
    return p


def cam(cid, url, approach="north"):
    return {"id": cid, "name": cid, "approach": approach, "stream_url": url, "enabled": True,
            "processing_width": 160, "processing_fps": 5.0}


def wait_for(pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.1)
    return False


def test_url_helpers():
    assert is_sample("file://samples/a.mp4") and not is_sample("rtsp://x/y")
    assert file_url_to_path("file:///C:/videos/a.mp4") == "C:/videos/a.mp4"
    assert mask_credentials("rtsp://u:p@1.2.3.4/x") == "rtsp://u:***@1.2.3.4/x"
    with pytest.raises(Exception):
        CameraConfig(id="A", name="a", approach="north", stream_url="ftp://x")


def test_sample_file_goes_online_and_loops(tiny_video):
    m = CameraManager()
    try:
        m.sync([cam("S1", f"file://{tiny_video}")])
        assert wait_for(lambda: m.is_online("S1"))
        st = m.statuses()["S1"]
        assert st["is_sample"] and st["detail"].startswith("Sample")
        seq1 = m.receiver("S1").latest().seq
        time.sleep(3)  # 20 frames at 10 fps = 2 s: must have looped
        assert m.receiver("S1").latest().seq > seq1
    finally:
        m.stop_all()


def test_bad_camera_does_not_affect_good_one(tiny_video):
    m = CameraManager()
    try:
        m.sync([cam("GOOD", f"file://{tiny_video}"), cam("BAD", "rtsp://127.0.0.1:9/none", "south")])
        assert wait_for(lambda: m.is_online("GOOD"))
        assert wait_for(lambda: m.statuses()["BAD"]["status"] == "offline", 20)
        assert m.is_online("GOOD")
        assert "retrying" in m.statuses()["BAD"]["detail"]
    finally:
        m.stop_all()


def test_disable_and_unconfigure_stop_receivers(tiny_video):
    m = CameraManager()
    try:
        c = cam("S1", f"file://{tiny_video}")
        m.sync([c])
        assert wait_for(lambda: m.is_online("S1"))
        m.sync([{**c, "enabled": False}])
        assert m.receiver("S1") is None
        assert m.statuses()["S1"]["status"] == "disabled"
        m.sync([{**c, "stream_url": ""}])
        assert m.statuses()["S1"]["status"] == "not_configured"
    finally:
        m.stop_all()


def test_stale_stream_reported_offline(tiny_video):
    m = CameraManager(start_receivers=False)
    m.sync([cam("S1", f"file://{tiny_video}")])
    m.report_frame("S1", 10.0)
    assert m.is_online("S1")
    m._status["S1"].last_seen = time.time() - 30
    assert m.statuses()["S1"]["status"] == "offline"

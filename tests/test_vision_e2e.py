"""End-to-end: synthetic sample video → receiver → YOLO + ByteTrack → measurement.

Skipped automatically when Ultralytics or the weights are unavailable.
Generates the sample video if it does not exist.
"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "synthetic_approach.mp4"

ultralytics = pytest.importorskip("ultralytics")


@pytest.mark.slow
def test_sample_video_produces_vision_measurements():
    if not SAMPLE.exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_sample_video.py")], check=True, cwd=ROOT)
    from cameras.manager import CameraManager
    from vision.processing.service import VisionConfig, VisionService
    from vision.regions.config import RegionConfig

    cam = {"id": "E2E", "name": "e2e", "approach": "north", "stream_url": "file://samples/synthetic_approach.mp4",
           "enabled": True, "processing_width": 640, "processing_fps": 5.0}
    mgr = CameraManager()
    vis = VisionService(VisionConfig())
    vis.set_regions("E2E", RegionConfig(
        approach=[(0.31, 0), (0.69, 0), (0.69, 0.87), (0.31, 0.87)],
        queue=[(0.31, 0.3), (0.69, 0.3), (0.69, 0.87), (0.31, 0.87)],
        stop_line=[(0.31, 0.875), (0.69, 0.875)], queue_length_m=45))
    try:
        mgr.sync([cam])
        vis.sync([cam], mgr.receiver)
        w = vis.worker("E2E")
        seen_queue = 0
        end = time.time() + 45
        while time.time() < end:
            m = w.fresh_measurement()
            if m:
                seen_queue = max(seen_queue, m.queue_count)
                if seen_queue >= 2 and m.arrival_rate_vpm > 0:
                    break
            time.sleep(0.5)
        if w.status == "model_error":
            pytest.skip(f"model unavailable: {w.model_errors}")
        assert w.status == "detecting"
        assert seen_queue >= 2, "queued vehicles should be measured during the red phase"
        assert m.source == "vision"
    finally:
        vis.stop_all()
        mgr.stop_all()

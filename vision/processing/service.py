"""Vision service: one worker thread per online camera.

worker loop (at the camera's processing_fps):
    latest frame from the receiver → resize to processing_width
    → YOLO + ByteTrack → ApproachTracker.update → ApproachMeasurement

Workers never block the API or the runtime loop; the runtime simply reads
each worker's most recent measurement. If the model cannot load, workers
keep running (regions still drawn) and report the error.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass

import cv2

from intelligence.types import ApproachMeasurement
from vision.regions.config import RegionConfig
from vision.tracking.state import ApproachTracker, Track, TrackerSettings

log = logging.getLogger("vision.service")


@dataclass
class VisionConfig:
    enabled: bool = True
    model: str = "yolo26n.pt"
    conf: float = 0.35
    imgsz: int = 640
    device: str | None = None  # None = auto (CPU on most laptops); e.g. "intel:gpu" for OpenVINO exports


class VisionWorker(threading.Thread):
    def __init__(self, camera: dict, regions: RegionConfig, cfg: VisionConfig, receiver_getter, model_errors: dict) -> None:
        super().__init__(name=f"vision-{camera['id']}", daemon=True)
        self.camera = camera
        self.cfg = cfg
        self.receiver_getter = receiver_getter
        self.tracker = ApproachTracker(camera["approach"], regions, TrackerSettings())
        self.model_errors = model_errors
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.measurement: ApproachMeasurement | None = None
        self.measured_at = 0.0
        self.processing_fps = 0.0
        self.detection_ms = 0.0
        self.status = "starting"
        self._yolo = None
        self._next_load_attempt = 0.0
        self._times: deque[float] = deque(maxlen=20)

    def stop(self) -> None:
        self._stop.set()

    def set_regions(self, regions: RegionConfig) -> None:
        with self._lock:
            self.tracker.set_regions(regions)

    def _load_model(self) -> None:
        if self._yolo is not None or not self.cfg.enabled or time.monotonic() < self._next_load_attempt:
            return
        self._next_load_attempt = time.monotonic() + 30.0  # retry a failed load every 30 s, not continuously
        try:
            from vision.detection.detector import YoloTracker

            self.status = "loading_model"
            self._yolo = YoloTracker(self.cfg.model, self.cfg.conf, self.cfg.imgsz, self.cfg.device)
            self.model_errors.pop(self.camera["id"], None)
            self.status = "waiting_for_frames"
        except Exception as e:  # missing ultralytics / weights / bad device
            log.exception("model load failed")
            from vision.detection.selftest import hint_for

            msg = f"{type(e).__name__}: {e}"[:300]
            self.model_errors[self.camera["id"]] = f"{msg} — {hint_for(msg)}"
            self.status = "model_error"

    def run(self) -> None:
        period = 1.0 / max(0.2, float(self.camera["processing_fps"]))
        width = int(self.camera["processing_width"])
        last_seq = -1
        while not self._stop.is_set():
            t0 = time.monotonic()
            self._load_model()
            rx = self.receiver_getter(self.camera["id"])
            frame = rx.latest() if rx else None
            if frame is None or frame.seq == last_seq:
                if frame is None and self.status in ("detecting", "starting"):
                    self.status = "waiting_for_frames"
                self._stop.wait(0.05)
                continue
            last_seq = frame.seq
            img = frame.image
            if img.shape[1] > width:
                img = cv2.resize(img, (width, int(img.shape[0] * width / img.shape[1])), interpolation=cv2.INTER_AREA)
            dets = []
            if self._yolo is not None and self.cfg.enabled:
                try:
                    self._yolo.conf = self.cfg.conf
                    dets = self._yolo.track(img)
                    self.detection_ms = self._yolo.last_ms
                    self.status = "detecting"
                except Exception:
                    log.exception("inference failed")
                    self.status = "inference_error"
            elif not self.cfg.enabled:
                self.status = "disabled"
            now = time.time()
            with self._lock:
                self.tracker.update(dets, now)
                if self._yolo is not None and self.cfg.enabled:
                    self.measurement = self.tracker.measure(now)
                    self.measured_at = now
            self._times.append(time.monotonic())
            if len(self._times) >= 2:
                self.processing_fps = (len(self._times) - 1) / (self._times[-1] - self._times[0])
            self._stop.wait(max(0.0, period - (time.monotonic() - t0)))

    # views
    def fresh_measurement(self, max_age_s: float = 3.0) -> ApproachMeasurement | None:
        with self._lock:
            if self.measurement and time.time() - self.measured_at <= max_age_s:
                return self.measurement
        return None

    def labelled_detections(self):
        with self._lock:
            return list(self.tracker.last_detections)

    def drain_finished(self) -> list[Track]:
        with self._lock:
            return self.tracker.drain_finished()

    def drain_delays(self) -> list[float]:
        with self._lock:
            return self.tracker.drain_delays()

    def last_departure_ts(self) -> float | None:
        with self._lock:
            return self.tracker.departures[-1] if self.tracker.departures else None

    def stats(self) -> dict:
        counts: dict[str, int] = {}
        states: dict[str, int] = {}
        for d, st in self.labelled_detections():
            counts[d.cls] = counts.get(d.cls, 0) + 1
            states[st] = states.get(st, 0) + 1
        return {
            "status": self.status,
            "processing_fps": round(self.processing_fps, 1),
            "detection_ms": round(self.detection_ms, 1),
            "class_counts": counts,
            "state_counts": states,
            "active_tracks": len(self.tracker.tracks),
            "model_error": self.model_errors.get(self.camera["id"]),
            "tracker": self._yolo.mode if self._yolo is not None else None,
        }


class VisionService:
    def __init__(self, cfg: VisionConfig | None = None) -> None:
        self.cfg = cfg or VisionConfig()
        self.workers: dict[str, VisionWorker] = {}
        self.regions: dict[str, RegionConfig] = {}
        self.model_errors: dict[str, str] = {}
        self._lock = threading.RLock()

    def sync(self, cameras: list[dict], receiver_getter) -> None:
        with self._lock:
            wanted = {c["id"]: c for c in cameras if c["enabled"] and c["stream_url"]}
            for cid in list(self.workers):
                w = self.workers[cid]
                c = wanted.get(cid)
                if c is None or any(w.camera[k] != c[k] for k in ("approach", "processing_fps", "processing_width", "stream_url")):
                    self.workers.pop(cid).stop()
            for cid, c in wanted.items():
                if cid not in self.workers:
                    w = VisionWorker(c, self.regions.get(cid, RegionConfig()), self.cfg, receiver_getter, self.model_errors)
                    self.workers[cid] = w
                    w.start()

    def set_regions(self, camera_id: str, regions: RegionConfig) -> None:
        self.regions[camera_id] = regions
        if camera_id in self.workers:
            self.workers[camera_id].set_regions(regions)

    def apply_config(self, cfg: VisionConfig, cameras: list[dict], receiver_getter) -> None:
        """Model/device/imgsz changes need fresh workers; conf/enabled apply live."""
        reload = (cfg.model, cfg.imgsz, cfg.device) != (self.cfg.model, self.cfg.imgsz, self.cfg.device)
        self.cfg.__dict__.update(cfg.__dict__)
        if reload:
            self.stop_all()
            self.model_errors.clear()
        self.sync(cameras, receiver_getter)

    def stop_all(self) -> None:
        with self._lock:
            for w in self.workers.values():
                w.stop()
            self.workers.clear()

    def worker(self, camera_id: str) -> VisionWorker | None:
        return self.workers.get(camera_id)

    def config_dict(self) -> dict:
        return asdict(self.cfg)

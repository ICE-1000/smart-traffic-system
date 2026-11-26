"""YOLO vehicle detector + ByteTrack tracker (Ultralytics).

One YoloTracker per camera, because ByteTrack keeps per-stream state.
Inference calls are serialised through a global lock: on a laptop CPU,
running several models at once is slower than taking turns.

Licence note: Ultralytics YOLO is AGPL-3.0. Fine for academic research;
closed/commercial deployment needs an Ultralytics Enterprise licence.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger("vision.detector")

# COCO class ids used by the pretrained model
COCO_CLASSES = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}
HEAVY_CLASSES = {"bus", "truck"}

INFERENCE_LOCK = threading.Lock()
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


@dataclass
class Detection:
    track_id: int | None
    cls: str
    confidence: float
    bbox: tuple[float, float, float, float]  # normalised x1, y1, x2, y2

    @property
    def anchor(self) -> tuple[float, float]:
        """Bottom-centre: where the vehicle touches the road."""
        x1, _, x2, y2 = self.bbox
        return ((x1 + x2) / 2, y2)

    @property
    def is_vehicle(self) -> bool:
        return self.cls in VEHICLE_CLASSES


def resolve_model_path(name: str) -> str:
    """Return a local path for the weights, downloading official weights into models/ if needed."""
    p = Path(name)
    if p.exists():
        return str(p)
    local = MODELS_DIR / p.name
    if local.exists():
        return str(local)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from ultralytics.utils.downloads import attempt_download_asset

        got = attempt_download_asset(str(local))
        if Path(got).exists():
            return str(got)
    except Exception as e:  # network down, unknown asset, ...
        log.warning("Could not download %s: %s", name, e)
    return name  # let Ultralytics try its own resolution / raise a clear error


class YoloTracker:
    """YOLO detection + tracking for one camera.

    mode "bytetrack": Ultralytics model.track() with ByteTrack (default).
    mode "iou":       model.predict() + greedy IoU tracker — used automatically if
                      ByteTrack cannot run on this machine (e.g. `lap` missing).
    """

    def __init__(self, model_name: str, conf: float = 0.35, imgsz: int = 640, device: str | None = None) -> None:
        from ultralytics import YOLO  # heavy import, only when vision is used

        from vision.tracking.iou_tracker import IouTracker

        self.model_path = resolve_model_path(model_name)
        self.model = YOLO(self.model_path)
        self.conf = conf
        self.imgsz = imgsz
        self.device = device
        self.last_ms = 0.0
        self.mode = "bytetrack"
        self.fallback_reason: str | None = None
        self._iou = IouTracker()

    def _kwargs(self, conf: float) -> dict:
        kw = dict(classes=list(COCO_CLASSES), conf=conf, imgsz=self.imgsz, agnostic_nms=True, verbose=False)
        if self.device:
            kw["device"] = self.device
        return kw

    def track(self, frame: np.ndarray) -> list[Detection]:
        h, w = frame.shape[:2]
        t0 = time.perf_counter()
        ids = None
        with INFERENCE_LOCK:
            res = None
            if self.mode == "bytetrack":
                try:
                    # ByteTrack re-associates LOW-confidence boxes with existing tracks, so detections down
                    # to 0.1 go to the tracker; new tracks still need >= new_track_thresh (bytetrack.yaml)
                    # and unconfirmed boxes below self.conf are dropped below. agnostic_nms stops one
                    # vehicle getting both "bus" and "car" boxes.
                    res = self.model.track(frame, persist=True, tracker="bytetrack.yaml", **self._kwargs(min(self.conf, 0.1)))[0]
                except (ImportError, ModuleNotFoundError, AttributeError) as e:
                    self.mode, self.fallback_reason = "iou", f"{type(e).__name__}: {e}"[:300]
                    log.warning("ByteTrack unavailable (%s) — using the IoU fallback tracker", self.fallback_reason)
            if res is None:
                res = self.model.predict(frame, **self._kwargs(self.conf))[0]
        boxes = res.boxes
        self.last_ms = (time.perf_counter() - t0) * 1000
        out: list[Detection] = []
        if boxes is None or len(boxes) == 0:
            if self.mode == "iou":
                self._iou.update([])
            return out
        xyxy = boxes.xyxy.cpu().numpy()
        cls = boxes.cls.cpu().numpy().astype(int)
        conf = boxes.conf.cpu().numpy()
        if self.mode == "iou":
            groups = ["person" if COCO_CLASSES.get(int(c)) == "person" else "vehicle" for c in cls]
            ids = self._iou.update([(tuple(float(v) for v in b), g) for b, g in zip(xyxy, groups)])
        else:
            ids = boxes.id.cpu().numpy().astype(int).tolist() if boxes.id is not None else [None] * len(cls)
        for (x1, y1, x2, y2), c, p, tid in zip(xyxy, cls, conf, ids):
            name = COCO_CLASSES.get(int(c))
            if name is None or (tid is None and p < self.conf):
                continue
            out.append(Detection(None if tid is None else int(tid), name, float(p),
                                 (float(x1) / w, float(y1) / h, float(x2) / w, float(y2) / h)))
        return out

"""Draw regions and tracked detections onto a frame for the dashboard stream."""
from __future__ import annotations

import cv2
import numpy as np

from vision.detection.detector import Detection
from vision.regions.config import RegionConfig

# BGR
STATE_COLOUR = {
    "queued": (32, 176, 255),  # amber
    "approaching": (255, 196, 60),  # sky
    "departed": (122, 212, 46),  # green
    "passing": (170, 150, 120),
    "unconfirmed": (140, 140, 140),
    "pedestrian": (255, 255, 255),
    "other": (200, 200, 200),
}


def _pts(poly, w, h) -> np.ndarray:
    return np.array([[int(x * w), int(y * h)] for x, y in poly], dtype=np.int32)


def draw_overlay(img: np.ndarray, regions: RegionConfig | None, dets: list[tuple[Detection, str]],
                 sample: bool = False, show_regions: bool = True) -> np.ndarray:
    out = img.copy()
    h, w = out.shape[:2]
    if regions and show_regions:
        layer = out.copy()
        cv2.fillPoly(layer, [_pts(regions.queue, w, h)], (32, 176, 255))
        cv2.addWeighted(layer, 0.14, out, 0.86, 0, out)
        cv2.polylines(out, [_pts(regions.approach, w, h)], True, (255, 196, 60), 1, cv2.LINE_AA)
        cv2.polylines(out, [_pts(regions.queue, w, h)], True, (32, 176, 255), 1, cv2.LINE_AA)
        if regions.stop_line:
            a, b = _pts(regions.stop_line, w, h)
            cv2.line(out, tuple(a), tuple(b), (80, 80, 255), 2, cv2.LINE_AA)
    scale = max(0.35, w / 2000)
    for d, state in dets:
        x1, y1, x2, y2 = (int(d.bbox[0] * w), int(d.bbox[1] * h), int(d.bbox[2] * w), int(d.bbox[3] * h))
        col = STATE_COLOUR.get(state, (200, 200, 200))
        cv2.rectangle(out, (x1, y1), (x2, y2), col, 2 if state == "queued" else 1, cv2.LINE_AA)
        label = f"{d.cls}{'' if d.track_id is None else f' #{d.track_id}'} {d.confidence:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
        cv2.rectangle(out, (x1, max(0, y1 - th - 6)), (x1 + tw + 6, y1), (31, 19, 8), -1)
        cv2.putText(out, label, (x1 + 3, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, scale, col, 1, cv2.LINE_AA)
    if sample:
        txt = "SAMPLE FOOTAGE - NOT LIVE"
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, scale * 1.1, 2)
        cv2.rectangle(out, (w - tw - 16, h - th - 16), (w - 4, h - 4), (0, 0, 0), -1)
        cv2.putText(out, txt, (w - tw - 10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, scale * 1.1, (32, 176, 255), 2, cv2.LINE_AA)
    return out

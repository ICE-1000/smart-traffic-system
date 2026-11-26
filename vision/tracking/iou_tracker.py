"""Fallback tracker (greedy IoU matching).

Used only if Ultralytics' ByteTrack cannot run on this machine (for example
the `lap` package failed to install). Each detection is matched to the
existing track with the highest box overlap (IoU >= `iou_min`) and the same
broad type (vehicle / person); unmatched detections start a new track after
`min_hits` consecutive frames; tracks are kept for `max_missed` frames.
Less robust to occlusion than ByteTrack, but keeps the system counting.
"""
from __future__ import annotations

from dataclasses import dataclass


def iou(a: tuple, b: tuple) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


@dataclass
class _T:
    id: int | None
    box: tuple
    group: str
    hits: int = 1
    missed: int = 0


class IouTracker:
    def __init__(self, iou_min: float = 0.3, min_hits: int = 2, max_missed: int = 10) -> None:
        self.iou_min, self.min_hits, self.max_missed = iou_min, min_hits, max_missed
        self.tracks: list[_T] = []
        self._next = 1

    def update(self, boxes: list[tuple[tuple, str]]) -> list[int | None]:
        """boxes: [(xyxy, group)] -> track id per box (None while unconfirmed)."""
        pairs = sorted(((iou(b, t.box), i, j) for i, (b, g) in enumerate(boxes)
                        for j, t in enumerate(self.tracks) if t.group == g), reverse=True)
        used_b, used_t, ids = set(), set(), [None] * len(boxes)
        for score, i, j in pairs:
            if score < self.iou_min:
                break
            if i in used_b or j in used_t:
                continue
            used_b.add(i)
            used_t.add(j)
            t = self.tracks[j]
            t.box, t.missed, t.hits = boxes[i][0], 0, t.hits + 1
            if t.id is None and t.hits >= self.min_hits:
                t.id, self._next = self._next, self._next + 1
            ids[i] = t.id
        for j, t in enumerate(self.tracks):
            if j not in used_t:
                t.missed += 1
        self.tracks = [t for t in self.tracks if t.missed <= self.max_missed]
        for i, (b, g) in enumerate(boxes):
            if i not in used_b:
                self.tracks.append(_T(None, b, g))
        return ids

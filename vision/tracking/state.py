"""Per-approach track bookkeeping → ApproachMeasurement.

Each tracked vehicle is classified every update as one of:
    passing      visible but outside the approach region
    approaching  inside the approach region and moving
    queued       inside the queue region and (nearly) stationary
    departed     crossed the stop line (or left after being in the approach)

Counting rules (no double counting across frames):
    arrival    first time a track ID is seen inside the approach region
    departure  first time that track crosses the stop line from the queue side
               (without a stop line: when a track that was in the approach is lost)
    wait time  from the moment a track first became queued until it departs
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from intelligence.types import ApproachMeasurement
from vision.detection.detector import HEAVY_CLASSES, Detection
from vision.regions.config import RegionConfig, centroid, point_in_polygon, side_of_line

# effective road length per class incl. gap (m) — fallback queue-length estimate
CLASS_LENGTH_M = {"car": 7.0, "motorcycle": 3.5, "bus": 14.0, "truck": 13.0}


@dataclass
class TrackerSettings:
    queue_speed: float = 0.06  # normalised frame units / s below which a vehicle in the queue region is waiting
    min_hits: int = 3  # a track must be seen this many times before it is counted (suppresses ID flicker)
    lost_after_s: float = 2.0
    speed_window_s: float = 1.0
    rate_window_s: float = 60.0


@dataclass
class Track:
    id: int
    cls: str
    first_seen: float
    last_seen: float
    positions: deque = field(default_factory=lambda: deque(maxlen=40))  # (t, x, y)
    in_approach: bool = False
    counted_arrival: bool = False
    queued_since: float | None = None
    departed: bool = False
    queue_side: float | None = None  # sign of the queue side of the stop line
    state: str = "passing"
    max_conf: float = 0.0
    last_bbox: tuple = ()
    wait_s: float | None = None  # time spent queued, recorded at departure
    class_votes: dict = field(default_factory=dict)

    def vote(self, cls: str, conf: float) -> None:
        """Class = confidence-weighted majority over the track's lifetime (stops bus/car flicker)."""
        self.class_votes[cls] = self.class_votes.get(cls, 0.0) + conf
        self.cls = max(self.class_votes, key=self.class_votes.get)

    def speed(self, window: float) -> float:
        if len(self.positions) < 2:
            return 0.0
        t1, x1, y1 = self.positions[-1]
        for t0, x0, y0 in self.positions:
            if t1 - t0 <= window:
                break
        dt = t1 - t0
        return math.hypot(x1 - x0, y1 - y0) / dt if dt > 0.05 else 0.0


class ApproachTracker:
    def __init__(self, approach: str, regions: RegionConfig | None = None, settings: TrackerSettings | None = None) -> None:
        self.approach = approach
        self.regions = regions or RegionConfig()
        self.s = settings or TrackerSettings()
        self.tracks: dict[int, Track] = {}
        self.arrivals: deque[float] = deque()
        self.departures: deque[float] = deque()
        self.started_at: float | None = None
        self.finished: list[Track] = []  # expired tracks, drained by the runtime for storage
        self.pedestrians_in_view = 0
        self.last_detections: list[tuple[Detection, str]] = []
        self.departed_delays: list[float] = []  # delay (s) per departed vehicle; 0 if it never queued

    def set_regions(self, regions: RegionConfig) -> None:
        self.regions = regions
        for tr in self.tracks.values():
            tr.queue_side = None

    def _queue_side(self) -> float | None:
        if not self.regions.stop_line:
            return None
        cx, cy = centroid(self.regions.queue)
        s = side_of_line(cx, cy, self.regions.stop_line)
        return math.copysign(1.0, s) if s else None

    # ------------------------------------------------------------ update
    def update(self, detections: list[Detection], t: float) -> None:
        if self.started_at is None:
            self.started_at = t
        r = self.regions
        qside = self._queue_side()
        self.pedestrians_in_view = sum(1 for d in detections if d.cls == "person")
        labelled: list[tuple[Detection, str]] = []

        for d in detections:
            if not d.is_vehicle:
                labelled.append((d, "pedestrian" if d.cls == "person" else "other"))
                continue
            if d.track_id is None:  # tracker not yet confirmed: show, don't count
                labelled.append((d, "unconfirmed"))
                continue
            x, y = d.anchor
            tr = self.tracks.get(d.track_id)
            if tr is None:
                tr = self.tracks[d.track_id] = Track(d.track_id, d.cls, t, t)
            tr.last_seen = t
            tr.vote(d.cls, d.confidence)
            tr.max_conf = max(tr.max_conf, d.confidence)
            tr.last_bbox = d.bbox
            tr.positions.append((t, x, y))

            in_app = point_in_polygon(x, y, r.approach) or point_in_polygon(x, y, r.queue)
            in_q = point_in_polygon(x, y, r.queue)
            if in_app and not tr.counted_arrival and len(tr.positions) >= self.s.min_hits:
                tr.counted_arrival = True
                self.arrivals.append(t)
            tr.in_approach = tr.in_approach or in_app

            # stop-line crossing
            if qside is not None and not tr.departed and tr.counted_arrival:
                s = side_of_line(x, y, r.stop_line)
                if s and math.copysign(1.0, s) != qside:
                    tr.departed = True
                    if tr.queued_since is not None:
                        tr.wait_s = round(t - tr.queued_since, 1)
                    tr.queued_since = None
                    self.departures.append(t)
                    self.departed_delays.append(tr.wait_s or 0.0)

            if tr.departed:
                tr.state = "departed"
            elif in_q and tr.speed(self.s.speed_window_s) < self.s.queue_speed:
                tr.queued_since = tr.queued_since or t
                tr.state = "queued"
            elif in_q and tr.queued_since is not None:
                tr.state = "queued"  # creeping forward inside the queue: still waiting
            elif in_app:
                tr.queued_since = None
                tr.state = "approaching"
            else:
                tr.queued_since = None
                tr.state = "passing"
            labelled.append((Detection(d.track_id, tr.cls, d.confidence, d.bbox), tr.state))

        self.last_detections = labelled
        self._expire(t, qside)

    def _expire(self, t: float, qside: float | None) -> None:
        for tid in [k for k, tr in self.tracks.items() if t - tr.last_seen > self.s.lost_after_s]:
            tr = self.tracks.pop(tid)
            # Without a stop line, a vehicle that was in the approach and is now gone has left.
            if qside is None and tr.in_approach and not tr.departed:
                tr.departed = True
                if tr.queued_since is not None:
                    tr.wait_s = round(tr.last_seen - tr.queued_since, 1)
                self.departures.append(tr.last_seen)
                self.departed_delays.append(tr.wait_s or 0.0)
            self.finished.append(tr)
        for dq in (self.arrivals, self.departures):
            while dq and t - dq[0] > self.s.rate_window_s:
                dq.popleft()

    # ------------------------------------------------------------ measurement
    def _queue_length_m(self, queued: list[Track]) -> float:
        if not queued:
            return 0.0
        r = self.regions
        if r.queue_length_m and r.stop_line:
            # project the furthest queued vehicle onto the stop line → far end of queue polygon axis
            (x1, y1), (x2, y2) = r.stop_line
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            far = max(r.queue, key=lambda p: math.hypot(p[0] - mx, p[1] - my))
            ax, ay = far[0] - mx, far[1] - my
            axis_len2 = ax * ax + ay * ay or 1e-9
            frac = max(((tr.positions[-1][1] - mx) * ax + (tr.positions[-1][2] - my) * ay) / axis_len2 for tr in queued)
            return round(min(1.0, max(0.0, frac)) * r.queue_length_m, 1)
        return round(sum(CLASS_LENGTH_M.get(tr.cls, 7.0) for tr in queued), 1)

    def measure(self, t: float) -> ApproachMeasurement:
        live = [tr for tr in self.tracks.values() if t - tr.last_seen <= 0.6]
        queued = [tr for tr in live if tr.state == "queued"]
        waits = [t - tr.queued_since for tr in queued if tr.queued_since is not None]
        moving = [tr for tr in live if tr.speed(self.s.speed_window_s) >= self.s.queue_speed]
        heavy = sum(1 for tr in live if tr.cls in HEAVY_CLASSES)
        window = min(self.s.rate_window_s, max(1.0, t - (self.started_at or t)))
        return ApproachMeasurement(
            approach=self.approach,  # type: ignore[arg-type]
            queue_count=len(queued),
            queue_length_m=self._queue_length_m(queued),
            avg_wait_s=round(sum(waits) / len(waits), 1) if waits else 0.0,
            max_wait_s=round(max(waits), 1) if waits else 0.0,
            arrival_rate_vpm=round(len(self.arrivals) * 60.0 / window, 1),
            departure_rate_vpm=round(len(self.departures) * 60.0 / window, 1),
            moving_ratio=round(len(moving) / len(live), 2) if live else 0.0,
            vehicles_in_view=len(live),
            heavy_vehicles=heavy,
            light_vehicles=len(live) - heavy,
            pedestrian_request=False,
            source="vision",
            pedestrians_in_view=self.pedestrians_in_view,
        )

    def drain_delays(self) -> list[float]:
        out, self.departed_delays = self.departed_delays, []
        return out

    def drain_finished(self) -> list[Track]:
        out, self.finished = self.finished, []
        return out

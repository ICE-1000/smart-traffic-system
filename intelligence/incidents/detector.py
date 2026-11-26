"""Rule-based incident detection (proposal: "incident detection").

Rules are evaluated every tick per approach. An incident opens when its
condition has held for `confirm_s` and closes after it has been false for
`clear_s` (hysteresis, so one noisy second never raises or clears an alert).

  blocked_discharge  signal green for >= green_s, queue >= min_queue and NO
                     vehicle crossed the stop line in the last window_s —
                     possible breakdown, crash or obstruction at the stop line.
  stalled_vehicle    a queued vehicle has waited >= stall_s — longer than any
                     normal cycle allows (max green x approaches + clearances).
  spillback          queue length >= limit_m for confirm_s — queue reaching the
                     end of the monitored section / upstream junction.
  camera_failure     a configured, enabled camera has been offline >= confirm_s.

These are indicators for an operator to check, not confirmed incidents.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from intelligence.types import ApproachMeasurement

LABEL = {"north": "North", "south": "South", "east": "East", "west": "West"}


@dataclass
class IncidentConfig:
    blocked_green_s: float = 15.0
    blocked_min_queue: int = 2
    blocked_window_s: float = 12.0
    stall_s: float = 240.0
    spillback_limit_m: float = 180.0
    confirm_s: float = 5.0
    clear_s: float = 20.0
    camera_offline_s: float = 30.0


@dataclass
class Incident:
    key: str  # kind:approach
    kind: str
    approach: str | None
    severity: str  # warning | critical
    started: float
    message: str
    ended: float | None = None
    db_id: int | None = None
    acknowledged: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class IncidentDetector:
    def __init__(self, config: IncidentConfig | None = None) -> None:
        self.config = config or IncidentConfig()
        self.active: dict[str, Incident] = {}
        self._cond_since: dict[str, float] = {}
        self._false_since: dict[str, float] = {}
        self._offline_since: dict[str, float] = {}
        self.closed: list[Incident] = []  # drained by the runtime for storage
        self.opened: list[Incident] = []

    def _evaluate(self, key: str, cond: bool, now: float, make) -> None:
        c = self.config
        if cond:
            self._false_since.pop(key, None)
            since = self._cond_since.setdefault(key, now)
            if key not in self.active and now - since >= c.confirm_s:
                inc = make()
                self.active[key] = inc
                self.opened.append(inc)
            elif key in self.active:
                self.active[key].message = make().message  # keep numbers current
        else:
            self._cond_since.pop(key, None)
            if key in self.active:
                fs = self._false_since.setdefault(key, now)
                if now - fs >= c.clear_s:
                    inc = self.active.pop(key)
                    inc.ended = now
                    self.closed.append(inc)
                    self._false_since.pop(key, None)

    def update(self, measurements: dict[str, ApproachMeasurement], colours: dict[str, str],
               green_elapsed: dict[str, float], last_departure: dict[str, float | None],
               cameras: list[dict], now: float | None = None) -> None:
        now = time.time() if now is None else now
        c = self.config
        for a, m in measurements.items():
            if m.source == "none":
                for kind in ("blocked_discharge", "stalled_vehicle", "spillback"):
                    self._evaluate(f"{kind}:{a}", False, now, lambda: None)
                continue
            ld = last_departure.get(a)
            blocked = (colours.get(a) == "green" and green_elapsed.get(a, 0) >= c.blocked_green_s
                       and m.queue_count >= c.blocked_min_queue
                       and (ld is None or now - ld >= c.blocked_window_s))
            self._evaluate(f"blocked_discharge:{a}", blocked, now, lambda a=a, m=m: Incident(
                f"blocked_discharge:{a}", "blocked_discharge", a, "critical", now,
                f"{LABEL[a]}: {m.queue_count} vehicles queued but none crossed the stop line during "
                f"{green_elapsed.get(a, 0):.0f}s of green — possible breakdown or obstruction."))
            self._evaluate(f"stalled_vehicle:{a}", m.max_wait_s >= c.stall_s, now, lambda a=a, m=m: Incident(
                f"stalled_vehicle:{a}", "stalled_vehicle", a, "warning", now,
                f"{LABEL[a]}: a vehicle has been stationary in the queue for {m.max_wait_s:.0f}s "
                f"(limit {c.stall_s:.0f}s)."))
            self._evaluate(f"spillback:{a}", m.queue_length_m >= c.spillback_limit_m, now, lambda a=a, m=m: Incident(
                f"spillback:{a}", "spillback", a, "warning", now,
                f"{LABEL[a]}: queue {m.queue_length_m:.0f} m reaches the monitored limit ({c.spillback_limit_m:.0f} m)."))
        for cam in cameras:
            key = f"camera_failure:{cam['id']}"
            offline = bool(cam.get("enabled") and cam.get("has_stream_url") and cam.get("status") != "online")
            if offline:
                self._offline_since.setdefault(key, now)
            else:
                self._offline_since.pop(key, None)
            # condition = offline long enough; _evaluate then adds confirm_s, so the total is camera_offline_s
            cond = offline and now - self._offline_since[key] >= max(0.0, c.camera_offline_s - c.confirm_s)
            self._evaluate(key, cond, now, lambda cam=cam: Incident(
                f"camera_failure:{cam['id']}", "camera_failure", cam.get("approach"), "warning", now,
                f"Camera {cam['id']} ({cam.get('name', '')}) offline: {cam.get('detail', '')}"))
        for key in [k for k in self.active if k.startswith("camera_failure:")]:
            if key.split(":", 1)[1] not in {cam["id"] for cam in cameras}:
                self._evaluate(key, False, now + self.config.clear_s, lambda: None)  # camera removed

    def drain(self) -> tuple[list[Incident], list[Incident]]:
        o, c = self.opened, self.closed
        self.opened, self.closed = [], []
        return o, c

    def active_list(self) -> list[dict]:
        return [i.to_dict() for i in sorted(self.active.values(), key=lambda i: i.started, reverse=True)]

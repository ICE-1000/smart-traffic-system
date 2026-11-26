"""Adaptive vs fixed-time evaluation (research question 2).

A counterfactual comparison: the SAME vehicle arrivals are fed into two
identical queue models of the junction. One is controlled by this
project's adaptive controller (priority engine + safe signal simulator),
the other by a conventional fixed-time plan. Because the arrivals are
identical, any difference in delay, queues and throughput is
caused by the signal plan alone.

Arrivals are generated each second from the MEASURED arrival rate of each
approach (camera + AI where available, otherwise the labelled demo model)
and the measured heavy-vehicle share, using one random draw shared by
both models.

Model assumptions (documented in docs/ALGORITHMS.md §4):
  * one stop line per approach, saturation flow `saturation_vps`
    (default 0.5 veh/s = 1 800 veh/h), 2 s start-up lost time,
    discharge at half rate during yellow;
  * delay = time from arrival at the queue to crossing the stop line;
  * the heavy-vehicle share per approach is the measured share smoothed
    over about two minutes (initial value 18 %);
  * results are model estimates for decision support, not measurements of
    what the real signals did.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import asdict, dataclass, field

from intelligence.congestion.engine import CongestionEngine
from intelligence.priority.engine import PriorityEngine
from intelligence.simulation.signal import SignalConfig, SignalSimulator
from intelligence.types import APPROACHES, ApproachMeasurement, SignalColour

CLASS_LENGTH_M = {"car": 7.0, "motorcycle": 3.5, "bus": 14.0, "truck": 13.0}
STARTUP_LOST_S = 2.0


@dataclass
class FixedTimePlan:
    """Conventional fixed-time plan: every approach gets its green in a fixed
    order, every cycle, regardless of demand."""
    order: list[str] = field(default_factory=lambda: ["north", "east", "south", "west"])
    green_s: dict[str, float] = field(default_factory=lambda: {a: 25.0 for a in APPROACHES})

    def validate(self) -> None:
        if sorted(self.order) != sorted(APPROACHES):
            raise ValueError("order must contain each approach exactly once")
        if any(g < 5 or g > 180 for g in self.green_s.values()):
            raise ValueError("fixed green times must be between 5 and 180 s")

    def cycle_s(self, yellow_s: float, clearance_s: float) -> float:
        return sum(self.green_s[a] for a in self.order) + len(self.order) * (yellow_s + clearance_s)


class FixedTimeController:
    def __init__(self, plan: FixedTimePlan, signal_cfg: SignalConfig) -> None:
        self.plan = plan
        self.cfg = signal_cfg
        self.idx = 0
        self.stage = "green"
        self.elapsed = 0.0

    @property
    def current(self) -> str:
        return self.plan.order[self.idx]

    def colours(self) -> dict[str, SignalColour]:
        out = {a: SignalColour.RED for a in APPROACHES}
        if self.stage == "green":
            out[self.current] = SignalColour.GREEN
        elif self.stage == "yellow":
            out[self.current] = SignalColour.YELLOW
        return out

    def tick(self, dt: float) -> None:
        self.elapsed += dt
        if self.stage == "green" and self.elapsed >= self.plan.green_s[self.current]:
            self.stage, self.elapsed = "yellow", 0.0
        elif self.stage == "yellow" and self.elapsed >= self.cfg.yellow_s:
            self.stage, self.elapsed = "all_red", 0.0
        elif self.stage == "all_red" and self.elapsed >= self.cfg.clearance_s:
            self.idx = (self.idx + 1) % len(self.plan.order)
            self.stage, self.elapsed = "green", 0.0


@dataclass
class _Veh:
    cls: str
    arrived: float


class QueueWorld:
    """Queues at one junction under one controller."""

    def __init__(self, saturation_vps: float) -> None:
        self.sat = saturation_vps
        self.queues: dict[str, deque[_Veh]] = {a: deque() for a in APPROACHES}
        self.green_for = {a: 0.0 for a in APPROACHES}
        self.credit = {a: 0.0 for a in APPROACHES}
        self.arr_times: dict[str, deque[float]] = {a: deque() for a in APPROACHES}
        self.dep_times: dict[str, deque[float]] = {a: deque() for a in APPROACHES}
        # accumulators
        self.arrived = {a: 0 for a in APPROACHES}
        self.departed = {a: 0 for a in APPROACHES}
        self.delay_s = {a: 0.0 for a in APPROACHES}  # delay of departed vehicles
        self.max_queue = {a: 0 for a in APPROACHES}
        self.stops = 0  # vehicles that had to stop (delay > 0)

    def add(self, approach: str, cls: str, t: float) -> None:
        self.queues[approach].append(_Veh(cls, t))
        self.arrived[approach] += 1
        self.arr_times[approach].append(t)

    def step(self, t: float, dt: float, colours: dict[str, SignalColour]) -> None:
        for a in APPROACHES:
            c = colours[a]
            q = self.queues[a]
            if c == SignalColour.GREEN:
                self.green_for[a] += dt
                if self.green_for[a] > STARTUP_LOST_S:
                    self.credit[a] += self.sat * dt
            elif c == SignalColour.YELLOW:
                self.credit[a] += 0.5 * self.sat * dt
            else:
                self.green_for[a] = 0.0
                self.credit[a] = 0.0
            while self.credit[a] >= 1.0 and q:
                v = q.popleft()
                self.credit[a] -= 1.0
                d = max(0.0, t - v.arrived)
                self.departed[a] += 1
                self.delay_s[a] += d
                if d > 0.5:
                    self.stops += 1
                self.dep_times[a].append(t)
            if not q:
                self.credit[a] = min(self.credit[a], 1.0)
            self.max_queue[a] = max(self.max_queue[a], len(q))
            for dq in (self.arr_times[a], self.dep_times[a]):
                while dq and t - dq[0] > 60.0:
                    dq.popleft()

    def measurement(self, a: str, t: float, window: float) -> ApproachMeasurement:
        q = self.queues[a]
        waits = [t - v.arrived for v in q]
        heavy = sum(1 for v in q if v.cls in ("bus", "truck"))
        return ApproachMeasurement(
            a, len(q), sum(CLASS_LENGTH_M.get(v.cls, 7.0) for v in q),
            sum(waits) / len(waits) if waits else 0.0, max(waits) if waits else 0.0,
            len(self.arr_times[a]) * 60.0 / window, len(self.dep_times[a]) * 60.0 / window,
            0.0, len(q), heavy, len(q) - heavy, False, "model",  # type: ignore[arg-type]
        )

    def residual_delay(self, t: float) -> float:
        """Delay so far of vehicles still queued (counted so a plan cannot 'hide' delay in its queue)."""
        return sum(t - v.arrived for q in self.queues.values() for v in q)


class ComparisonEngine:
    def __init__(self, priority_cfg, signal_cfg: SignalConfig, congestion: CongestionEngine,
                 plan: FixedTimePlan | None = None, saturation_vps: float = 0.5, seed: int = 11) -> None:
        self.priority_cfg = priority_cfg  # shared with the live engine (operator tuning applies)
        self.signal_cfg = signal_cfg
        self.congestion = congestion
        self.plan = plan or FixedTimePlan()
        self.saturation_vps = saturation_vps
        self.seed = seed
        self.series: deque[dict] = deque(maxlen=720)  # 2 h at one point / 10 s
        self.reset()

    def reset(self) -> None:
        self.plan.validate()
        self.rng = random.Random(self.seed)
        self.t = 0.0
        self.adaptive = QueueWorld(self.saturation_vps)
        self.fixed = QueueWorld(self.saturation_vps)
        self.adaptive_ctl = SignalSimulator(PriorityEngine(self.priority_cfg), self.signal_cfg)
        self.fixed_ctl = FixedTimeController(self.plan, self.signal_cfg)
        self.series.clear()
        self.inputs: dict[str, dict] = {}
        self._heavy: dict[str, float] = {a: 0.18 for a in APPROACHES}  # smoothed heavy-vehicle share
        self._last_point = -10.0

    def _poisson(self, lam: float) -> int:
        import math

        l, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= l:
                return k
            k += 1

    def step(self, dt: float, measured: dict[str, ApproachMeasurement]) -> None:
        self.t += dt
        t = self.t
        # 1. identical arrivals into both worlds
        for a in APPROACHES:
            m = measured[a]
            rate = 0.0 if m.source == "none" else max(0.0, m.arrival_rate_vpm)
            if m.vehicles_in_view:
                # exponential smoothing (~2 min time constant): one bus in view must not make the share 100 %
                self._heavy[a] += 0.008 * (m.heavy_vehicles / m.vehicles_in_view - self._heavy[a])
            heavy_share = self._heavy[a]
            self.inputs[a] = {"rate_vpm": round(rate, 2), "heavy_share": round(heavy_share, 2), "source": m.source}
            for _ in range(self._poisson(rate * dt / 60.0)):
                r = self.rng.random()
                cls = ("bus" if self.rng.random() < 0.45 else "truck") if r < heavy_share else (
                    "motorcycle" if self.rng.random() < 0.15 else "car")
                self.adaptive.add(a, cls, t)
                self.fixed.add(a, cls, t)
        # 2. controllers
        window = min(60.0, max(1.0, t))
        ms = {a: self.adaptive.measurement(a, t, window) for a in APPROACHES}
        cg = self.congestion.evaluate_all(list(ms.values()))
        self.adaptive_ctl.tick(dt, ms, cg)
        self.fixed_ctl.tick(dt)
        # 3. discharge
        self.adaptive.step(t, dt, self.adaptive_ctl.colours())
        self.fixed.step(t, dt, self.fixed_ctl.colours())
        if t - self._last_point >= 10.0:
            self._last_point = t
            a, f = self._world_summary(self.adaptive), self._world_summary(self.fixed)
            self.series.append({"t": round(t), "adaptive_delay": a["mean_delay_s"], "fixed_delay": f["mean_delay_s"],
                                "adaptive_queue": a["queued_now"], "fixed_queue": f["queued_now"]})

    # ------------------------------------------------------------ results
    def _world_summary(self, w: QueueWorld) -> dict:
        dep = sum(w.departed.values())
        delay = sum(w.delay_s.values())
        total_delay_h = (delay + w.residual_delay(self.t)) / 3600.0
        return {
            "arrived": sum(w.arrived.values()),
            "departed": dep,
            "throughput_vph": round(dep / self.t * 3600, 1) if self.t > 0 else 0.0,
            "mean_delay_s": round(delay / dep, 1) if dep else 0.0,
            "vehicle_hours_delay": round(total_delay_h, 3),
            "queued_now": sum(len(q) for q in w.queues.values()),
            "max_queue": dict(w.max_queue),
            "stop_rate": round(w.stops / dep, 3) if dep else 0.0,
            "per_approach_mean_delay_s": {a: round(w.delay_s[a] / w.departed[a], 1) if w.departed[a] else 0.0 for a in APPROACHES},
        }

    def summary(self) -> dict:
        a = self._world_summary(self.adaptive)
        f = self._world_summary(self.fixed)

        def pct(fixed: float, adaptive: float) -> float | None:
            return round((fixed - adaptive) / fixed * 100.0, 1) if fixed > 0 else None

        return {
            "elapsed_s": round(self.t),
            "warming_up": self.t < 600,
            "inputs": self.inputs,
            "adaptive": a,
            "fixed": f,
            "improvement_pct": {
                "mean_delay": pct(f["mean_delay_s"], a["mean_delay_s"]),
                "vehicle_hours_delay": pct(f["vehicle_hours_delay"], a["vehicle_hours_delay"]),
                "stop_rate": pct(f["stop_rate"], a["stop_rate"]),
                "throughput": round((a["throughput_vph"] - f["throughput_vph"]) / f["throughput_vph"] * 100, 1)
                if f["throughput_vph"] else None,
            },
            "fixed_plan": {**asdict(self.plan), "cycle_s": self.plan.cycle_s(self.signal_cfg.yellow_s, self.signal_cfg.clearance_s)},
            "saturation_vps": self.saturation_vps,
            "series": list(self.series),
        }

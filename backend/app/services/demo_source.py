"""DEMONSTRATION measurement source (Phase 1).

Produces ApproachMeasurement objects from a small stochastic queueing
model so the congestion, priority and simulation engines can be
exercised before the camera / vision pipeline exists (Phases 2-5).

Everything produced here is tagged source="demo" and the dashboard
labels it SIMULATED. It is NOT real traffic data and must not be
presented as such.

Model: Poisson arrivals per approach (rate configurable at runtime),
vehicles queue behind the stop line while the simulated signal is not
green, and discharge at a saturation flow when green. Because the
signal simulator feeds back into this model, you can watch the priority
engine react to the demand it creates.
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass

from intelligence.types import APPROACHES, ApproachMeasurement

# class -> (share, effective queue length in metres incl. gap, heavy?)
VEHICLE_MIX = {
    "car": (0.70, 7.0, False),
    "motorcycle": (0.12, 3.5, False),
    "bus": (0.08, 14.0, True),
    "truck": (0.10, 13.0, True),
}

DEFAULT_RATES_VPM = {"north": 9.0, "south": 6.0, "east": 2.5, "west": 0.8}


@dataclass
class _Vehicle:
    cls: str
    arrived_at: float


class _ApproachModel:
    def __init__(self, name: str, rate_vpm: float, rng: random.Random) -> None:
        self.name = name
        self.base_rate = rate_vpm
        self.rng = rng
        self.queue: deque[_Vehicle] = deque()
        self.arrivals: deque[float] = deque()  # timestamps, rolling 60 s
        self.departures: deque[float] = deque()
        self.moving: deque[tuple[float, str]] = deque()  # recently departed, still in view
        self.green_for = 0.0
        self.discharge_credit = 0.0
        self.total_seen = 0
        self.phase = rng.random() * math.tau
        self.departed_delays: list[float] = []  # delay (s) of each vehicle that crossed the stop line

    def rate_at(self, t: float) -> float:
        # Slow ±35 % wave (~6 min period) so demand visibly shifts over time.
        return max(0.0, self.base_rate * (1 + 0.35 * math.sin(t / 57.0 + self.phase)))

    def _poisson(self, lam: float) -> int:
        l, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= l:
                return k
            k += 1

    def _pick_class(self) -> str:
        r, acc = self.rng.random(), 0.0
        for cls, (share, _, _) in VEHICLE_MIX.items():
            acc += share
            if r <= acc:
                return cls
        return "car"

    def step(self, t: float, dt: float, colour: str, saturation_vps: float) -> None:
        for _ in range(self._poisson(self.rate_at(t) * dt / 60.0)):
            self.queue.append(_Vehicle(self._pick_class(), t))
            self.arrivals.append(t)
            self.total_seen += 1

        if colour == "green":
            self.green_for += dt
            if self.green_for > 2.0:  # start-up lost time
                self.discharge_credit += saturation_vps * dt
        elif colour == "yellow":
            self.discharge_credit += 0.5 * saturation_vps * dt
        else:
            self.green_for = 0.0
            self.discharge_credit = 0.0

        while self.discharge_credit >= 1.0 and self.queue:
            v = self.queue.popleft()
            self.discharge_credit -= 1.0
            self.departures.append(t)
            self.departed_delays.append(max(0.0, t - v.arrived_at))
            self.moving.append((t, v.cls))
        if not self.queue:
            self.discharge_credit = min(self.discharge_credit, 1.0)

        for dq in (self.arrivals, self.departures):
            while dq and t - dq[0] > 60.0:
                dq.popleft()
        while self.moving and t - self.moving[0][0] > 6.0:
            self.moving.popleft()

    def measure(self, t: float) -> ApproachMeasurement:
        waits = [t - v.arrived_at for v in self.queue]
        in_view_classes = [v.cls for v in self.queue] + [c for _, c in self.moving]
        heavy = sum(1 for c in in_view_classes if VEHICLE_MIX[c][2])
        window = min(60.0, max(t, 1.0))
        in_view = len(in_view_classes)
        return ApproachMeasurement(
            approach=self.name,  # type: ignore[arg-type]
            queue_count=len(self.queue),
            queue_length_m=round(sum(VEHICLE_MIX[v.cls][1] for v in self.queue), 1),
            avg_wait_s=round(sum(waits) / len(waits), 1) if waits else 0.0,
            max_wait_s=round(max(waits), 1) if waits else 0.0,
            arrival_rate_vpm=round(len(self.arrivals) * 60.0 / window, 1),
            departure_rate_vpm=round(len(self.departures) * 60.0 / window, 1),
            moving_ratio=round(len(self.moving) / in_view, 2) if in_view else 0.0,
            vehicles_in_view=in_view,
            heavy_vehicles=heavy,
            light_vehicles=in_view - heavy,
            pedestrian_request=False,  # set by the runtime from operator calls
            source="demo",
        )


class DemoTrafficSource:
    source_name = "demo"

    def __init__(self, seed: int | None = 7, saturation_vps: float = 0.6,
                 rates: dict[str, float] | None = None) -> None:
        self.rng = random.Random(seed)
        self.saturation_vps = saturation_vps
        rates = {**DEFAULT_RATES_VPM, **(rates or {})}
        self.models = {a: _ApproachModel(a, rates[a], self.rng) for a in APPROACHES}
        self.t = 0.0

    def step(self, dt: float, colours: dict[str, str]) -> dict[str, ApproachMeasurement]:
        self.t += dt
        for a, m in self.models.items():
            m.step(self.t, dt, colours.get(a, "red"), self.saturation_vps)
        return self.measure()

    def measure(self) -> dict[str, ApproachMeasurement]:
        return {a: m.measure(self.t) for a, m in self.models.items()}

    def set_rate(self, approach: str, vpm: float) -> None:
        self.models[approach].base_rate = max(0.0, min(vpm, 60.0))

    def rates(self) -> dict[str, float]:
        return {a: m.base_rate for a, m in self.models.items()}

    def drain_delays(self) -> dict[str, list[float]]:
        """Delays of vehicles that departed since the last call, per approach."""
        out = {a: m.departed_delays for a, m in self.models.items()}
        for m in self.models.values():
            m.departed_delays = []
        return out

    def totals(self) -> dict[str, int]:
        return {a: m.total_seen for a, m in self.models.items()}

"""Congestion Index (CI) — the proposal's benchmarking measure.

    CI  = (actual travel time - free-flow travel time) / free-flow travel time
    TTI = actual / free-flow = 1 + CI          (Travel Time Index, FHWA/TTI usage)

At a junction approach the actual travel time over the monitored section
is the free-flow time plus the junction delay, so

    CI = mean delay per vehicle / free-flow travel time of the section,
    free-flow time = section length / free-flow speed.

* mean delay: vehicles that crossed the stop line in the last `window_s`
  (vehicles that never queued count as 0 s delay).
* section length: the camera's measured queue-area length if configured,
  otherwise `default_section_m`.
* free-flow speed: should be MEASURED — e.g. off-peak moving-car runs on
  the Field Surveys page (FHWA practice: free-flow speed from off-peak
  conditions). The default 40 km/h is a placeholder.

No congested / uncongested thresholds are imposed: CI and TTI are reported
as numbers and compared between periods and with the corridor CI from the
moving-car surveys.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass


@dataclass
class IndexConfig:
    free_flow_kmh: float = 40.0
    default_section_m: float = 100.0
    window_s: float = 300.0
    min_samples: int = 3

    def validate(self) -> None:
        if not 5 <= self.free_flow_kmh <= 120:
            raise ValueError("free-flow speed must be 5–120 km/h")
        if not 10 <= self.default_section_m <= 2000:
            raise ValueError("section length must be 10–2000 m")
        if not 60 <= self.window_s <= 3600:
            raise ValueError("window must be 60–3600 s")

    def to_dict(self) -> dict:
        return asdict(self)


def free_flow_time_s(section_m: float, free_flow_kmh: float) -> float:
    return section_m / (free_flow_kmh / 3.6)


def congestion_index(mean_delay_s: float, section_m: float, free_flow_kmh: float) -> float:
    return mean_delay_s / free_flow_time_s(section_m, free_flow_kmh)


class DelayWindow:
    """Rolling window of (timestamp, delay) for one approach."""

    def __init__(self) -> None:
        self.samples: deque[tuple[float, float]] = deque()
        self.source: str | None = None

    def add(self, ts: float, delays: list[float], source: str) -> None:
        if source != self.source:  # never mix camera and demo delays in one mean
            self.samples.clear()
            self.source = source
        for d in delays:
            self.samples.append((ts, d))

    def result(self, now: float, section_m: float, cfg: IndexConfig) -> dict:
        while self.samples and now - self.samples[0][0] > cfg.window_s:
            self.samples.popleft()
        n = len(self.samples)
        t_ff = free_flow_time_s(section_m, cfg.free_flow_kmh)
        if n < cfg.min_samples:
            return {"samples": n, "mean_delay_s": None, "ci": None, "tti": None,
                    "section_m": round(section_m, 1), "free_flow_s": round(t_ff, 1)}
        mean = sum(d for _, d in self.samples) / n
        ci = mean / t_ff
        return {"samples": n, "mean_delay_s": round(mean, 1), "ci": round(ci, 2), "tti": round(1 + ci, 2),
                "section_m": round(section_m, 1), "free_flow_s": round(t_ff, 1)}

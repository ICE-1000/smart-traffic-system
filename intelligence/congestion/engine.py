"""Congestion analysis engine.

Turns raw approach measurements into a 0-100 congestion score using a
configurable weighted model (see docs/ALGORITHMS.md for the rationale).

    score = 100 * Σ wᵢ · clamp(xᵢ / normᵢ, 0, 1)

Indicators: queue count, average waiting time, queue length, arrival
rate, and a "net growth" term (arrivals exceeding departures means the
queue is building). Weights must sum to 1.0.

This module only *measures*. It never decides who gets green — that is
the priority engine's job.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from intelligence.types import ApproachMeasurement, CongestionResult


@dataclass
class CongestionConfig:
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "queue_count": 0.30,
            "wait_time": 0.30,
            "queue_length": 0.20,
            "arrival_rate": 0.10,
            "net_growth": 0.10,
        }
    )
    # Values at or above these saturate the normalised indicator to 1.0.
    norms: dict[str, float] = field(
        default_factory=lambda: {
            "queue_count": 30.0,  # vehicles
            "wait_time": 120.0,  # seconds
            "queue_length": 180.0,  # metres
            "arrival_rate": 30.0,  # vehicles / minute
            "net_growth": 15.0,  # (arrivals - departures) vehicles / minute
        }
    )
    # Upper bounds (exclusive) of each category on the 0-100 scale.
    thresholds: dict[str, float] = field(
        default_factory=lambda: {"free": 10, "light": 30, "moderate": 55, "heavy": 75}
    )

    def validate(self) -> None:
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Congestion weights must sum to 1.0 (got {total:.3f})")
        missing = set(self.weights) ^ set(self.norms)
        if missing:
            raise ValueError(f"weights/norms keys mismatch: {sorted(missing)}")
        if any(v <= 0 for v in self.norms.values()):
            raise ValueError("All normalisation bounds must be positive")


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


class CongestionEngine:
    def __init__(self, config: CongestionConfig | None = None) -> None:
        self.config = config or CongestionConfig()
        self.config.validate()

    def categorise(self, score: float) -> str:
        t = self.config.thresholds
        if score < t["free"]:
            return "free"
        if score < t["light"]:
            return "light"
        if score < t["moderate"]:
            return "moderate"
        if score < t["heavy"]:
            return "heavy"
        return "critical"

    def evaluate(self, m: ApproachMeasurement) -> CongestionResult:
        n = self.config.norms
        raw = {
            "queue_count": m.queue_count,
            "wait_time": m.avg_wait_s,
            "queue_length": m.queue_length_m,
            "arrival_rate": m.arrival_rate_vpm,
            "net_growth": m.arrival_rate_vpm - m.departure_rate_vpm,
        }
        components = {k: round(_clamp01(v / n[k]), 4) for k, v in raw.items()}
        contributions = {
            k: round(100 * self.config.weights[k] * components[k], 2) for k in components
        }
        score = round(sum(contributions.values()), 1)
        return CongestionResult(
            approach=m.approach,
            score=score,
            category=self.categorise(score),  # type: ignore[arg-type]
            components=components,
            contributions=contributions,
        )

    def evaluate_all(self, ms: list[ApproachMeasurement]) -> dict[str, CongestionResult]:
        return {m.approach: self.evaluate(m) for m in ms}

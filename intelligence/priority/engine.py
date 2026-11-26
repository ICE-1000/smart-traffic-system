"""Traffic-priority decision engine.

Given congestion results and service history, recommends which approach
should be served next and explains why — in words generated from the
actual numbers.

Priority index for approach i (0-100+):

    P_i = w_demand · congestion_score_i
        + w_wait   · 100 · clamp(time_since_served_i / starvation_s, 0, 1)

Rules applied in order:
1. Starvation guard — any approach with demand (vehicles or pedestrian
   request) that has not been served for >= starvation_s wins outright
   (longest-starved first).
2. Empty-approach skip — approaches with no queue and no pedestrian
   request are skipped, *unless* they have gone unserved for
   max_skip_s (covers undetected turning traffic, cyclists, pedestrians).
3. Highest priority index wins; ties broken by longest time since served.

The engine is stateless with respect to the clock: the caller passes
`time_since_served`. This keeps it deterministic and unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from intelligence.types import ApproachMeasurement, CongestionResult

LABEL = {"north": "North", "south": "South", "east": "East", "west": "West"}


@dataclass
class PriorityConfig:
    demand_weight: float = 0.7
    wait_weight: float = 0.3
    starvation_s: float = 90.0  # force service after this long with demand
    max_skip_s: float = 180.0  # an empty approach is still served after this long
    min_queue_to_serve: int = 1


@dataclass
class ApproachPriority:
    approach: str
    priority_index: float
    congestion_score: float
    queue_count: int
    avg_wait_s: float
    time_since_served_s: float
    eligible: bool
    note: str


@dataclass
class PriorityDecision:
    recommended: str | None
    next_recommended: str | None
    rule: str  # "demand" | "starvation" | "max_skip" | "no_data" | "no_demand"
    reason: str
    ranking: list[ApproachPriority] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


class PriorityEngine:
    def __init__(self, config: PriorityConfig | None = None) -> None:
        self.config = config or PriorityConfig()

    def _has_demand(self, m: ApproachMeasurement) -> bool:
        return m.queue_count >= self.config.min_queue_to_serve or m.pedestrian_request

    def decide(
        self,
        measurements: dict[str, ApproachMeasurement],
        congestion: dict[str, CongestionResult],
        time_since_served: dict[str, float],
        exclude: str | None = None,
    ) -> PriorityDecision:
        """Rank approaches. `exclude` removes the currently-green approach
        when the caller is choosing what to switch *to*."""
        c = self.config
        ranking: list[ApproachPriority] = []
        for a, m in measurements.items():
            if a == exclude:
                continue
            tss = time_since_served.get(a, 0.0)
            idx = c.demand_weight * congestion[a].score + c.wait_weight * 100 * _clamp01(
                tss / c.starvation_s
            )
            demand = self._has_demand(m)
            if m.source == "none":
                # No camera data: demand unknown. Fall back to fixed-time style service
                # once the approach has waited the starvation limit.
                idx = c.wait_weight * 100 * _clamp01(tss / c.starvation_s)
                eligible = tss >= c.starvation_s or m.pedestrian_request
                note = "no data — fixed-time fallback" if eligible else "no data — waiting for fallback slot"
            elif demand:
                eligible, note = True, "has demand"
            elif tss >= c.max_skip_s:
                eligible, note = True, f"no detected demand but unserved ≥ {c.max_skip_s:.0f}s"
            else:
                eligible, note = False, "skipped: no queue and no pedestrian request"
            ranking.append(
                ApproachPriority(
                    approach=a,
                    priority_index=round(idx, 1),
                    congestion_score=congestion[a].score,
                    queue_count=m.queue_count,
                    avg_wait_s=round(m.avg_wait_s, 1),
                    time_since_served_s=round(tss, 1),
                    eligible=eligible,
                    note=note,
                )
            )

        ranking.sort(key=lambda r: (r.eligible, r.priority_index, r.time_since_served_s), reverse=True)
        eligible = [r for r in ranking if r.eligible]

        if not eligible:
            return PriorityDecision(None, None, "no_demand", "No approach currently has detected demand; holding current phase.", ranking)

        # Rule 1: starvation guard
        starved = [
            r for r in eligible
            if r.time_since_served_s >= c.starvation_s and self._has_demand(measurements[r.approach])
        ]
        if starved:
            starved.sort(key=lambda r: r.time_since_served_s, reverse=True)
            top = starved[0]
            rest = [r for r in eligible if r.approach != top.approach]
            reason = (
                f"{LABEL[top.approach]} approach prioritised by the fairness rule: "
                f"{top.queue_count} vehicles have gone unserved for {top.time_since_served_s:.0f}s "
                f"(limit {c.starvation_s:.0f}s), even though its congestion score is {top.congestion_score:.0f}."
            )
            return PriorityDecision(top.approach, rest[0].approach if rest else None, "starvation", reason, ranking)

        top = eligible[0]
        nxt = eligible[1].approach if len(eligible) > 1 else None
        if measurements[top.approach].source == "none":
            reason = (
                f"{LABEL[top.approach]} approach served on the fixed-time fallback: no camera data, "
                f"unserved for {top.time_since_served_s:.0f}s (limit {c.starvation_s:.0f}s)."
            )
            return PriorityDecision(top.approach, nxt, "no_data", reason, ranking)
        if not self._has_demand(measurements[top.approach]):
            reason = (
                f"{LABEL[top.approach]} approach scheduled for a service check: no vehicles detected, "
                f"but it has not been served for {top.time_since_served_s:.0f}s (limit {c.max_skip_s:.0f}s) — "
                "covers undetected turning traffic and pedestrians."
            )
            return PriorityDecision(top.approach, nxt, "max_skip", reason, ranking)

        reason = self._demand_reason(top, eligible[1:])
        return PriorityDecision(top.approach, nxt, "demand", reason, ranking)

    @staticmethod
    def _demand_reason(top: ApproachPriority, others: list[ApproachPriority]) -> str:
        parts = [f"{top.queue_count} queued vehicles", f"congestion score {top.congestion_score:.0f}"]
        if top.avg_wait_s > 0:
            parts.append(f"average wait {top.avg_wait_s:.0f}s")
        reason = f"{LABEL[top.approach]} approach prioritised: highest priority index ({top.priority_index:.0f}) from " + ", ".join(parts)
        if others:
            o = others[0]
            reason += f". Next: {LABEL[o.approach]} (index {o.priority_index:.0f}, {o.queue_count} queued)."
        else:
            reason += "."
        return reason

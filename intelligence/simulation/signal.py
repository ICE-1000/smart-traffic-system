"""Traffic-signal SIMULATION engine.

SAFETY: this is a research/simulation component only. It has no output
to any physical controller and must never be wired to one. Real-world
deployment requires the road authority, qualified traffic engineers,
approved equipment and formal safety validation.

State machine per cycle:

    GREEN(a) --(min green reached) and (queue cleared | max green | fairness)-->
    YELLOW(a) --yellow_s--> ALL_RED --clearance_s--> GREEN(b)

Demand-responsive in two ways (queue-clearance actuated control):
  * green DURATION follows demand — a green is held while its queue is
    still discharging and ends when the queue clears (gap-out), at max
    green, or when the fairness (starvation) rule names another approach;
  * phase ORDER follows demand — the next green goes to the approach with
    the highest priority index; empty approaches are skipped.
A green is never cut while its queue is still discharging just because
another approach scores higher: every switch costs yellow + all-red +
start-up time, and evaluation showed that this rule made the controller
worse than fixed time under balanced heavy demand (docs/ALGORITHMS.md §3).

Emergency pre-emption (simulated): an operator can request priority for
one approach; the current green ends safely (after at least
`preempt_min_green_s`, always via yellow and all-red) and the requested
approach is held green for the requested time.

Every tick asserts that no two conflicting approaches are green at the
same time (split phasing by default: every approach conflicts with
every other).
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field, asdict
from typing import Literal

from intelligence.priority.engine import LABEL, PriorityDecision, PriorityEngine
from intelligence.types import APPROACHES, ApproachMeasurement, CongestionResult, SignalColour

Stage = Literal["green", "yellow", "all_red"]


@dataclass
class SignalConfig:
    min_green_s: float = 10.0
    max_green_s: float = 45.0
    yellow_s: float = 3.0
    clearance_s: float = 2.0  # all-red
    preempt_min_green_s: float = 5.0  # shortest green allowed before an emergency pre-emption
    # Pairs allowed to be green together. Empty = strict split phasing.
    compatible_pairs: list[tuple[str, str]] = field(default_factory=list)

    def validate(self) -> None:
        if self.min_green_s <= 0 or self.yellow_s <= 0 or self.clearance_s < 0:
            raise ValueError("Timings must be positive (clearance may be 0)")
        if self.max_green_s < self.min_green_s:
            raise ValueError("max_green_s must be >= min_green_s")


@dataclass
class SignalEvent:
    ts: float
    kind: str  # "phase_start" | "yellow" | "all_red" | "hold"
    approach: str | None
    reason: str


class ConflictError(RuntimeError):
    pass


class SignalSimulator:
    def __init__(self, priority: PriorityEngine, config: SignalConfig | None = None,
                 approaches: tuple[str, ...] = APPROACHES, initial: str = "north") -> None:
        self.config = config or SignalConfig()
        self.config.validate()
        self.priority = priority
        self.approaches = approaches
        self.current: str = initial
        self.stage: Stage = "green"
        self.stage_elapsed = 0.0
        self.green_elapsed = 0.0
        self.target: str | None = None
        self.pending_reason = ""
        self.time_since_served = {a: 0.0 for a in approaches}
        self.served_seconds = {a: 0.0 for a in approaches}  # cumulative green time
        self.events: list[SignalEvent] = [SignalEvent(time.time(), "phase_start", initial, "Initial phase")]
        self.last_decision: PriorityDecision | None = None
        self.preempt: dict | None = None  # {"approach", "hold_s", "reason", "active_since"}

    # ------------------------------------------------------------------ safety
    def _conflicts(self, a: str, b: str) -> bool:
        pairs = {tuple(sorted(p)) for p in self.config.compatible_pairs}
        return tuple(sorted((a, b))) not in pairs

    def colours(self) -> dict[str, SignalColour]:
        out = {a: SignalColour.RED for a in self.approaches}
        if self.stage == "green":
            out[self.current] = SignalColour.GREEN
        elif self.stage == "yellow":
            out[self.current] = SignalColour.YELLOW
        return out

    def assert_safe(self) -> None:
        greens = [a for a, c in self.colours().items() if c != SignalColour.RED]
        for a, b in itertools.combinations(greens, 2):
            if self._conflicts(a, b):
                raise ConflictError(f"Conflicting approaches {a} and {b} both non-red")

    # ------------------------------------------------------------------ pre-emption
    def request_preemption(self, approach: str, hold_s: float = 20.0, reason: str = "Emergency vehicle") -> None:
        if approach not in self.approaches:
            raise ValueError("unknown approach")
        self.preempt = {"approach": approach, "hold_s": float(hold_s), "reason": reason, "active_since": None,
                        "requested_at": time.time()}
        self._log("preempt", approach, f"{reason}: pre-emption requested for {LABEL[approach]} ({hold_s:.0f}s)")
        if self.stage == "green" and self.current == approach:
            self.preempt["active_since"] = self.green_elapsed

    def cancel_preemption(self) -> None:
        if self.preempt:
            self._log("preempt", self.preempt["approach"], "Pre-emption cancelled")
        self.preempt = None

    # ------------------------------------------------------------------ tick
    def _log(self, kind: str, approach: str | None, reason: str) -> None:
        self.events.append(SignalEvent(time.time(), kind, approach, reason))
        del self.events[:-200]

    def tick(self, dt: float, measurements: dict[str, ApproachMeasurement],
             congestion: dict[str, CongestionResult]) -> None:
        c = self.config
        self.stage_elapsed += dt
        for a in self.approaches:
            if self.stage == "green" and a == self.current:
                self.time_since_served[a] = 0.0
                self.served_seconds[a] += dt
            else:
                self.time_since_served[a] += dt

        # Always compute an overall ranking for the dashboard.
        self.last_decision = self.priority.decide(measurements, congestion, self.time_since_served)

        if self.stage == "green":
            self.green_elapsed = self.stage_elapsed
            self._evaluate_green(measurements, congestion)
        elif self.stage == "yellow" and self.stage_elapsed >= c.yellow_s:
            self.stage, self.stage_elapsed = "all_red", 0.0
            self._log("all_red", None, f"All-red clearance {c.clearance_s:.0f}s")
        elif self.stage == "all_red" and self.stage_elapsed >= c.clearance_s:
            self.current, self.stage, self.stage_elapsed = self.target or self.current, "green", 0.0
            self.green_elapsed = 0.0
            self._log("phase_start", self.current, self.pending_reason)
            self.target = None
            if self.preempt and self.preempt["approach"] == self.current:
                self.preempt["active_since"] = 0.0
        self.assert_safe()

    def _evaluate_green(self, ms: dict[str, ApproachMeasurement], cg: dict[str, CongestionResult]) -> None:
        c = self.config
        cur = self.current
        # --- emergency pre-emption has precedence (still via yellow + all-red)
        if self.preempt:
            p = self.preempt
            if p["approach"] == cur:
                if p["active_since"] is None:
                    p["active_since"] = self.green_elapsed
                if self.green_elapsed - p["active_since"] < p["hold_s"]:
                    return  # hold green for the emergency vehicle
                self._log("preempt", cur, f"Pre-emption for {LABEL[cur]} completed")
                self.preempt = None
            elif self.green_elapsed >= min(c.preempt_min_green_s, c.min_green_s):
                self._begin_transition(p["approach"], f"{p['reason']}: emergency pre-emption — {LABEL[p['approach']]} served next.")
                return
            else:
                return
        if self.green_elapsed < c.min_green_s:
            return
        alt = self.priority.decide(ms, cg, self.time_since_served, exclude=cur)
        if alt.recommended is None:
            return  # nobody else needs service: rest in green
        cur_m = ms[cur]
        if self.green_elapsed >= c.max_green_s:
            why = f"{LABEL[cur]} reached max green ({c.max_green_s:.0f}s). " + alt.reason
        elif cur_m.queue_count == 0 and not cur_m.pedestrian_request:
            why = f"{LABEL[cur]} queue cleared after {self.green_elapsed:.0f}s. " + alt.reason
        elif alt.rule == "starvation":
            why = alt.reason
        else:
            return  # queue still discharging: keep green (avoids wasting yellow/all-red/start-up time)
        self._begin_transition(alt.recommended, why)

    def _begin_transition(self, target: str, reason: str) -> None:
        self.target = target
        self.pending_reason = reason
        self.stage, self.stage_elapsed = "yellow", 0.0
        self._log("yellow", self.current, f"Ending {LABEL[self.current]} green → {LABEL[target]}")

    # ------------------------------------------------------------------ view
    def snapshot(self) -> dict:
        c = self.config
        remaining_min = max(0.0, c.min_green_s - self.green_elapsed) if self.stage == "green" else 0.0
        remaining_max = max(0.0, c.max_green_s - self.green_elapsed) if self.stage == "green" else 0.0
        return {
            "current": self.current,
            "stage": self.stage,
            "stage_elapsed_s": round(self.stage_elapsed, 1),
            "target": self.target,
            "remaining_min_green_s": round(remaining_min, 1),
            "remaining_max_green_s": round(remaining_max, 1),
            "colours": {a: col.value for a, col in self.colours().items()},
            "time_since_served_s": {a: round(v, 1) for a, v in self.time_since_served.items()},
            "served_seconds": {a: round(v, 1) for a, v in self.served_seconds.items()},
            "config": asdict(c),
            "preemption": dict(self.preempt) if self.preempt else None,
            "events": [asdict(e) for e in self.events[-20:]][::-1],
        }

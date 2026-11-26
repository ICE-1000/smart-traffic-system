"""Reproducible adaptive-vs-fixed comparison over standard demand patterns.

    python scripts/evaluate_controller.py            # 5 seeds x 1 h per pattern
    python scripts/evaluate_controller.py --seeds 10 --minutes 120

Uses the same ComparisonEngine as the dashboard (Evaluation page),
with default timings (min/max green 10/45 s, yellow 3 s, all-red 2 s;
saturation 0.5 veh/s). Two fixed-time baselines, both on a 120 s cycle:
  * equal split   — 25 s green per approach (a schedule that ignores demand,
                    the situation described in the proposal's problem statement);
  * tuned split   — the same 100 s of green shared in proportion to each
                    approach's demand (5 s minimum each, remaining 80 s in
                    proportion to demand), i.e. a well-timed fixed plan.
Demand patterns are synthetic test cases, not Lusaka measurements.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence.congestion.engine import CongestionEngine  # noqa: E402
from intelligence.evaluation.comparison import ComparisonEngine, FixedTimePlan  # noqa: E402
from intelligence.priority.engine import PriorityConfig  # noqa: E402
from intelligence.simulation.signal import SignalConfig  # noqa: E402
from intelligence.types import APPROACHES, ApproachMeasurement  # noqa: E402

PATTERNS = {
    "Dominant approach (N 14 / S 3 / E 1 / W 0)": {"north": 14, "south": 3, "east": 1, "west": 0},
    "Unbalanced (N 9 / S 6 / E 2.5 / W 0.8)": {"north": 9, "south": 6, "east": 2.5, "west": 0.8},
    "Mixed (N 8 / S 2 / E 5 / W 3)": {"north": 8, "south": 2, "east": 5, "west": 3},
    "Balanced moderate (4 each)": {a: 4 for a in APPROACHES},
    "Balanced heavy (5 each)": {a: 5 for a in APPROACHES},
    "Balanced at capacity (6 each)": {a: 6 for a in APPROACHES},
    "Light (2/2/1/1)": {"north": 2, "south": 2, "east": 1, "west": 1},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--minutes", type=int, default=60)
    args = ap.parse_args()
    print(f"{'Demand pattern (veh/min per approach)':46} {'Adaptive':>9} {'Equal':>7} {'vs equal':>9} {'Tuned':>7} {'vs tuned':>9}")
    for name, rates in PATTERNS.items():
        ad, fd, td = [], [], []
        total = sum(rates.values()) or 1
        # 5 s minimum each, the remaining 80 s shared in proportion to demand -> 100 s green, 120 s cycle
        tuned = FixedTimePlan(green_s={a: round(5.0 + 80.0 * rates[a] / total, 1) for a in APPROACHES})
        for seed in range(args.seeds):
            ms = {a: ApproachMeasurement(a, 0, 0, 0, 0, rates[a], 0, 0, 10, 2, 8, False, "demo") for a in APPROACHES}
            ce = ComparisonEngine(PriorityConfig(), SignalConfig(), CongestionEngine(), seed=seed)
            ct = ComparisonEngine(PriorityConfig(), SignalConfig(), CongestionEngine(), plan=tuned, seed=seed)
            for _ in range(args.minutes * 60):
                ce.step(1, ms)
                ct.step(1, ms)
            s, t = ce.summary(), ct.summary()
            ad.append(s["adaptive"]["mean_delay_s"])
            fd.append(s["fixed"]["mean_delay_s"])
            td.append(t["fixed"]["mean_delay_s"])
        a, f, tt = statistics.mean(ad), statistics.mean(fd), statistics.mean(td)
        print(f"{name:46} {a:>8.1f}s {f:>6.1f}s {(f - a) / f * 100:>+8.1f}% {tt:>6.1f}s {(tt - a) / tt * 100:>+8.1f}%")
    print("\nMean delay per vehicle; positive % = adaptive lower. Mean over seeds; synthetic demand.")


if __name__ == "__main__":
    main()

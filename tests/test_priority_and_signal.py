import itertools

from backend.app.services.demo_source import DemoTrafficSource
from intelligence.congestion.engine import CongestionEngine
from intelligence.priority.engine import PriorityConfig, PriorityEngine
from intelligence.simulation.signal import SignalConfig, SignalSimulator
from intelligence.types import APPROACHES, ApproachMeasurement


def meas(q: dict[str, int], wait: dict[str, float] | None = None, ped: set[str] = frozenset()):
    wait = wait or {}
    return {
        a: ApproachMeasurement(a, q.get(a, 0), q.get(a, 0) * 7.0, wait.get(a, 0.0), wait.get(a, 0.0),
                               q.get(a, 0) / 2, 0.0, 0.0, q.get(a, 0), 0, q.get(a, 0), a in ped)
        for a in APPROACHES
    }


def decide(q, tss=None, wait=None, ped=frozenset(), cfg=None):
    ms = meas(q, wait, ped)
    cg = CongestionEngine().evaluate_all(list(ms.values()))
    return PriorityEngine(cfg).decide(ms, cg, tss or {a: 0.0 for a in APPROACHES})


def test_highest_demand_wins_spec_example():
    d = decide({"north": 25, "south": 18, "east": 2, "west": 0})
    assert d.recommended == "north"
    assert d.next_recommended == "south"
    assert d.rule == "demand"
    assert "North" in d.reason and "25 queued" in d.reason


def test_empty_approach_skipped():
    d = decide({"north": 0, "south": 3, "east": 0, "west": 0})
    west = next(r for r in d.ranking if r.approach == "west")
    assert not west.eligible
    assert d.recommended == "south"


def test_pedestrian_request_makes_empty_approach_eligible():
    d = decide({"north": 0, "south": 0, "east": 0, "west": 0}, ped={"west"})
    assert d.recommended == "west"


def test_starvation_overrides_demand():
    d = decide({"north": 30, "east": 2}, tss={"north": 5, "south": 0, "east": 120, "west": 0})
    assert d.recommended == "east"
    assert d.rule == "starvation"


def test_empty_approach_served_after_max_skip():
    cfg = PriorityConfig(max_skip_s=60)
    d = decide({}, tss={"north": 0, "south": 0, "east": 0, "west": 70}, cfg=cfg)
    assert d.recommended == "west"
    assert d.rule == "max_skip"


def run_sim(seconds=1800, cfg=None, rates=None):
    src = DemoTrafficSource(seed=3, rates=rates)
    ce = CongestionEngine()
    sim = SignalSimulator(PriorityEngine(), cfg)
    greens_seen = []
    for _ in range(seconds):
        ms = src.step(1, {a: c.value for a, c in sim.colours().items()})
        sim.tick(1, ms, ce.evaluate_all(list(ms.values())))  # tick() asserts safety itself
        greens_seen.append(sum(1 for c in sim.colours().values() if c.value != "red"))
    return sim, greens_seen


def test_never_more_than_one_non_red_with_split_phasing():
    _, greens = run_sim()
    assert max(greens) <= 1


def test_yellow_always_followed_by_all_red():
    sim, _ = run_sim(rates={"north": 20, "south": 15, "east": 8, "west": 5})
    kinds = [e.kind for e in sim.events]
    for i, k in enumerate(kinds[:-1]):
        if k == "yellow":
            assert kinds[i + 1] == "all_red"
        if k == "all_red":
            assert kinds[i + 1] == "phase_start"


def test_no_approach_monopolises_green():
    sim, _ = run_sim(rates={"north": 25, "south": 2, "east": 2, "west": 2})
    served = sim.served_seconds
    assert all(served[a] > 0 for a in APPROACHES)
    assert max(sim.time_since_served.values()) < 300


def test_green_duration_bounds_via_counters():
    cfg = SignalConfig(min_green_s=10, max_green_s=25)
    src = DemoTrafficSource(seed=5, rates={"north": 20, "south": 20, "east": 20, "west": 20})
    ce = CongestionEngine()
    sim = SignalSimulator(PriorityEngine(), cfg)
    run, durations = 0, []
    prev = None
    for _ in range(1200):
        ms = src.step(1, {a: c.value for a, c in sim.colours().items()})
        sim.tick(1, ms, ce.evaluate_all(list(ms.values())))
        g = next((a for a, c in sim.colours().items() if c.value == "green"), None)
        if g and g == prev:
            run += 1
        elif prev and run:
            durations.append(run)
            run = 0
        if g and g != prev:
            run = 1
        prev = g
    assert durations, "expected phase changes"
    assert all(cfg.min_green_s <= d <= cfg.max_green_s + 1 for d in durations[1:]), durations


def test_no_data_approach_gets_fixed_time_fallback_only():
    ms = meas({"north": 5})
    ms["west"] = ApproachMeasurement.no_data("west")
    cg = CongestionEngine().evaluate_all(list(ms.values()))
    eng = PriorityEngine()
    d = eng.decide(ms, cg, {"north": 0, "south": 0, "east": 0, "west": 30})
    assert d.recommended == "north"
    assert not next(r for r in d.ranking if r.approach == "west").eligible
    d = eng.decide(ms, cg, {"north": 0, "south": 0, "east": 0, "west": 95})
    assert next(r for r in d.ranking if r.approach == "west").eligible
    ms_only_west = {a: ApproachMeasurement.no_data(a) for a in APPROACHES}
    d = eng.decide(ms_only_west, CongestionEngine().evaluate_all(list(ms_only_west.values())),
                   {"north": 0, "south": 10, "east": 20, "west": 95})
    assert d.recommended == "west" and d.rule == "no_data"

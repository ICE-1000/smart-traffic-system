"""Evaluation (RQ2), Congestion Index, moving-car method, incidents, pre-emption."""
import pytest

from intelligence.congestion.engine import CongestionEngine
from intelligence.evaluation.comparison import ComparisonEngine, FixedTimeController, FixedTimePlan
from intelligence.evaluation.indices import DelayWindow, IndexConfig, congestion_index, free_flow_time_s
from intelligence.evaluation.surveys import count_accuracy, moving_car
from intelligence.incidents.detector import IncidentConfig, IncidentDetector
from intelligence.priority.engine import PriorityConfig, PriorityEngine
from intelligence.simulation.signal import SignalConfig, SignalSimulator
from intelligence.types import APPROACHES, ApproachMeasurement, SignalColour


def rates_ms(rates: dict[str, float]):
    return {a: ApproachMeasurement(a, 0, 0, 0, 0, rates.get(a, 0), 0, 0, 10, 2, 8, False, "demo") for a in APPROACHES}


def run(rates, seconds=3600, seed=3):
    ce = ComparisonEngine(PriorityConfig(), SignalConfig(), CongestionEngine(), seed=seed)
    ms = rates_ms(rates)
    for _ in range(seconds):
        ce.step(1, ms)
    return ce.summary()


# ------------------------------------------------------------ RQ2: adaptive vs fixed
def test_both_plans_receive_identical_arrivals():
    s = run({"north": 9, "south": 6, "east": 2.5, "west": 0.8}, seconds=900)
    assert s["adaptive"]["arrived"] == s["fixed"]["arrived"] > 0


def test_adaptive_beats_fixed_with_unbalanced_demand():
    s = run({"north": 14, "south": 3, "east": 1, "west": 0})
    assert s["adaptive"]["mean_delay_s"] < s["fixed"]["mean_delay_s"] * 0.5
    assert s["improvement_pct"]["vehicle_hours_delay"] > 0
    assert s["adaptive"]["throughput_vph"] >= s["fixed"]["throughput_vph"]


def test_adaptive_not_worse_than_fixed_below_capacity_balanced():
    """Regression test for the controller fix: cutting greens while a queue still
    discharges made the adaptive plan far worse than fixed time under balanced demand."""
    s = run({a: 5 for a in APPROACHES})
    assert s["adaptive"]["mean_delay_s"] <= s["fixed"]["mean_delay_s"]


def test_fixed_time_controller_cycle():
    cfg = SignalConfig(yellow_s=3, clearance_s=2)
    plan = FixedTimePlan(order=["north", "east", "south", "west"], green_s={"north": 10, "east": 5, "south": 5, "west": 5})
    ctl = FixedTimeController(plan, cfg)
    greens = []
    for _ in range(plan.cycle_s(3, 2) * 2):
        cols = ctl.colours()
        g = [a for a, c in cols.items() if c == SignalColour.GREEN]
        assert len([c for c in cols.values() if c != SignalColour.RED]) <= 1
        greens.append(g[0] if g else None)
        ctl.tick(1)
    assert greens[:10] == ["north"] * 10
    assert plan.cycle_s(3, 2) == 45
    assert greens.count("north") == 20 and greens.count("east") == 10


def test_fixed_plan_validation():
    with pytest.raises(ValueError):
        FixedTimePlan(order=["north", "north", "south", "west"]).validate()
    with pytest.raises(ValueError):
        FixedTimePlan(green_s={a: 2 for a in APPROACHES}).validate()


def test_total_delay_counts_vehicles_still_queued():
    s = run({"north": 14, "south": 3, "east": 1, "west": 0}, seconds=1800)
    f = s["fixed"]
    departed_delay_h = f["mean_delay_s"] * f["departed"] / 3600
    assert f["queued_now"] > 0 and f["vehicle_hours_delay"] > departed_delay_h


# ------------------------------------------------------------ Congestion Index
def test_congestion_index_definition():
    # 100 m at 36 km/h = 10 s free-flow; 15 s delay -> actual 25 s -> CI 1.5, TTI 2.5
    assert free_flow_time_s(100, 36) == pytest.approx(10)
    assert congestion_index(15, 100, 36) == pytest.approx(1.5)
    w = DelayWindow()
    w.add(0, [10, 20, 15], "vision")
    r = w.result(1, 100, IndexConfig(free_flow_kmh=36))
    assert r["ci"] == 1.5 and r["tti"] == 2.5 and r["samples"] == 3


def test_delay_window_never_mixes_sources_and_expires():
    w = DelayWindow()
    w.add(0, [100, 100, 100], "demo")
    w.add(1, [10], "vision")
    assert len(w.samples) == 1
    cfg = IndexConfig(window_s=60)
    assert w.result(1000, 100, cfg)["samples"] == 0
    assert w.result(1000, 100, cfg)["ci"] is None


# ------------------------------------------------------------ moving-car method
def test_moving_car_textbook_consistency():
    # stream 600 veh/h at 30 km/h over 1 km -> t̄ = 2 min; observer: tw 3, ta 1.5
    r = moving_car(1.0, tw_min=3, ta_min=1.5, x=35, y=10, free_flow_kmh=40)
    assert r["flow_vph"] == 600.0
    assert r["mean_journey_time_min"] == 2.0
    assert r["space_mean_speed_kmh"] == 30.0
    assert r["ci"] == pytest.approx(0.33, abs=0.005)


def test_moving_car_rejects_impossible_input():
    with pytest.raises(ValueError):
        moving_car(1, 1, 1, 0, 0, None)
    with pytest.raises(ValueError):
        moving_car(1, 1, 1, 1, 50, None)  # t̄ would be negative


def test_count_accuracy():
    assert count_accuracy(20, 19) == {"error_pct": -5.0, "accuracy_pct": 95.0}
    assert count_accuracy(0, 5)["accuracy_pct"] is None


# ------------------------------------------------------------ incidents
def _ms(q=0, mw=0.0, ql=0.0, source="vision"):
    return {a: ApproachMeasurement(a, q if a == "north" else 0, ql if a == "north" else 0, 0, mw if a == "north" else 0,
                                   0, 0, 0, q, 0, q, False, source) for a in APPROACHES}


def test_blocked_discharge_opens_and_clears_with_hysteresis():
    d = IncidentDetector(IncidentConfig(confirm_s=5, clear_s=20))
    for i in range(30):
        d.update(_ms(q=5), {"north": "green"}, {"north": 20 + i}, {"north": None}, [], now=1000 + i)
    assert "blocked_discharge:north" in d.active
    for i in range(30, 45):
        d.update(_ms(q=0), {"north": "red"}, {"north": 0}, {"north": 1000 + i}, [], now=1000 + i)
    assert "blocked_discharge:north" in d.active  # not cleared before clear_s
    for i in range(45, 60):
        d.update(_ms(q=0), {"north": "red"}, {"north": 0}, {"north": 1000 + i}, [], now=1000 + i)
    assert not d.active


def test_no_incidents_from_missing_data_and_camera_failure_timing():
    d = IncidentDetector(IncidentConfig(camera_offline_s=30, confirm_s=5))
    cam = [{"id": "C", "name": "c", "approach": "south", "enabled": True, "has_stream_url": True, "status": "offline", "detail": "x"}]
    for i in range(29):
        d.update(_ms(q=9, mw=999, ql=999, source="none"), {"north": "green"}, {"north": 99}, {"north": None}, cam, now=i)
    assert not d.active  # no traffic incidents without data; camera not yet 30 s
    d.update(_ms(source="none"), {}, {}, {}, cam, now=31)
    assert "camera_failure:C" in d.active


def test_stalled_vehicle_and_spillback():
    d = IncidentDetector(IncidentConfig(confirm_s=1, stall_s=240, spillback_limit_m=100))
    for i in range(5):
        d.update(_ms(q=3, mw=300, ql=150), {"north": "red"}, {}, {"north": None}, [], now=i)
    assert {"stalled_vehicle:north", "spillback:north"} <= set(d.active)


# ------------------------------------------------------------ emergency pre-emption
def test_preemption_is_safe_and_holds_green():
    from intelligence.congestion.engine import CongestionEngine as CE

    sim = SignalSimulator(PriorityEngine(), SignalConfig(min_green_s=10, preempt_min_green_s=5), initial="north")
    ms = rates_ms({})
    for a in APPROACHES:
        ms[a].queue_count = 3
    cg = CE().evaluate_all(list(ms.values()))
    sim.request_preemption("west", hold_s=15)
    stages = []
    for _ in range(60):
        sim.tick(1, ms, cg)
        stages.append((sim.current, sim.stage))
        assert sum(1 for c in sim.colours().values() if c != SignalColour.RED) <= 1
    first_west = stages.index(("west", "green"))
    seq = [st for _, st in stages[:first_west]]
    assert "yellow" in seq and "all_red" in seq  # always via yellow and all-red
    assert first_west <= 5 + 3 + 2 + 1
    held = [s for s in stages[first_west:first_west + 15]]
    assert all(s == ("west", "green") for s in held)
    assert sim.preempt is None  # completed afterwards


def test_iou_tracker_keeps_ids():
    from vision.tracking.iou_tracker import IouTracker

    t = IouTracker(min_hits=2)
    box = (10, 10, 50, 50)
    assert t.update([(box, "vehicle")]) == [None]  # unconfirmed on first sight
    ids1 = t.update([((12, 10, 52, 50), "vehicle")])
    ids2 = t.update([((14, 10, 54, 50), "vehicle"), ((200, 200, 240, 240), "vehicle")])
    assert ids1[0] is not None and ids2[0] == ids1[0] and ids2[1] is None

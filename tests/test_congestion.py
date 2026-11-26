import pytest

from intelligence.congestion.engine import CongestionConfig, CongestionEngine
from intelligence.types import ApproachMeasurement


def m(approach="north", q=0, qlen=0.0, wait=0.0, arr=0.0, dep=0.0):
    return ApproachMeasurement(approach, q, qlen, wait, wait, arr, dep, 0.0, q, 0, q)


def test_empty_approach_scores_zero_and_free():
    r = CongestionEngine().evaluate(m())
    assert r.score == 0
    assert r.category == "free"


def test_saturated_approach_scores_100_and_critical():
    r = CongestionEngine().evaluate(m(q=60, qlen=400, wait=500, arr=60, dep=0))
    assert r.score == 100
    assert r.category == "critical"


def test_score_is_not_count_alone():
    eng = CongestionEngine()
    same_count_short_wait = eng.evaluate(m(q=10, qlen=70, wait=10, arr=5, dep=5))
    same_count_long_wait = eng.evaluate(m(q=10, qlen=70, wait=110, arr=5, dep=5))
    assert same_count_long_wait.score > same_count_short_wait.score


def test_departures_exceeding_arrivals_do_not_reduce_below_zero():
    r = CongestionEngine().evaluate(m(q=5, arr=2, dep=20))
    assert r.components["net_growth"] == 0


def test_contributions_sum_to_score():
    r = CongestionEngine().evaluate(m(q=12, qlen=90, wait=45, arr=12, dep=6))
    assert abs(sum(r.contributions.values()) - r.score) < 0.11


def test_invalid_weights_rejected():
    with pytest.raises(ValueError):
        CongestionEngine(CongestionConfig(weights={"queue_count": 0.5, "wait_time": 0.6, "queue_length": 0,
                                                   "arrival_rate": 0, "net_growth": 0}))

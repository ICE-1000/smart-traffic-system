"""Vision measurement logic with synthetic detections (no model needed)."""
import pytest
from pydantic import ValidationError

from vision.detection.detector import Detection
from vision.regions.config import RegionConfig, point_in_polygon, side_of_line
from vision.tracking.state import ApproachTracker

# Road runs top→bottom; queue area is the lower half; stop line at y = 0.9
REGIONS = RegionConfig(
    approach=[(0.2, 0.0), (0.8, 0.0), (0.8, 0.9), (0.2, 0.9)],
    queue=[(0.2, 0.4), (0.8, 0.4), (0.8, 0.9), (0.2, 0.9)],
    stop_line=[(0.2, 0.9), (0.8, 0.9)],
    queue_length_m=50,
)


def det(tid, x, y, cls="car", conf=0.8, w=0.08, h=0.08):
    """Detection whose bottom-centre anchor is (x, y)."""
    return Detection(tid, cls, conf, (x - w / 2, y - h, x + w / 2, y))


def test_geometry_helpers():
    sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert point_in_polygon(0.5, 0.5, sq)
    assert not point_in_polygon(1.5, 0.5, sq)
    line = [(0, 0.5), (1, 0.5)]
    assert side_of_line(0.5, 0.2, line) * side_of_line(0.5, 0.8, line) < 0


def test_region_validation():
    with pytest.raises(ValidationError):
        RegionConfig(queue=[(0, 0), (1, 1)])
    with pytest.raises(ValidationError):
        RegionConfig(stop_line=[(0, 0)])
    assert RegionConfig(queue=[(-1, 0), (2, 0), (0.5, 3)]).queue[1] == (1.0, 0.0)  # clamped


def test_vehicle_counted_once_and_queues_then_departs():
    tr = ApproachTracker("north", REGIONS)
    t = 0.0
    # approaching: moving down the road
    for y in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
        tr.update([det(1, 0.5, y)], t)
        t += 0.5
    # stopped at y = 0.85 for 20 s
    for _ in range(40):
        tr.update([det(1, 0.5, 0.85)], t)
        t += 0.5
    m = tr.measure(t)
    assert len(tr.arrivals) == 1  # one vehicle, many frames → one arrival
    assert m.queue_count == 1
    assert 18 <= m.avg_wait_s <= 21
    assert m.queue_length_m == pytest.approx(5.0, abs=1.5)  # 0.05 of the 0.5-long axis → 10 % of 50 m
    # crosses the stop line
    for y in (0.88, 0.93, 0.98):
        tr.update([det(1, 0.5, y)], t)
        t += 0.5
    m = tr.measure(t)
    assert len(tr.departures) == 1
    assert m.queue_count == 0
    assert tr.tracks[1].wait_s and tr.tracks[1].wait_s >= 18


def test_pedestrians_are_not_vehicles():
    tr = ApproachTracker("north", REGIONS)
    for i in range(10):
        tr.update([det(7, 0.5, 0.8, cls="person"), det(8, 0.4, 0.8, cls="person")], i * 0.5)
    m = tr.measure(5.0)
    assert m.queue_count == 0 and m.vehicles_in_view == 0
    assert m.pedestrians_in_view == 2
    assert len(tr.arrivals) == 0


def test_short_lived_flicker_not_counted_as_arrival():
    tr = ApproachTracker("north", REGIONS)
    tr.update([det(5, 0.5, 0.5)], 0.0)
    tr.update([det(5, 0.5, 0.5)], 0.2)  # only 2 sightings (< min_hits)
    tr.update([], 5.0)  # expired
    assert len(tr.arrivals) == 0


def test_class_majority_vote():
    tr = ApproachTracker("north", REGIONS)
    seq = ["bus", "bus", "car", "bus", "truck", "bus"]
    for i, c in enumerate(seq):
        tr.update([det(3, 0.5, 0.3 + i * 0.05, cls=c)], i * 0.5)
    assert tr.tracks[3].cls == "bus"


def test_heavy_vehicle_counts_and_fallback_queue_length():
    regions = RegionConfig(queue=REGIONS.queue, approach=REGIONS.approach)  # no stop line / length
    tr = ApproachTracker("east", regions)
    for i in range(12):
        tr.update([det(1, 0.4, 0.8, cls="bus"), det(2, 0.6, 0.8, cls="car")], i * 0.5)
    m = tr.measure(6.0)
    assert m.queue_count == 2
    assert m.heavy_vehicles == 1 and m.light_vehicles == 1
    assert m.queue_length_m == 21.0  # bus 14 m + car 7 m


def test_departure_without_stop_line_when_track_lost():
    regions = RegionConfig(queue=REGIONS.queue, approach=REGIONS.approach)
    tr = ApproachTracker("east", regions)
    for i in range(6):
        tr.update([det(1, 0.5, 0.2 + i * 0.1)], i * 0.5)
    tr.update([], 10.0)
    assert len(tr.departures) == 1

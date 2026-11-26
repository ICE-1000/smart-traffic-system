"""Field-survey calculations: moving-car method and manual-count validation.

Moving-car (moving observer) method — Wardrop & Charlesworth (1954).
A test car drives the section with the stream (journey time tw) and
against it (journey time ta). Observed:
    x = vehicles met travelling in the stream direction while the car goes AGAINST it
    y = vehicles that overtook the car minus vehicles the car overtook, while going WITH it
Then
    flow                q  = (x + y) / (ta + tw)
    mean journey time   t̄  = tw - y / q
    space-mean speed    v  = distance / t̄
    CI                     = (t̄ - t_free) / t_free,  t_free = distance / free-flow speed
Times in minutes, flow converted to veh/h. Several run pairs should be
averaged for a reliable estimate.
"""
from __future__ import annotations


def moving_car(distance_km: float, tw_min: float, ta_min: float, x: float, y: float,
               free_flow_kmh: float | None) -> dict:
    if distance_km <= 0 or tw_min <= 0 or ta_min <= 0:
        raise ValueError("distance and journey times must be positive")
    if x + y <= 0:
        raise ValueError("x + y must be positive (no vehicles observed in the stream)")
    q_per_min = (x + y) / (ta_min + tw_min)
    t_mean_min = tw_min - y / q_per_min
    if t_mean_min <= 0:
        raise ValueError("computed mean journey time is not positive — check x, y and the journey times")
    speed_kmh = distance_km / (t_mean_min / 60.0)
    out = {
        "flow_vph": round(q_per_min * 60.0, 1),
        "mean_journey_time_min": round(t_mean_min, 3),
        "space_mean_speed_kmh": round(speed_kmh, 1),
        "ci": None,
        "tti": None,
    }
    if free_flow_kmh and free_flow_kmh > 0:
        t_free = distance_km / free_flow_kmh * 60.0
        ci = (t_mean_min - t_free) / t_free
        out.update(ci=round(ci, 2), tti=round(1 + ci, 2), free_flow_time_min=round(t_free, 3))
    return out


def count_accuracy(manual: int, system: int) -> dict:
    """Error of the automatic count against the manual (ground-truth) count."""
    if manual <= 0:
        return {"error_pct": None, "accuracy_pct": None}
    err = (system - manual) / manual * 100.0
    return {"error_pct": round(err, 1), "accuracy_pct": round(max(0.0, 100.0 - abs(err)), 1)}

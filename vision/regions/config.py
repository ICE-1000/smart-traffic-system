"""Per-camera virtual regions.

All coordinates are normalised (0..1) relative to the frame, so they stay
valid if the processing resolution changes. Each phone is mounted at a
different angle, so regions are configured per camera in the dashboard.

approach   polygon covering the road approaching the junction (arrivals are
           counted when a vehicle is first seen inside it)
queue      polygon where waiting vehicles stand (normally the last ~30-80 m
           before the stop line)
stop_line  two points; crossing it from the queue side counts a departure
queue_length_m  real-world length of the queue polygon measured along the
           road (optional). With it, queue length is estimated geometrically;
           without it, from vehicle-class lengths.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

Point = tuple[float, float]


class RegionConfig(BaseModel):
    approach: list[Point] = Field(default_factory=lambda: [(0, 0), (1, 0), (1, 1), (0, 1)])
    queue: list[Point] = Field(default_factory=lambda: [(0, 0.35), (1, 0.35), (1, 1), (0, 1)])
    stop_line: list[Point] | None = None
    queue_length_m: float | None = Field(None, gt=0, le=1000)

    @field_validator("approach", "queue")
    @classmethod
    def _poly(cls, v: list[Point]) -> list[Point]:
        if len(v) < 3:
            raise ValueError("A region polygon needs at least 3 points")
        return [_clamp_pt(p) for p in v]

    @field_validator("stop_line")
    @classmethod
    def _line(cls, v: list[Point] | None) -> list[Point] | None:
        if v is None:
            return None
        if len(v) != 2:
            raise ValueError("stop_line needs exactly 2 points")
        return [_clamp_pt(p) for p in v]


def _clamp_pt(p: Point) -> Point:
    return (min(1.0, max(0.0, float(p[0]))), min(1.0, max(0.0, float(p[1]))))


def point_in_polygon(x: float, y: float, poly: list[Point]) -> bool:
    """Ray casting."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def side_of_line(x: float, y: float, line: list[Point]) -> float:
    """>0 one side, <0 the other, 0 on the line."""
    (x1, y1), (x2, y2) = line
    return (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)


def centroid(poly: list[Point]) -> Point:
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))

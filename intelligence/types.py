"""Shared data types for the intelligence layer.

These types form the contract between the measurement producers
(demo source today, computer-vision pipeline from Phase 4/5) and the
congestion / priority / simulation engines. Engines never care where
measurements came from; the `source` field is carried through so the
dashboard can label simulated values honestly.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Literal

Approach = Literal["north", "south", "east", "west"]
APPROACHES: tuple[Approach, ...] = ("north", "south", "east", "west")

MeasurementSource = Literal["demo", "vision", "none", "model"]  # none = camera/vision unavailable; model = evaluation queue model


class SignalColour(str, Enum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


@dataclass
class ApproachMeasurement:
    """Raw traffic indicators for one approach at one instant."""

    approach: Approach
    queue_count: int  # vehicles waiting inside the queue region
    queue_length_m: float  # estimated physical queue length
    avg_wait_s: float  # mean waiting time of vehicles currently queued
    max_wait_s: float  # longest waiting vehicle
    arrival_rate_vpm: float  # vehicles per minute entering the approach
    departure_rate_vpm: float  # vehicles per minute leaving past the stop line
    moving_ratio: float  # 0..1 share of tracked vehicles that are moving
    vehicles_in_view: int
    heavy_vehicles: int  # buses + trucks
    light_vehicles: int  # cars + motorcycles
    pedestrian_request: bool = False
    source: MeasurementSource = "demo"
    pedestrians_in_view: int = 0

    @classmethod
    def no_data(cls, approach: "Approach") -> "ApproachMeasurement":
        return cls(approach, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, False, "none", 0)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CongestionResult:
    approach: Approach
    score: float  # 0..100
    category: Literal["free", "light", "moderate", "heavy", "critical"]
    components: dict[str, float] = field(default_factory=dict)  # normalised 0..1 inputs
    contributions: dict[str, float] = field(default_factory=dict)  # weighted points

    def to_dict(self) -> dict:
        return asdict(self)

"""ORM entities. Timestamps are UTC epoch seconds (float) everywhere for
consistency across SQLite and PostgreSQL."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class Intersection(Base):
    """A study site. The proposal's study nodes are seeded at start-up."""
    __tablename__ = "intersections"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80), default="Lusaka")
    node_type: Mapped[str] = mapped_column(String(16), default="signalised")  # signalised | roundabout | unconfirmed
    corridor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Camera(Base):
    __tablename__ = "cameras"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    intersection_id: Mapped[str] = mapped_column(ForeignKey("intersections.id"))
    name: Mapped[str] = mapped_column(String(80))
    approach: Mapped[str] = mapped_column(String(10))
    stream_url: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    processing_width: Mapped[int] = mapped_column(Integer, default=640)
    processing_fps: Mapped[float] = mapped_column(Float, default=5.0)
    regions: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # vision.regions.RegionConfig
    created_at: Mapped[float] = mapped_column(Float)


class TrafficMeasurement(Base):
    __tablename__ = "traffic_measurements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[float] = mapped_column(Float, index=True)
    intersection_id: Mapped[str] = mapped_column(String(32), index=True)
    approach: Mapped[str] = mapped_column(String(10), index=True)
    camera_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(10))  # demo | vision
    queue_count: Mapped[int] = mapped_column(Integer)
    queue_length_m: Mapped[float] = mapped_column(Float)
    avg_wait_s: Mapped[float] = mapped_column(Float)
    arrival_rate_vpm: Mapped[float] = mapped_column(Float)
    departure_rate_vpm: Mapped[float] = mapped_column(Float)
    vehicles_in_view: Mapped[int] = mapped_column(Integer)
    heavy_vehicles: Mapped[int] = mapped_column(Integer)
    signal_colour: Mapped[str] = mapped_column(String(8))
    mean_delay_s: Mapped[float | None] = mapped_column(Float, nullable=True)  # departed vehicles, last 5 min
    congestion_index: Mapped[float | None] = mapped_column(Float, nullable=True)  # (actual - free-flow) / free-flow


class CongestionMeasurement(Base):
    __tablename__ = "congestion_measurements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[float] = mapped_column(Float, index=True)
    intersection_id: Mapped[str] = mapped_column(String(32), index=True)
    approach: Mapped[str] = mapped_column(String(10), index=True)
    source: Mapped[str] = mapped_column(String(10))
    score: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(10))
    components: Mapped[dict] = mapped_column(JSON)


class VehicleDetection(Base):
    """One row per finished vehicle TRACK (not per frame, no raw video)."""
    __tablename__ = "vehicle_detections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[float] = mapped_column(Float, index=True)  # last seen
    first_seen: Mapped[float] = mapped_column(Float)
    camera_id: Mapped[str] = mapped_column(String(32), index=True)
    approach: Mapped[str] = mapped_column(String(10), index=True)
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    object_class: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)  # max over the track
    bbox: Mapped[list] = mapped_column(JSON)  # last [x1, y1, x2, y2], normalised 0..1
    entered_approach: Mapped[bool] = mapped_column(Boolean, default=False)
    departed: Mapped[bool] = mapped_column(Boolean, default=False)
    wait_s: Mapped[float | None] = mapped_column(Float, nullable=True)


class AppSetting(Base):
    """Operator-tuned configuration that must survive restarts (weights, timings, vision)."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[float] = mapped_column(Float)


class PriorityDecisionRecord(Base):
    __tablename__ = "priority_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[float] = mapped_column(Float, index=True)
    intersection_id: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(10))
    recommended: Mapped[str | None] = mapped_column(String(10), nullable=True)
    next_recommended: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rule: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    ranking: Mapped[list] = mapped_column(JSON)


class SignalSimulationEvent(Base):
    __tablename__ = "signal_simulation_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[float] = mapped_column(Float, index=True)
    intersection_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    approach: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reason: Mapped[str] = mapped_column(Text)


class SystemEvent(Base):
    __tablename__ = "system_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[float] = mapped_column(Float, index=True)
    level: Mapped[str] = mapped_column(String(8))  # info | warning | error
    component: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)


class IncidentRecord(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intersection_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    approach: Mapped[str | None] = mapped_column(String(10), nullable=True)
    severity: Mapped[str] = mapped_column(String(10))
    started: Mapped[float] = mapped_column(Float, index=True)
    ended: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(10), default="mixed")


class EvaluationSnapshot(Base):
    """Adaptive vs fixed-time comparison results, saved every minute."""
    __tablename__ = "evaluation_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[float] = mapped_column(Float, index=True)
    intersection_id: Mapped[str] = mapped_column(String(32), index=True)
    run_started: Mapped[float] = mapped_column(Float, index=True)
    elapsed_s: Mapped[float] = mapped_column(Float)
    sources: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict] = mapped_column(JSON)


class SurveyRun(Base):
    """Moving-car (moving observer) survey: one pair of runs, with and against the stream."""
    __tablename__ = "survey_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created: Mapped[float] = mapped_column(Float)
    intersection_id: Mapped[str] = mapped_column(String(32), index=True)
    corridor: Mapped[str] = mapped_column(String(120))
    direction: Mapped[str] = mapped_column(String(40))
    run_time: Mapped[float] = mapped_column(Float, index=True)  # when the runs were made (epoch s)
    distance_km: Mapped[float] = mapped_column(Float)
    tw_min: Mapped[float] = mapped_column(Float)  # journey time travelling WITH the stream
    ta_min: Mapped[float] = mapped_column(Float)  # journey time travelling AGAINST the stream
    x: Mapped[float] = mapped_column(Float)  # vehicles met in the stream while travelling against it
    y: Mapped[float] = mapped_column(Float)  # vehicles overtaking the observer minus vehicles overtaken (with stream)
    free_flow_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ValidationCount(Base):
    """Manual count / stopwatch session used to validate the camera + AI measurements."""
    __tablename__ = "validation_counts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created: Mapped[float] = mapped_column(Float)
    intersection_id: Mapped[str] = mapped_column(String(32), index=True)
    camera_id: Mapped[str] = mapped_column(String(32))
    start_ts: Mapped[float] = mapped_column(Float)
    end_ts: Mapped[float] = mapped_column(Float)
    manual_count: Mapped[int] = mapped_column(Integer)
    manual_mean_wait_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

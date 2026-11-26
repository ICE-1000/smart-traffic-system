"""REST API. Interactive docs at /docs (Swagger) and /redoc."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import asdict

import asyncio
import csv
import io
from typing import Literal

import cv2
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.app.core.database import SessionLocal
from backend.app.models import db
from backend.app.services.runtime import runtime
from cameras.configuration import CameraConfig
from intelligence.congestion.engine import CongestionConfig
from intelligence.simulation.signal import SignalConfig
from intelligence.types import APPROACHES
from vision.processing.overlay import draw_overlay
from vision.processing.service import VisionConfig
from vision.regions.config import RegionConfig

router = APIRouter(prefix="/api")


def _require_snapshot() -> dict:
    if not runtime.snapshot:
        raise HTTPException(503, "Runtime warming up")
    return runtime.snapshot


# ---------------------------------------------------------------- health
@router.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "ts": time.time(), **runtime.system_status()}


@router.get("/system/events", tags=["system"])
def system_events(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    with SessionLocal() as s:
        rows = s.scalars(select(db.SystemEvent).order_by(db.SystemEvent.ts.desc()).limit(limit)).all()
        return [{"ts": r.ts, "level": r.level, "component": r.component, "message": r.message} for r in rows]


# ---------------------------------------------------------------- cameras
@router.get("/cameras", tags=["cameras"])
def list_cameras() -> list[dict]:
    return runtime.public_cameras()


@router.post("/cameras", tags=["cameras"], status_code=201)
def upsert_camera(cfg: CameraConfig) -> dict:
    """Create or update a camera. If the masked URL returned by GET is sent
    back unchanged (contains ***), the stored URL is kept; an empty string
    clears it."""
    with SessionLocal() as s:
        row = s.get(db.Camera, cfg.id)
        if row is None:
            row = db.Camera(id=cfg.id, intersection_id=runtime.snapshot.get("intersection", {}).get("id", "INT-001"),
                            created_at=time.time())
            s.add(row)
        if "***" in cfg.stream_url:
            cfg.stream_url = row.stream_url or ""  # masked value echoed back: keep stored URL
        for k in ("name", "approach", "stream_url", "enabled", "processing_width", "processing_fps"):
            setattr(row, k, getattr(cfg, k))
        if row.enabled and s.scalars(select(db.Camera).where(db.Camera.approach == cfg.approach, db.Camera.enabled,
                                                             db.Camera.id != cfg.id)).first():
            raise HTTPException(409, f"Another enabled camera already monitors the {cfg.approach} approach")
        s.add(db.SystemEvent(ts=time.time(), level="info", component="cameras", message=f"Camera {cfg.id} saved"))
        s.commit()
    runtime.reload_cameras()
    return next(c for c in runtime.public_cameras() if c["id"] == cfg.id)


def _camera(camera_id: str) -> dict:
    cam = next((c for c in runtime._camera_cache if c["id"] == camera_id), None)
    if cam is None:
        raise HTTPException(404, "Camera not found")
    return cam


@router.post("/cameras/{camera_id}/reconnect", tags=["cameras"])
def reconnect_camera(camera_id: str) -> dict:
    cam = _camera(camera_id)
    if not cam["stream_url"] or not cam["enabled"]:
        raise HTTPException(409, "Camera has no stream address or is disabled")
    if runtime.data_source == "demo":
        raise HTTPException(409, "Cameras are not started in demo mode (System Settings → data source)")
    runtime.cameras.reconnect(camera_id)
    runtime.vision.sync(runtime._camera_cache, runtime.cameras.receiver)
    return {"ok": True}


@router.get("/cameras/{camera_id}/regions", tags=["cameras"])
def get_regions(camera_id: str) -> dict:
    cam = _camera(camera_id)
    return {"configured": bool(cam["regions"]), **(RegionConfig(**cam["regions"]) if cam["regions"] else RegionConfig()).model_dump()}


@router.put("/cameras/{camera_id}/regions", tags=["cameras"])
def put_regions(camera_id: str, regions: RegionConfig) -> dict:
    _camera(camera_id)
    with SessionLocal() as s:
        row = s.get(db.Camera, camera_id)
        row.regions = regions.model_dump()
        s.add(db.SystemEvent(ts=time.time(), level="info", component="vision", message=f"Regions updated for {camera_id}"))
        s.commit()
    runtime.reload_cameras()
    return {"configured": True, **regions.model_dump()}


def _frame(camera_id: str, overlay: bool, max_width: int):
    rx = runtime.cameras.receiver(camera_id)
    fr = rx.latest() if rx else None
    if fr is None:
        return None, None
    img = fr.image
    if img.shape[1] > max_width:
        img = cv2.resize(img, (max_width, int(img.shape[0] * max_width / img.shape[1])), interpolation=cv2.INTER_AREA)
    if overlay:
        w = runtime.vision.worker(camera_id)
        img = draw_overlay(img, runtime.vision.regions.get(camera_id), w.labelled_detections() if w else [], sample=rx.sample)
    elif rx.sample:
        img = draw_overlay(img, None, [], sample=True)
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 72])
    return (jpg.tobytes() if ok else None), fr.seq


@router.get("/cameras/{camera_id}/snapshot.jpg", tags=["cameras"])
def camera_snapshot(camera_id: str, overlay: bool = False, max_width: int = Query(960, ge=160, le=1920)) -> Response:
    _camera(camera_id)
    jpg, _ = _frame(camera_id, overlay, max_width)
    if jpg is None:
        raise HTTPException(404, "No frame available — camera offline")
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/cameras/{camera_id}/stream.mjpeg", tags=["cameras"])
async def camera_stream(camera_id: str, request: Request, overlay: bool = True, fps: float = Query(8, gt=0, le=25),
                        max_width: int = Query(640, ge=160, le=1920)) -> StreamingResponse:
    """MJPEG for <img> tags. Frames are only encoded while someone is watching."""
    _camera(camera_id)
    boundary = "frame"

    async def gen():
        last_seq = None
        while not await request.is_disconnected():
            t0 = time.monotonic()
            jpg, seq = await asyncio.to_thread(_frame, camera_id, overlay, max_width)
            if jpg is not None and seq != last_seq:
                last_seq = seq
                yield (f"--{boundary}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpg)}\r\n\r\n").encode() + jpg + b"\r\n"
            await asyncio.sleep(max(0.0, 1.0 / fps - (time.monotonic() - t0)))

    return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}",
                             headers={"Cache-Control": "no-store"})


@router.delete("/cameras/{camera_id}", tags=["cameras"], status_code=204)
def delete_camera(camera_id: str) -> None:
    with SessionLocal() as s:
        row = s.get(db.Camera, camera_id)
        if row is None:
            raise HTTPException(404, "Camera not found")
        s.delete(row)
        s.commit()
    runtime.reload_cameras()


# ---------------------------------------------------------------- traffic
@router.get("/traffic/current", tags=["traffic"])
def traffic_current() -> dict:
    return _require_snapshot()


@router.get("/traffic/recent", tags=["traffic"])
def traffic_recent(seconds: int = Query(600, ge=10, le=1800)) -> dict:
    """Per-second points from the in-memory buffer (for live charts)."""
    cutoff = time.time() - seconds
    return {"source": runtime.snapshot.get("source", "demo"), "points": [p for p in runtime.recent if p["ts"] >= cutoff]}


@router.get("/traffic/history", tags=["traffic"])
def traffic_history(minutes: int = Query(60, ge=1, le=60 * 24 * 31), bucket_s: int = Query(60, ge=5, le=86400)) -> dict:
    """Bucketed averages from the database, per approach."""
    return _history(minutes, bucket_s)


@router.get("/traffic/history.csv", tags=["traffic"])
def traffic_history_csv(minutes: int = Query(60, ge=1, le=60 * 24 * 31), bucket_s: int = Query(60, ge=5, le=86400)) -> Response:
    """Same data as /traffic/history as a CSV download (timestamps in UTC ISO 8601)."""
    h = _history(minutes, bucket_s)
    cols = ["ts"] + sorted({k for b in h["buckets"] for k in b if k != "ts"})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time_utc", *cols[1:], "sources"])
    for b in h["buckets"]:
        w.writerow([time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(b["ts"])), *[b.get(c, "") for c in cols[1:]], "|".join(h["sources"])])
    name = f"traffic-history-{time.strftime('%Y%m%d-%H%M')}.csv"
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _history(minutes: int, bucket_s: int) -> dict:
    """History of the ACTIVE study site only."""
    cutoff = time.time() - minutes * 60
    iid = runtime.site["id"]
    with SessionLocal() as s:
        tm = s.scalars(select(db.TrafficMeasurement).where(db.TrafficMeasurement.ts >= cutoff,
                                                           db.TrafficMeasurement.intersection_id == iid)).all()
        cm = s.scalars(select(db.CongestionMeasurement).where(db.CongestionMeasurement.ts >= cutoff,
                                                              db.CongestionMeasurement.intersection_id == iid)).all()
    acc: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    sources = set()
    for r in tm:
        b = int(r.ts // bucket_s * bucket_s)
        sources.add(r.source)
        acc[b][f"{r.approach}_queue"].append(r.queue_count)
        acc[b][f"{r.approach}_wait"].append(r.avg_wait_s)
        acc[b][f"{r.approach}_arrival"].append(r.arrival_rate_vpm)
        acc[b][f"{r.approach}_departure"].append(r.departure_rate_vpm)
        acc[b][f"{r.approach}_green"].append(1.0 if r.signal_colour == "green" else 0.0)
        acc[b][f"{r.approach}_in_view"].append(r.vehicles_in_view)
        if r.congestion_index is not None:
            acc[b][f"{r.approach}_ci"].append(r.congestion_index)
        if r.mean_delay_s is not None:
            acc[b][f"{r.approach}_delay"].append(r.mean_delay_s)
    for r in cm:
        acc[int(r.ts // bucket_s * bucket_s)][f"{r.approach}_score"].append(r.score)
    buckets = []
    for b in sorted(acc):
        row = {"ts": b}
        for k, vals in acc[b].items():
            row[k] = round(sum(vals) / len(vals), 2)
        row["arrivals"] = round(sum(row.get(f"{a}_arrival", 0) for a in APPROACHES), 1)
        row["departures"] = round(sum(row.get(f"{a}_departure", 0) for a in APPROACHES), 1)
        row["in_view"] = round(sum(row.get(f"{a}_in_view", 0) for a in APPROACHES), 1)
        buckets.append(row)
    return {"sources": sorted(sources), "bucket_s": bucket_s, "buckets": buckets, "site": runtime.site}


# ---------------------------------------------------------------- congestion
@router.get("/congestion", tags=["congestion"])
def congestion() -> dict:
    snap = _require_snapshot()
    return {"source": snap["source"], "config": asdict(runtime.congestion.config),
            "approaches": {a: r["congestion"] for a, r in snap["approaches"].items()}}


class CongestionConfigIn(BaseModel):
    weights: dict[str, float]
    norms: dict[str, float] | None = None


@router.post("/congestion/config", tags=["congestion"])
def set_congestion_config(body: CongestionConfigIn) -> dict:
    cfg = CongestionConfig(weights=body.weights, norms=body.norms or runtime.congestion.config.norms,
                           thresholds=runtime.congestion.config.thresholds)
    try:
        cfg.validate()
    except ValueError as e:
        raise HTTPException(422, str(e))
    runtime.congestion.config = cfg
    runtime.save_setting("congestion", asdict(cfg))
    runtime.restart_evaluation()
    return asdict(cfg)


# ---------------------------------------------------------------- priority
@router.get("/priority", tags=["priority"])
def priority() -> dict:
    snap = _require_snapshot()
    return {"source": snap["source"], "config": asdict(runtime.priority.config), **snap["priority"]}


@router.get("/priority/history", tags=["priority"])
def priority_history(limit: int = Query(30, ge=1, le=500)) -> list[dict]:
    with SessionLocal() as s:
        rows = s.scalars(select(db.PriorityDecisionRecord).where(db.PriorityDecisionRecord.intersection_id == runtime.site["id"])
                         .order_by(db.PriorityDecisionRecord.ts.desc()).limit(limit)).all()
        return [{"ts": r.ts, "source": r.source, "recommended": r.recommended, "next_recommended": r.next_recommended,
                 "rule": r.rule, "reason": r.reason} for r in rows]


# ---------------------------------------------------------------- simulation
@router.get("/simulation/state", tags=["simulation"])
def simulation_state() -> dict:
    return runtime.sim.snapshot()


class SimulationConfigIn(BaseModel):
    min_green_s: float = Field(gt=0, le=120)
    max_green_s: float = Field(gt=0, le=300)
    yellow_s: float = Field(gt=0, le=10)
    clearance_s: float = Field(ge=0, le=10)
    preempt_min_green_s: float = Field(5.0, ge=3, le=60)
    starvation_s: float | None = Field(None, gt=0, le=600)
    max_skip_s: float | None = Field(None, gt=0, le=1200)


@router.post("/simulation/config", tags=["simulation"])
def set_simulation_config(body: SimulationConfigIn) -> dict:
    cfg = SignalConfig(min_green_s=body.min_green_s, max_green_s=body.max_green_s, yellow_s=body.yellow_s,
                       clearance_s=body.clearance_s, preempt_min_green_s=body.preempt_min_green_s,
                       compatible_pairs=runtime.sim.config.compatible_pairs)
    try:
        cfg.validate()
    except ValueError as e:
        raise HTTPException(422, str(e))
    runtime.sim.config = cfg
    if body.starvation_s:
        runtime.priority.config.starvation_s = body.starvation_s
    if body.max_skip_s:
        runtime.priority.config.max_skip_s = body.max_skip_s
    runtime.save_setting("signal", asdict(cfg))
    runtime.save_setting("priority", asdict(runtime.priority.config))
    runtime.restart_evaluation()
    return {"signal": asdict(cfg), "priority": asdict(runtime.priority.config)}


class DemandIn(BaseModel):
    approach: str
    rate_vpm: float = Field(ge=0, le=60)


@router.post("/simulation/demand", tags=["simulation"])
def set_demo_demand(body: DemandIn) -> dict:
    """Adjust the DEMO arrival rate for an approach (demo source only)."""
    if body.approach not in APPROACHES:
        raise HTTPException(422, "Unknown approach")
    runtime.demo.set_rate(body.approach, body.rate_vpm)
    return {"rates_vpm": runtime.demo.rates()}


class PedestrianIn(BaseModel):
    approach: str


@router.post("/simulation/pedestrian", tags=["simulation"])
def pedestrian_request(body: PedestrianIn) -> dict:
    """Placeholder pedestrian call: marks demand on an approach so it is not skipped."""
    if body.approach not in APPROACHES:
        raise HTTPException(422, "Unknown approach")
    runtime.request_pedestrian(body.approach)
    return {"ok": True}


# ---------------------------------------------------------------- vision + system
class VisionConfigIn(BaseModel):
    enabled: bool = True
    model: str = Field("yolo26n.pt", min_length=1, max_length=200)
    conf: float = Field(0.35, ge=0.05, le=0.95)
    imgsz: int = Field(640, ge=160, le=1280)
    device: str | None = None


@router.get("/vision/config", tags=["vision"])
def get_vision_config() -> dict:
    return {**runtime.vision.config_dict(), "errors": runtime.vision.model_errors}


@router.post("/vision/config", tags=["vision"])
def set_vision_config(body: VisionConfigIn) -> dict:
    cfg = VisionConfig(**body.model_dump())
    runtime.vision.apply_config(cfg, runtime._camera_cache, runtime.cameras.receiver)
    runtime.save_setting("vision", runtime.vision.config_dict())
    if cfg.enabled:
        runtime.start_selftest()  # verify the new model / device immediately
    return runtime.vision.config_dict()


@router.get("/vision/selftest", tags=["vision"])
def get_selftest() -> dict:
    return runtime.ai_selftest


@router.post("/vision/selftest", tags=["vision"])
def run_selftest_now() -> dict:
    """Re-run the AI self-test with the current model settings (runs in the background)."""
    runtime.start_selftest()
    return runtime.ai_selftest


@router.get("/vision/selftest.jpg", tags=["vision"])
def selftest_image() -> Response:
    if not runtime.ai_selftest_jpg:
        raise HTTPException(404, "No self-test image yet")
    return Response(runtime.ai_selftest_jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/vision/detections", tags=["vision"])
def vision_detections(camera_id: str | None = None, limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
    """Finished vehicle tracks (one row per vehicle, not per frame)."""
    with SessionLocal() as s:
        q = select(db.VehicleDetection).order_by(db.VehicleDetection.ts.desc()).limit(limit)
        if camera_id:
            q = q.where(db.VehicleDetection.camera_id == camera_id)
        return [{"ts": r.ts, "first_seen": r.first_seen, "camera_id": r.camera_id, "approach": r.approach,
                 "track_id": r.track_id, "object_class": r.object_class, "confidence": r.confidence,
                 "departed": r.departed, "wait_s": r.wait_s} for r in s.scalars(q).all()]


class SystemConfigIn(BaseModel):
    data_source: Literal["auto", "vision", "demo"]


@router.get("/system/config", tags=["system"])
def get_system_config() -> dict:
    return {"data_source": runtime.data_source}


@router.post("/system/config", tags=["system"])
def set_system_config(body: SystemConfigIn) -> dict:
    runtime.set_data_source(body.data_source)
    runtime.save_setting("system", {"data_source": body.data_source})
    runtime.log_event("info", "system", f"Data source set to {body.data_source}")
    return {"data_source": runtime.data_source}

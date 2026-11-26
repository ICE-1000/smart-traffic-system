"""Research endpoints aligned with the proposal:

* study sites (proposal study nodes) ............ /api/sites
* adaptive vs fixed-time evaluation (RQ2) ....... /api/evaluation
* Congestion Index benchmarking ................. /api/indices
* incident detection, emergency pre-emption ..... /api/incidents, /api/simulation/preempt
* field surveys: moving-car method, validation .. /api/surveys
* peak vs off-peak analysis, short-term forecast  /api/analytics
"""
from __future__ import annotations

import csv
import io
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.models import db
from backend.app.services.runtime import runtime
from intelligence.evaluation.comparison import FixedTimePlan
from intelligence.evaluation.indices import IndexConfig
from intelligence.evaluation.surveys import count_accuracy, moving_car
from intelligence.incidents.detector import IncidentConfig
from intelligence.types import APPROACHES

router = APIRouter(prefix="/api")

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo(settings.timezone)
except Exception:  # tz database missing: fall back to the laptop's local time
    TZ = None


def _local(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, TZ) if TZ else datetime.fromtimestamp(ts)


# ================================================================ study sites
NODE_TYPES = ("signalised", "roundabout", "unconfirmed")


class SiteIn(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    name: str = Field(min_length=1, max_length=120)
    node_type: str = Field(pattern="^(signalised|roundabout|unconfirmed)$")
    corridor: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=1000)


def _site_dict(r: db.Intersection) -> dict:
    return {"id": r.id, "name": r.name, "node_type": r.node_type, "corridor": r.corridor,
            "description": r.description, "city": r.city, "active": r.id == runtime.site["id"]}


@router.get("/sites", tags=["sites"])
def list_sites() -> list[dict]:
    with SessionLocal() as s:
        return [_site_dict(r) for r in s.scalars(select(db.Intersection).order_by(db.Intersection.id)).all()]


@router.post("/sites", tags=["sites"], status_code=201)
def upsert_site(body: SiteIn) -> dict:
    with SessionLocal() as s:
        row = s.get(db.Intersection, body.id) or db.Intersection(id=body.id)
        row.name, row.node_type, row.corridor, row.description = body.name, body.node_type, body.corridor, body.description
        s.add(row)
        s.commit()
        out = _site_dict(row)
    if body.id == runtime.site["id"]:
        runtime._activate_site(body.id, log_it=False)
    return out


class ActiveSiteIn(BaseModel):
    id: str


@router.post("/sites/active", tags=["sites"])
def set_active_site(body: ActiveSiteIn) -> dict:
    try:
        return runtime.set_site(body.id)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ================================================================ evaluation (RQ2)
@router.get("/evaluation", tags=["evaluation"])
def evaluation() -> dict:
    return {"site": runtime.site, "run_started": runtime.eval_run_started, **runtime.comparison.summary()}


class EvaluationConfigIn(BaseModel):
    order: list[str] | None = None
    green_s: dict[str, float] | None = None
    saturation_vps: float | None = Field(None, ge=0.2, le=1.0)


@router.post("/evaluation/config", tags=["evaluation"])
def set_evaluation_config(body: EvaluationConfigIn) -> dict:
    plan = FixedTimePlan(order=body.order or list(runtime.eval_plan.order),
                         green_s={**runtime.eval_plan.green_s, **(body.green_s or {})})
    try:
        plan.validate()
    except ValueError as e:
        raise HTTPException(422, str(e))
    runtime.eval_plan = plan
    if body.saturation_vps:
        runtime.eval_saturation_vps = body.saturation_vps
    runtime.save_setting("evaluation", {"plan": asdict(plan), "saturation_vps": runtime.eval_saturation_vps})
    runtime.restart_evaluation()
    runtime.log_event("info", "evaluation", "Evaluation settings changed — new comparison run started")
    return {"plan": asdict(plan), "saturation_vps": runtime.eval_saturation_vps}


@router.post("/evaluation/reset", tags=["evaluation"])
def reset_evaluation() -> dict:
    runtime.restart_evaluation()
    return {"run_started": runtime.eval_run_started}


@router.get("/evaluation/runs", tags=["evaluation"])
def evaluation_runs(limit: int = Query(20, ge=1, le=200)) -> list[dict]:
    """Latest saved result of each comparison run at the active site (for the report)."""
    with SessionLocal() as s:
        rows = s.scalars(select(db.EvaluationSnapshot).where(db.EvaluationSnapshot.intersection_id == runtime.site["id"])
                         .order_by(db.EvaluationSnapshot.ts.desc())).all()
    latest: dict[float, db.EvaluationSnapshot] = {}
    for r in rows:
        latest.setdefault(r.run_started, r)
    out = []
    for r in list(latest.values())[:limit]:
        d = r.data
        out.append({"run_started": r.run_started, "saved": r.ts, "elapsed_s": r.elapsed_s, "sources": r.sources,
                    "adaptive_mean_delay_s": d["adaptive"]["mean_delay_s"], "fixed_mean_delay_s": d["fixed"]["mean_delay_s"],
                    "adaptive_vehicle_hours": d["adaptive"]["vehicle_hours_delay"],
                    "fixed_vehicle_hours": d["fixed"]["vehicle_hours_delay"],
                    "improvement_pct": d["improvement_pct"]})
    return out


# ================================================================ Congestion Index
@router.get("/indices", tags=["indices"])
def indices() -> dict:
    return {"config": runtime.index_cfg.to_dict(), "approaches": runtime.indices}


@router.post("/indices/config", tags=["indices"])
def set_indices_config(body: dict) -> dict:
    try:
        cfg = IndexConfig(**{k: float(v) if k != "min_samples" else int(v) for k, v in body.items()
                             if k in IndexConfig.__dataclass_fields__})
        cfg.validate()
    except (TypeError, ValueError) as e:
        raise HTTPException(422, str(e))
    runtime.index_cfg = cfg
    runtime.save_setting("indices", cfg.to_dict())
    return cfg.to_dict()


# ================================================================ incidents + pre-emption
@router.get("/incidents", tags=["incidents"])
def incidents(status: str = Query("all", pattern="^(active|all)$"), limit: int = Query(100, ge=1, le=1000)) -> dict:
    with SessionLocal() as s:
        rows = s.scalars(select(db.IncidentRecord).where(db.IncidentRecord.intersection_id == runtime.site["id"])
                         .order_by(db.IncidentRecord.started.desc()).limit(limit)).all()
        history = [{"id": r.id, "kind": r.kind, "approach": r.approach, "severity": r.severity, "started": r.started,
                    "ended": r.ended, "message": r.message, "acknowledged": r.acknowledged, "source": r.source}
                   for r in rows if status == "all" or r.ended is None]
    return {"active": runtime.incidents.active_list(), "history": history, "config": asdict(runtime.incidents.config)}


@router.post("/incidents/{incident_id}/acknowledge", tags=["incidents"])
def acknowledge_incident(incident_id: int) -> dict:
    with SessionLocal() as s:
        r = s.get(db.IncidentRecord, incident_id)
        if r is None:
            raise HTTPException(404, "Incident not found")
        r.acknowledged = True
        s.commit()
    for inc in runtime.incidents.active.values():
        if inc.db_id == incident_id:
            inc.acknowledged = True
    return {"ok": True}


@router.post("/incidents/config", tags=["incidents"])
def set_incident_config(body: dict) -> dict:
    try:
        cfg = IncidentConfig(**{**asdict(runtime.incidents.config),
                                **{k: v for k, v in body.items() if k in IncidentConfig.__dataclass_fields__}})
        if min(cfg.confirm_s, cfg.clear_s, cfg.stall_s, cfg.blocked_green_s, cfg.spillback_limit_m) <= 0:
            raise ValueError("all incident thresholds must be positive")
    except (TypeError, ValueError) as e:
        raise HTTPException(422, str(e))
    runtime.incidents.config = cfg
    runtime.save_setting("incidents", asdict(cfg))
    return asdict(cfg)


class PreemptIn(BaseModel):
    approach: str = Field(pattern="^(north|south|east|west)$")
    hold_s: float = Field(20, ge=5, le=120)
    reason: str = Field("Emergency vehicle", min_length=1, max_length=80)


@router.post("/simulation/preempt", tags=["simulation"])
def preempt(body: PreemptIn) -> dict:
    """SIMULATED emergency-vehicle pre-emption (no connection to real signals)."""
    runtime.sim.request_preemption(body.approach, body.hold_s, body.reason)
    runtime.log_event("warning", "simulation", f"Emergency pre-emption requested: {body.approach} ({body.reason})")
    return {"preemption": runtime.sim.preempt}


@router.delete("/simulation/preempt", tags=["simulation"])
def cancel_preempt() -> dict:
    runtime.sim.cancel_preemption()
    return {"preemption": None}


# ================================================================ field surveys
class MovingCarIn(BaseModel):
    corridor: str = Field(min_length=1, max_length=120)
    direction: str = Field(min_length=1, max_length=40)
    run_time: float  # epoch seconds
    distance_km: float = Field(gt=0, le=50)
    tw_min: float = Field(gt=0, le=240)
    ta_min: float = Field(gt=0, le=240)
    x: float = Field(ge=0, le=100000)
    y: float = Field(ge=-100000, le=100000)
    free_flow_kmh: float | None = Field(None, gt=0, le=150)
    notes: str | None = Field(None, max_length=500)


def _period(ts: float) -> str:
    h = _local(ts).hour + _local(ts).minute / 60
    if 7 <= h < 9:
        return "am_peak"
    if 16 <= h < 19:
        return "pm_peak"
    if 6 <= h < 22:
        return "off_peak"
    return "night"


def _run_dict(r: db.SurveyRun) -> dict:
    base = {"id": r.id, "corridor": r.corridor, "direction": r.direction, "run_time": r.run_time,
            "period": _period(r.run_time), "distance_km": r.distance_km, "tw_min": r.tw_min, "ta_min": r.ta_min,
            "x": r.x, "y": r.y, "free_flow_kmh": r.free_flow_kmh, "notes": r.notes}
    try:
        base["result"] = moving_car(r.distance_km, r.tw_min, r.ta_min, r.x, r.y, r.free_flow_kmh)
    except ValueError as e:
        base["result"] = {"error": str(e)}
    return base


@router.get("/surveys/moving-car", tags=["surveys"])
def list_moving_car() -> dict:
    with SessionLocal() as s:
        rows = [_run_dict(r) for r in s.scalars(select(db.SurveyRun).where(db.SurveyRun.intersection_id == runtime.site["id"])
                                                 .order_by(db.SurveyRun.run_time.desc())).all()]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if "error" not in r["result"]:
            groups[(r["corridor"], r["direction"], r["period"])].append(r["result"])
    summary = []
    for (corr, direc, per), res in sorted(groups.items()):
        cis = [x["ci"] for x in res if x["ci"] is not None]
        summary.append({"corridor": corr, "direction": direc, "period": per, "runs": len(res),
                        "mean_flow_vph": round(sum(x["flow_vph"] for x in res) / len(res), 1),
                        "mean_journey_time_min": round(sum(x["mean_journey_time_min"] for x in res) / len(res), 3),
                        "mean_speed_kmh": round(sum(x["space_mean_speed_kmh"] for x in res) / len(res), 1),
                        "mean_ci": round(sum(cis) / len(cis), 2) if cis else None})
    return {"runs": rows, "summary": summary}


@router.post("/surveys/moving-car", tags=["surveys"], status_code=201)
def add_moving_car(body: MovingCarIn) -> dict:
    try:
        moving_car(body.distance_km, body.tw_min, body.ta_min, body.x, body.y, body.free_flow_kmh)
    except ValueError as e:
        raise HTTPException(422, str(e))
    with SessionLocal() as s:
        r = db.SurveyRun(created=time.time(), intersection_id=runtime.site["id"], **body.model_dump())
        s.add(r)
        s.commit()
        return _run_dict(r)


@router.delete("/surveys/moving-car/{run_id}", tags=["surveys"], status_code=204)
def delete_moving_car(run_id: int) -> None:
    with SessionLocal() as s:
        r = s.get(db.SurveyRun, run_id)
        if r is None:
            raise HTTPException(404, "Run not found")
        s.delete(r)
        s.commit()


@router.get("/surveys/moving-car.csv", tags=["surveys"])
def moving_car_csv() -> Response:
    data = list_moving_car()["runs"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["site", "corridor", "direction", "run_time_local", "period", "distance_km", "tw_min", "ta_min", "x", "y",
                "free_flow_kmh", "flow_vph", "mean_journey_time_min", "space_mean_speed_kmh", "ci", "tti", "notes"])
    for r in data:
        res = r["result"]
        w.writerow([runtime.site["name"], r["corridor"], r["direction"], _local(r["run_time"]).strftime("%Y-%m-%d %H:%M"),
                    r["period"], r["distance_km"], r["tw_min"], r["ta_min"], r["x"], r["y"], r["free_flow_kmh"] or "",
                    res.get("flow_vph", ""), res.get("mean_journey_time_min", ""), res.get("space_mean_speed_kmh", ""),
                    res.get("ci", "") if res.get("ci") is not None else "", res.get("tti", "") if res.get("tti") is not None else "",
                    r["notes"] or ""])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="moving-car-surveys.csv"'})


class ValidationIn(BaseModel):
    camera_id: str
    start_ts: float
    end_ts: float
    manual_count: int = Field(ge=0, le=100000)
    manual_mean_wait_s: float | None = Field(None, ge=0, le=3600)
    notes: str | None = Field(None, max_length=500)


def _validation_dict(r: db.ValidationCount, s) -> dict:
    tracks = s.scalars(select(db.VehicleDetection).where(
        db.VehicleDetection.camera_id == r.camera_id, db.VehicleDetection.first_seen >= r.start_ts,
        db.VehicleDetection.first_seen < r.end_ts, db.VehicleDetection.entered_approach.is_(True))).all()
    waits = [t.wait_s for t in tracks if t.wait_s is not None]
    sys_wait = round(sum(waits) / len(waits), 1) if waits else None
    out = {"id": r.id, "camera_id": r.camera_id, "start_ts": r.start_ts, "end_ts": r.end_ts,
           "duration_min": round((r.end_ts - r.start_ts) / 60, 1), "manual_count": r.manual_count,
           "system_count": len(tracks), "manual_mean_wait_s": r.manual_mean_wait_s, "system_mean_wait_s": sys_wait,
           "notes": r.notes, **count_accuracy(r.manual_count, len(tracks))}
    if r.manual_mean_wait_s and sys_wait is not None:
        out["wait_error_pct"] = round((sys_wait - r.manual_mean_wait_s) / r.manual_mean_wait_s * 100, 1)
    return out


@router.get("/surveys/validation", tags=["surveys"])
def list_validation() -> dict:
    with SessionLocal() as s:
        rows = [_validation_dict(r, s) for r in s.scalars(select(db.ValidationCount).where(
            db.ValidationCount.intersection_id == runtime.site["id"]).order_by(db.ValidationCount.start_ts.desc())).all()]
    valid = [r for r in rows if r["manual_count"] > 0]
    tot_m = sum(r["manual_count"] for r in valid)
    tot_s = sum(r["system_count"] for r in valid)
    return {"sessions": rows, "overall": {"sessions": len(valid), "manual_total": tot_m, "system_total": tot_s,
                                          **count_accuracy(tot_m, tot_s)}}


@router.post("/surveys/validation", tags=["surveys"], status_code=201)
def add_validation(body: ValidationIn) -> dict:
    if body.end_ts <= body.start_ts:
        raise HTTPException(422, "end must be after start")
    if body.end_ts > time.time() + 60:
        raise HTTPException(422, "the counting session must already have ended")
    if not any(c["id"] == body.camera_id for c in runtime._camera_cache):
        raise HTTPException(404, "Camera not found")
    with SessionLocal() as s:
        r = db.ValidationCount(created=time.time(), intersection_id=runtime.site["id"], **body.model_dump())
        s.add(r)
        s.commit()
        return _validation_dict(r, s)


@router.delete("/surveys/validation/{vid}", tags=["surveys"], status_code=204)
def delete_validation(vid: int) -> None:
    with SessionLocal() as s:
        r = s.get(db.ValidationCount, vid)
        if r is None:
            raise HTTPException(404, "Session not found")
        s.delete(r)
        s.commit()


# ================================================================ peak analysis + forecast
PERIOD_LABEL = {"am_peak": "AM peak 07:00–09:00", "pm_peak": "PM peak 16:00–19:00",
                "off_peak": "Off-peak 06:00–22:00 (other)", "night": "Night 22:00–06:00"}


@router.get("/analytics/periods", tags=["analytics"])
def period_analysis(days: int = Query(7, ge=1, le=31), weekdays_only: bool = False) -> dict:
    """Peak vs off-peak comparison using the proposal's peak periods (local time)."""
    cutoff = time.time() - days * 86400
    with SessionLocal() as s:
        rows = s.scalars(select(db.TrafficMeasurement).where(db.TrafficMeasurement.ts >= cutoff,
                                                             db.TrafficMeasurement.intersection_id == runtime.site["id"])).all()
    acc: dict[tuple, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    sources: dict[str, set] = defaultdict(set)
    for r in rows:
        if weekdays_only and _local(r.ts).weekday() >= 5:
            continue
        p = _period(r.ts)
        sources[p].add(r.source)
        for key in ((p, r.approach), (p, "all")):
            d = acc[key]
            d["queue"].append(r.queue_count)
            d["wait"].append(r.avg_wait_s)
            d["arrival_vph"].append(r.arrival_rate_vpm * 60)
            if r.congestion_index is not None:
                d["ci"].append(r.congestion_index)
            if r.mean_delay_s is not None:
                d["delay"].append(r.mean_delay_s)
    out = []
    for p in PERIOD_LABEL:
        for a in ("all", *APPROACHES):
            d = acc.get((p, a))
            if not d:
                continue
            mean = lambda k: round(sum(d[k]) / len(d[k]), 2) if d[k] else None  # noqa: E731
            n = len(d["queue"])
            out.append({"period": p, "label": PERIOD_LABEL[p], "approach": a,
                        "samples": n, "minutes": round(n * settings.persist_every_s / 60 / (4 if a == "all" else 1), 1),
                        "mean_queue": mean("queue"), "mean_wait_s": mean("wait"), "mean_arrival_vph": mean("arrival_vph"),
                        "mean_ci": mean("ci"), "mean_delay_s": mean("delay"), "sources": sorted(sources[p])})
    return {"days": days, "weekdays_only": weekdays_only, "timezone": settings.timezone if TZ else "local",
            "site": runtime.site, "rows": out}


def _holt(series: list[float], alpha: float = 0.4, beta: float = 0.2, horizon: int = 15) -> tuple[list[float], float | None]:
    """Holt's linear exponential smoothing; returns forecasts and in-sample one-step MAE."""
    level, trend = series[0], series[1] - series[0]
    errors = []
    for x in series[1:]:
        pred = level + trend
        errors.append(abs(x - pred))
        new_level = alpha * x + (1 - alpha) * (level + trend)
        trend = beta * (new_level - level) + (1 - beta) * trend
        level = new_level
    fc = [max(0.0, level + h * trend) for h in range(1, horizon + 1)]
    return fc, (sum(errors) / len(errors) if errors else None)


@router.get("/analytics/forecast", tags=["analytics"])
def forecast(horizon: int = Query(15, ge=5, le=60), history_min: int = Query(90, ge=20, le=360)) -> dict:
    """Short-term arrival-rate forecast per approach (Holt's method on 1-minute means)."""
    cutoff = time.time() - history_min * 60
    with SessionLocal() as s:
        rows = s.scalars(select(db.TrafficMeasurement).where(db.TrafficMeasurement.ts >= cutoff,
                                                             db.TrafficMeasurement.intersection_id == runtime.site["id"])
                         .order_by(db.TrafficMeasurement.ts)).all()
    per: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    srcs: set[str] = set()
    for r in rows:
        per[r.approach][int(r.ts // 60 * 60)].append(r.arrival_rate_vpm * 60)
        srcs.add(r.source)
    out = {}
    for a in APPROACHES:
        mins = sorted(per[a])
        hist = [{"ts": m, "vph": round(sum(per[a][m]) / len(per[a][m]), 1)} for m in mins]
        if len(hist) < 10:
            out[a] = {"history": hist, "forecast": [], "mae_vph": None, "enough_data": False}
            continue
        fc, mae = _holt([h["vph"] for h in hist], horizon=horizon)
        last = mins[-1]
        out[a] = {"history": hist[-60:], "forecast": [{"ts": last + 60 * (i + 1), "vph": round(v, 1)} for i, v in enumerate(fc)],
                  "mae_vph": round(mae, 1) if mae is not None else None, "enough_data": True}
    return {"method": "Holt linear exponential smoothing (alpha 0.4, beta 0.2) on 1-minute mean arrival rates",
            "horizon_min": horizon, "sources": sorted(srcs), "approaches": out}

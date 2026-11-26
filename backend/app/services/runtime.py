"""Runtime orchestrator: the "brain" loop.

Every tick (1 Hz):
    for each approach pick a measurement:
        vision  – fresh ApproachMeasurement from that approach's camera worker
        demo    – the demo traffic model (DATA_SOURCE=auto fallback or demo mode)
        none    – no usable data (DATA_SOURCE=vision and camera/AI unavailable)
    congestion <- CongestionEngine(measurements)
    signal     <- SignalSimulator.tick(...)   (uses PriorityEngine)
    indices    <- Congestion Index per approach from departed-vehicle delays
    evaluation <- ComparisonEngine: adaptive vs fixed-time on the same arrivals
    incidents  <- IncidentDetector rules
    snapshot   -> WebSocket clients
    every 5 s  -> database (worker thread); evaluation snapshot every 60 s

Camera receivers and YOLO workers run in their own threads; this loop only
reads their latest results, so a slow or dead camera never stalls it.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from pathlib import Path

import psutil
from sqlalchemy import delete, select

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, check_database, run_migrations
from backend.app.models import db
from backend.app.services.demo_source import DemoTrafficSource
from backend.app.websocket.manager import ConnectionManager
from cameras.configuration import is_sample, mask_credentials
from cameras.manager import CameraManager
from intelligence.congestion.engine import CongestionConfig, CongestionEngine
from intelligence.evaluation.comparison import ComparisonEngine, FixedTimePlan
from intelligence.evaluation.indices import DelayWindow, IndexConfig
from intelligence.incidents.detector import IncidentConfig, IncidentDetector
from intelligence.priority.engine import PriorityConfig, PriorityEngine
from intelligence.simulation.signal import SignalConfig, SignalSimulator
from intelligence.types import APPROACHES, ApproachMeasurement
from vision.processing.service import VisionConfig, VisionService
from vision.regions.config import RegionConfig

log = logging.getLogger("runtime")

DEFAULT_CAMERAS = [
    ("CAM-01", "North approach camera", "north"),
    ("CAM-02", "South approach camera", "south"),
    ("CAM-03", "East approach camera", "east"),
    ("CAM-04", "West approach camera", "west"),
]
DATA_SOURCES = ("auto", "vision", "demo")

# First start only: CAM-01 shows the bundled SAMPLE video (always labelled) so the AI pipeline is visibly
# working before any phone is connected. Replace the address with the phone's stream in Camera Management.
SAMPLE_CAMERA_URL = "file://samples/synthetic_approach.mp4"
SAMPLE_REGIONS = {"approach": [[0.31, 0.0], [0.69, 0.0], [0.69, 0.87], [0.31, 0.87]],
                  "queue": [[0.31, 0.3], [0.69, 0.3], [0.69, 0.87], [0.31, 0.87]],
                  "stop_line": [[0.31, 0.875], [0.69, 0.875]], "queue_length_m": 45}

# Study nodes named in the research proposal (slide "Study Area — Key Critical Study Nodes").
# Control type of City Market Cross is not stated in the proposal: confirm on site.
STUDY_SITES = [
    ("CBD-01", "Kafue Roundabout", "roundabout", "Cairo Road",
     "Primary southern gateway arterial along Cairo Road (proposal study node)."),
    ("CBD-02", "Hybrid Roundabout", "roundabout", "Great North Road",
     "High-density junction on Great North Road (proposal study node)."),
    ("CBD-03", "City Market Cross", "unconfirmed", "Lumumba Road",
     "Commercial transit hub along Lumumba Road (proposal study node). Confirm control type on site."),
]


class TrafficRuntime:
    def __init__(self) -> None:
        self.ws = ConnectionManager()
        self.data_source = settings.data_source if settings.data_source in DATA_SOURCES else "auto"
        self.cameras = CameraManager(start_receivers=self.data_source != "demo")
        self.vision = VisionService(VisionConfig(settings.vision_enabled, settings.yolo_model, settings.yolo_conf,
                                                 settings.yolo_imgsz, settings.yolo_device))
        self.congestion = CongestionEngine()
        self.priority = PriorityEngine()
        self.sim = SignalSimulator(self.priority)
        self.demo = DemoTrafficSource(seed=settings.demo_seed)
        self.ped_requests: set[str] = set()
        self.recent: deque[dict] = deque(maxlen=1800)  # 30 min @ 1 Hz
        self.snapshot: dict = {}
        self.started_at = time.time()
        self.tick_ms = 0.0
        self.db_ok = False
        self._last_persist = 0.0
        self._last_retention = 0.0
        self._persisted_events = 0.0
        self._last_decision_key: tuple | None = None
        self._last_decision_ts = 0.0
        self._task: asyncio.Task | None = None
        self._camera_cache: list[dict] = []
        self._vision_counts: dict[str, int] = {}  # finished vehicle tracks per camera since start
        self.site: dict = {"id": settings.intersection_id, "name": settings.intersection_name,
                           "node_type": "signalised", "corridor": None, "description": None}
        self.index_cfg = IndexConfig()
        self.delay_windows = {a: DelayWindow() for a in APPROACHES}
        self.last_departure: dict[str, float | None] = {a: None for a in APPROACHES}
        self.indices: dict[str, dict] = {}
        self.incidents = IncidentDetector()
        self.eval_plan = FixedTimePlan()
        self.eval_saturation_vps = 0.5
        self.comparison = self._new_comparison()
        self._last_eval_persist = 0.0
        self.ai_selftest: dict = {"status": "not_run"}
        self.ai_selftest_jpg: bytes | None = None
        self.proc = psutil.Process()
        self.proc.cpu_percent(None)

    # ------------------------------------------------------------ settings persistence
    def _new_comparison(self) -> ComparisonEngine:
        self.eval_run_started = time.time()
        return ComparisonEngine(self.priority.config, self.sim.config, self.congestion, self.eval_plan,
                                self.eval_saturation_vps)

    def restart_evaluation(self) -> None:
        """Start a fresh adaptive-vs-fixed run (after tuning changes, so runs are never mixed)."""
        self.comparison = self._new_comparison()

    def load_settings(self) -> None:
        with SessionLocal() as s:
            rows = {r.key: r.value for r in s.scalars(select(db.AppSetting)).all()}

        def only(cls, d: dict) -> dict:
            return {k: v for k, v in d.items() if k in cls.__dataclass_fields__}

        def apply(key: str, fn) -> None:  # one bad entry never discards the others
            if key in rows:
                try:
                    fn(rows[key])
                except Exception:
                    log.exception("Stored setting %r invalid — keeping default", key)

        def _congestion(v):
            cfg = CongestionConfig(**only(CongestionConfig, v))
            cfg.validate()
            self.congestion.config = cfg

        def _signal(v):
            v = only(SignalConfig, v)
            v["compatible_pairs"] = [tuple(p) for p in v.get("compatible_pairs", [])]
            cfg = SignalConfig(**v)
            cfg.validate()
            self.sim.config = cfg

        def _system(v):
            if v.get("data_source") in DATA_SOURCES:
                self.data_source = v["data_source"]
                self.cameras.start_receivers = self.data_source != "demo"

        def _indices(v):
            cfg = IndexConfig(**only(IndexConfig, v))
            cfg.validate()
            self.index_cfg = cfg

        def _evaluation(v):
            plan = FixedTimePlan(**only(FixedTimePlan, v.get("plan", {})))
            plan.validate()
            self.eval_plan = plan
            self.eval_saturation_vps = float(v.get("saturation_vps", 0.5))

        apply("congestion", _congestion)
        apply("signal", _signal)
        apply("priority", lambda v: setattr(self.priority, "config", PriorityConfig(**only(PriorityConfig, v))))
        apply("vision", lambda v: self.vision.cfg.__dict__.update(VisionConfig(**only(VisionConfig, v)).__dict__))
        apply("system", _system)
        apply("indices", _indices)
        apply("incidents", lambda v: setattr(self.incidents, "config", IncidentConfig(**only(IncidentConfig, v))))
        apply("evaluation", _evaluation)
        apply("site", lambda v: self._activate_site(v["intersection_id"], log_it=False))
        self.restart_evaluation()

    def save_setting(self, key: str, value: dict) -> None:
        with SessionLocal() as s:
            row = s.get(db.AppSetting, key)
            if row is None:
                s.add(db.AppSetting(key=key, value=value, updated_at=time.time()))
            else:
                row.value, row.updated_at = value, time.time()
            s.commit()

    def log_event(self, level: str, component: str, message: str) -> None:
        try:
            with SessionLocal() as s:
                s.add(db.SystemEvent(ts=time.time(), level=level, component=component, message=message))
                s.commit()
        except Exception:
            log.exception("could not log event")

    # ------------------------------------------------------------ lifecycle
    def bootstrap_db(self) -> None:
        run_migrations()
        with SessionLocal() as s:
            if not s.get(db.Intersection, settings.intersection_id):
                s.add(db.Intersection(id=settings.intersection_id, name=settings.intersection_name, node_type="signalised",
                                      description="Development / demonstration site."))
            for sid, name, node_type, corridor, desc in STUDY_SITES:
                if not s.get(db.Intersection, sid):
                    s.add(db.Intersection(id=sid, name=name, node_type=node_type, corridor=corridor, description=desc))
            if not s.scalars(select(db.Camera)).first():
                sample_ok = (Path(__file__).resolve().parents[3] / "samples" / "synthetic_approach.mp4").exists()
                for cid, name, approach in DEFAULT_CAMERAS:
                    first = cid == "CAM-01" and sample_ok
                    s.add(db.Camera(id=cid, intersection_id=settings.intersection_id, name=name, approach=approach,
                                    stream_url=SAMPLE_CAMERA_URL if first else "",
                                    regions=SAMPLE_REGIONS if first else None, created_at=time.time()))
            s.add(db.SystemEvent(ts=time.time(), level="info", component="backend", message="Backend started"))
            s.commit()
        self._activate_site(settings.intersection_id, log_it=False)
        self.load_settings()
        self.reload_cameras()
        self.db_ok = check_database()
        if self.vision.cfg.enabled:
            self.start_selftest()

    # ------------------------------------------------------------ AI self-test
    def start_selftest(self) -> None:
        """Load the model and detect on the bundled test image (background thread)."""
        if self.ai_selftest.get("status") == "running":
            return
        self.ai_selftest = {"status": "running", "ts": time.time()}

        def _run() -> None:
            from vision.detection.selftest import run_selftest

            cfg = self.vision.cfg
            info, jpg = run_selftest(cfg.model, cfg.device, cfg.imgsz, cfg.conf)
            info["status"] = "passed" if info["ok"] else "failed"
            self.ai_selftest, self.ai_selftest_jpg = info, jpg
            if info["ok"]:
                self.log_event("info", "vision", f"AI self-test passed: {info['detections']} objects in {info['infer_ms']} ms")
            else:
                log.error("AI self-test failed: %s | %s", info.get("error"), info.get("hint"))
                self.log_event("error", "vision", f"AI self-test failed: {info.get('error')} — {info.get('hint')}")

        threading.Thread(target=_run, name="ai-selftest", daemon=True).start()

    def reload_cameras(self) -> None:
        with SessionLocal() as s:
            rows = s.scalars(select(db.Camera).order_by(db.Camera.id)).all()
            self._camera_cache = [
                {"id": r.id, "name": r.name, "approach": r.approach, "stream_url": r.stream_url,
                 "enabled": r.enabled, "processing_width": r.processing_width, "processing_fps": r.processing_fps,
                 "regions": r.regions}
                for r in rows
            ]
        for c in self._camera_cache:
            try:
                self.vision.set_regions(c["id"], RegionConfig(**c["regions"]) if c["regions"] else RegionConfig())
            except Exception:
                self.vision.set_regions(c["id"], RegionConfig())
        self.cameras.sync(self._camera_cache)
        if self.data_source == "demo":
            self.vision.stop_all()
        else:
            self.vision.sync(self._camera_cache, self.cameras.receiver)

    def set_data_source(self, mode: str) -> None:
        self.data_source = mode
        self.cameras.start_receivers = mode != "demo"
        if mode == "demo":
            self.vision.stop_all()
            self.cameras.stop_all()
        self.reload_cameras()

    def _activate_site(self, site_id: str, log_it: bool = True) -> dict:
        with SessionLocal() as s:
            row = s.get(db.Intersection, site_id)
            if row is None:
                raise ValueError(f"Unknown site {site_id}")
            self.site = {"id": row.id, "name": row.name, "node_type": row.node_type, "corridor": row.corridor,
                         "description": row.description, "city": row.city}
        if log_it:
            self.log_event("info", "site", f"Active study site: {self.site['name']} ({self.site['id']})")
            self.restart_evaluation()
            for w in self.delay_windows.values():
                w.samples.clear()
        return self.site

    def set_site(self, site_id: str) -> dict:
        site = self._activate_site(site_id)
        self.save_setting("site", {"intersection_id": site_id})
        if self.snapshot:  # reflect the switch immediately, not at the next tick
            self.snapshot["site"] = site
            self.snapshot["intersection"] = {"id": site["id"], "name": site["name"]}
        return site

    def camera_for(self, approach: str) -> dict | None:
        return next((c for c in self._camera_cache if c["approach"] == approach and c["enabled"]), None)

    def public_cameras(self) -> list[dict]:
        st = self.cameras.statuses()
        out = []
        for c in self._camera_cache:
            w = self.vision.worker(c["id"])
            out.append({
                **{k: v for k, v in c.items() if k != "regions"},
                "stream_url": mask_credentials(c["stream_url"]),
                "has_stream_url": bool(c["stream_url"]),
                "is_sample": is_sample(c["stream_url"]),
                "has_regions": bool(c["regions"]),
                **{k: v for k, v in st.get(c["id"], {}).items() if k not in ("camera_id", "is_sample")},
                "vision": w.stats() if w else None,
            })
        return out

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.vision.stop_all()
        self.cameras.stop_all()

    async def _loop(self) -> None:
        dt = settings.tick_seconds
        while True:
            t0 = time.perf_counter()
            try:
                self.step(dt)
                await self.ws.broadcast({"type": "snapshot", **self.snapshot})
                if time.time() - self._last_persist >= settings.persist_every_s:
                    self._last_persist = time.time()
                    await asyncio.to_thread(self.persist)
            except Exception:  # keep the loop alive; surface the error
                log.exception("runtime tick failed")
            self.tick_ms = (time.perf_counter() - t0) * 1000
            await asyncio.sleep(max(0.0, dt - (time.perf_counter() - t0)))

    # ------------------------------------------------------------ measurements
    def _measurements(self, dt: float) -> dict[str, ApproachMeasurement]:
        colours = {a: c.value for a, c in self.sim.colours().items()}
        demo = self.demo.step(dt, colours)  # always stepped so the demo stays continuous
        out: dict[str, ApproachMeasurement] = {}
        for a in APPROACHES:
            m: ApproachMeasurement | None = None
            if self.data_source != "demo":
                cam = self.camera_for(a)
                w = self.vision.worker(cam["id"]) if cam else None
                if cam and w and self.cameras.is_online(cam["id"]):
                    m = w.fresh_measurement()
            if m is None:
                m = demo[a] if self.data_source in ("auto", "demo") else ApproachMeasurement.no_data(a)  # type: ignore[arg-type]
            m.pedestrian_request = a in self.ped_requests
            out[a] = m
        # departure delays for the Congestion Index (only from the source actually used)
        now = time.time()
        demo_delays = self.demo.drain_delays()
        for a in APPROACHES:
            cam = self.camera_for(a)
            w = self.vision.worker(cam["id"]) if cam else None
            vision_delays = w.drain_delays() if w else []
            delays = demo_delays[a] if out[a].source == "demo" else vision_delays if out[a].source == "vision" else []
            if out[a].source in ("demo", "vision"):
                self.delay_windows[a].add(now, delays, out[a].source)
            if delays:
                self.last_departure[a] = now
        return out

    def request_pedestrian(self, approach: str) -> None:
        self.ped_requests.add(approach)

    # ------------------------------------------------------------ tick
    def step(self, dt: float) -> dict:
        ms = self._measurements(dt)
        cg = self.congestion.evaluate_all(list(ms.values()))
        self.sim.tick(dt, ms, cg)
        colours = {a: c.value for a, c in self.sim.colours().items()}
        now_wall = time.time()
        for a in APPROACHES:
            cam = self.camera_for(a)
            regions = (cam or {}).get("regions") or {}
            section = regions.get("queue_length_m") or self.index_cfg.default_section_m
            self.indices[a] = self.delay_windows[a].result(now_wall, section, self.index_cfg) if ms[a].source != "none" else \
                {"samples": 0, "mean_delay_s": None, "ci": None, "tti": None, "section_m": section, "free_flow_s": None}
        self.comparison.step(dt, ms)
        green_elapsed = {a: (self.sim.green_elapsed if self.sim.stage == "green" and a == self.sim.current else 0.0)
                         for a in APPROACHES}
        for a in list(self.ped_requests):
            if colours[a] == "green":
                self.ped_requests.discard(a)  # placeholder: served by the green phase
        now = time.time()

        decision = self.sim.last_decision
        cam_by_approach = {a: (self.camera_for(a) or {}).get("id") for a in APPROACHES}
        approaches = {
            a: {
                "approach": a,
                "camera_id": cam_by_approach[a],
                "measurement": ms[a].to_dict(),
                "congestion": cg[a].to_dict(),
                "signal": colours[a],
                "time_since_served_s": round(self.sim.time_since_served[a], 1),
                "indices": self.indices[a],
            }
            for a in APPROACHES
        }
        sources = {m.source for m in ms.values()}
        source = sources.pop() if len(sources) == 1 else "mixed"
        queued = sum(m.queue_count for m in ms.values())
        avg_wait = (sum(m.avg_wait_s * m.queue_count for m in ms.values()) / queued) if queued else 0.0
        worst = max(cg.values(), key=lambda r: r.score)
        point = {
            "ts": now,
            **{f"{a}_queue": ms[a].queue_count for a in APPROACHES},
            **{f"{a}_score": cg[a].score for a in APPROACHES},
            **{f"{a}_wait": ms[a].avg_wait_s for a in APPROACHES},
            **{f"{a}_qlen": ms[a].queue_length_m for a in APPROACHES},
            **{f"{a}_green": 1 if colours[a] == "green" else 0 for a in APPROACHES},
            "arrivals": round(sum(m.arrival_rate_vpm for m in ms.values()), 1),
            "departures": round(sum(m.departure_rate_vpm for m in ms.values()), 1),
            "in_view": sum(m.vehicles_in_view for m in ms.values()),
            "avg_wait": round(avg_wait, 1),
        }
        self.recent.append(point)
        cams = self.public_cameras()
        self.incidents.update(ms, colours, green_elapsed, self.last_departure, cams, now)
        detected_total = sum(
            self.demo.totals()[a] if ms[a].source == "demo" else self._vision_total(cam_by_approach[a])
            for a in APPROACHES
        )
        self.snapshot = {
            "ts": now,
            "source": source,
            "data_source_mode": self.data_source,
            "intersection": {"id": self.site["id"], "name": self.site["name"]},
            "site": self.site,
            "incidents": self.incidents.active_list(),
            "evaluation": self._evaluation_brief(),
            "approaches": approaches,
            "priority": {**(decision.to_dict() if decision else {}), "current_green": self.sim.current,
                         "stage": self.sim.stage},
            "signal": self.sim.snapshot(),
            "totals": {
                "vehicles_detected": detected_total,
                "vehicles_in_view": point["in_view"],
                "heavy_in_view": sum(m.heavy_vehicles for m in ms.values()),
                "light_in_view": sum(m.light_vehicles for m in ms.values()),
                "queued": queued,
                "avg_wait_s": round(avg_wait, 1),
                "most_congested": {"approach": worst.approach, "score": worst.score, "category": worst.category},
                "cameras_online": sum(1 for c in cams if c.get("status") == "online"),
                "cameras_total": len(cams),
                "critical_approaches": sum(1 for r in cg.values() if r.category == "critical"),
                "spillback_approaches": sum(1 for m in ms.values() if m.queue_length_m >= self.congestion.config.norms["queue_length"]),
                "no_data_approaches": sum(1 for m in ms.values() if m.source == "none"),
            },
            "cameras": cams,
            "point": point,
            "demo": {"rates_vpm": self.demo.rates()} if "demo" in {m.source for m in ms.values()} else None,
            "system": self.system_status(),
        }
        return self.snapshot

    def _evaluation_brief(self) -> dict:
        full = self.comparison.summary()
        pick = lambda w: {k: w[k] for k in ("mean_delay_s", "vehicle_hours_delay", "throughput_vph", "queued_now",  # noqa: E731
                                            "departed", "stop_rate")}
        return {"elapsed_s": full["elapsed_s"], "warming_up": full["warming_up"], "run_started": self.eval_run_started,
                "adaptive": pick(full["adaptive"]), "fixed": pick(full["fixed"]),
                "improvement_pct": full["improvement_pct"]}

    def _vision_total(self, camera_id: str | None) -> int:
        return self._vision_counts.get(camera_id or "", 0)

    def system_status(self) -> dict:
        workers = list(self.vision.workers.values())
        stats = [w.stats() for w in workers]
        detecting = [s for s in stats if s["status"] == "detecting"]
        if self.data_source == "demo":
            ai = "disabled (demo mode)"
        elif not self.vision.cfg.enabled:
            ai = "disabled"
        elif self.vision.model_errors or self.ai_selftest.get("status") == "failed":
            ai = "error"
        elif detecting:
            ai = "running"
        elif any(s["status"] == "loading_model" for s in stats) or self.ai_selftest.get("status") == "running":
            ai = "loading"
        elif self.ai_selftest.get("status") == "passed":
            ai = "ready (waiting for camera frames)"
        else:
            ai = "idle (no camera frames)"
        return {
            "backend": "ok",
            "database": "ok" if self.db_ok else "error",
            "websocket_clients": self.ws.count,
            "ai_model": ai,
            "ai_model_name": self.vision.cfg.model,
            "ai_model_error": next(iter(self.vision.model_errors.values()), None) or self.ai_selftest.get("error"),
            "ai_hint": self.ai_selftest.get("hint"),
            "ai_tracker": next((w._yolo.mode for w in workers if w._yolo is not None), self.ai_selftest.get("tracker")),
            "video_processing": f"running ({len(detecting)} feed{'s' if len(detecting) != 1 else ''})" if detecting else "idle",
            "data_source": self.snapshot.get("source", "demo") if self.snapshot else "demo",
            "data_source_mode": self.data_source,
            "cpu_percent": round(self.proc.cpu_percent(None), 1),
            "system_cpu_percent": round(psutil.cpu_percent(None), 1),
            "memory_mb": round(self.proc.memory_info().rss / 1e6, 1),
            "system_memory_percent": round(psutil.virtual_memory().percent, 1),
            "tick_ms": round(self.tick_ms, 2),
            "processing_fps": round(sum(s["processing_fps"] for s in detecting), 1) if detecting else None,
            "detection_ms": round(sum(s["detection_ms"] for s in detecting) / len(detecting), 1) if detecting else None,
            "active_feeds": self.cameras.online_count(),
            "uptime_s": round(time.time() - self.started_at),
        }

    # ------------------------------------------------------------ persistence
    def persist(self) -> None:
        snap = self.snapshot
        if not snap:
            return
        ts, iid = snap["ts"], self.site["id"]
        try:
            with SessionLocal() as s:
                for a, row in snap["approaches"].items():
                    m, c = row["measurement"], row["congestion"]
                    if m["source"] == "none":
                        continue  # don't store fabricated zeros
                    s.add(db.TrafficMeasurement(
                        ts=ts, intersection_id=iid, approach=a, camera_id=row["camera_id"], source=m["source"],
                        queue_count=m["queue_count"], queue_length_m=m["queue_length_m"], avg_wait_s=m["avg_wait_s"],
                        arrival_rate_vpm=m["arrival_rate_vpm"], departure_rate_vpm=m["departure_rate_vpm"],
                        vehicles_in_view=m["vehicles_in_view"], heavy_vehicles=m["heavy_vehicles"],
                        signal_colour=row["signal"], mean_delay_s=row["indices"].get("mean_delay_s"),
                        congestion_index=row["indices"].get("ci")))
                    s.add(db.CongestionMeasurement(ts=ts, intersection_id=iid, approach=a, source=m["source"],
                                                   score=c["score"], category=c["category"], components=c["components"]))
                for e in reversed(self.sim.events):
                    if e.ts <= self._persisted_events:
                        break
                    s.add(db.SignalSimulationEvent(ts=e.ts, intersection_id=iid, kind=e.kind, approach=e.approach, reason=e.reason))
                if self.sim.events:
                    self._persisted_events = self.sim.events[-1].ts
                p = snap["priority"]
                key = (p.get("recommended"), p.get("rule"))
                if key != self._last_decision_key or ts - self._last_decision_ts > 30:
                    s.add(db.PriorityDecisionRecord(ts=ts, intersection_id=iid, source=snap["source"], recommended=p.get("recommended"),
                                                    next_recommended=p.get("next_recommended"), rule=p.get("rule", ""),
                                                    reason=p.get("reason", ""), ranking=p.get("ranking", [])))
                    self._last_decision_key, self._last_decision_ts = key, ts
                # finished vehicle tracks from the vision workers
                for cid, w in list(self.vision.workers.items()):
                    for tr in w.drain_finished():
                        if not tr.counted_arrival and len(tr.positions) < 3:
                            continue  # momentary false positives
                        self._vision_counts[cid] = self._vision_counts.get(cid, 0) + 1
                        s.add(db.VehicleDetection(ts=tr.last_seen, first_seen=tr.first_seen, camera_id=cid,
                                                  approach=w.camera["approach"], track_id=tr.id, object_class=tr.cls,
                                                  confidence=round(tr.max_conf, 3), bbox=[round(v, 4) for v in tr.last_bbox],
                                                  entered_approach=tr.counted_arrival, departed=tr.departed, wait_s=tr.wait_s))
                opened, closed = self.incidents.drain()
                for inc in opened:
                    rec = db.IncidentRecord(intersection_id=iid, kind=inc.kind, approach=inc.approach, severity=inc.severity,
                                            started=inc.started, message=inc.message, source=snap["source"])
                    s.add(rec)
                    s.flush()
                    inc.db_id = rec.id
                for inc in closed:
                    rec = s.get(db.IncidentRecord, inc.db_id) if inc.db_id else None
                    if rec:
                        rec.ended, rec.message = inc.ended, inc.message
                if time.time() - self._last_eval_persist >= 60 and self.comparison.t >= 60:
                    self._last_eval_persist = time.time()
                    summ = self.comparison.summary()
                    summ.pop("series", None)
                    s.add(db.EvaluationSnapshot(ts=ts, intersection_id=iid, run_started=self.eval_run_started,
                                                elapsed_s=summ["elapsed_s"], sources=snap["source"], data=summ))
                if time.time() - self._last_retention > 3600:
                    self._last_retention = time.time()
                    cutoff = time.time() - settings.retention_days * 86400
                    for model in (db.TrafficMeasurement, db.CongestionMeasurement, db.VehicleDetection,
                                  db.PriorityDecisionRecord, db.SignalSimulationEvent, db.EvaluationSnapshot):
                        s.execute(delete(model).where(model.ts < cutoff))
                    s.execute(delete(db.IncidentRecord).where(db.IncidentRecord.started < cutoff))
                s.commit()
            self.db_ok = True
        except Exception:
            self.db_ok = False
            log.exception("persist failed")


runtime = TrafficRuntime()

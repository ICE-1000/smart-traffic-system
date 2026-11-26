# Project report — Phases 1 to 10

Each phase was delivered as a runnable increment and verified before the next one.

## Phase 1 — Foundation
FastAPI backend (REST + `/ws/live` at 1 Hz), congestion / priority / signal-simulation modules,
demo traffic model, React + TypeScript + Tailwind + Recharts + Lucide dashboard (8 pages)
following the supplied control-room reference: top bar, nested sidebar, light breadcrumb strip,
map-centred intersection with four floating camera windows, KPI boxes, right column with Flow,
Queue Length (area + ring gauge) and Congestion Broadcast panels.

## Phase 2 — Camera connectivity
`cameras/receiver.py`: OpenCV/FFmpeg capture per camera, RTSP over TCP, open/read timeouts,
newest-frame-only buffer, grab/retrieve split to save CPU, reconnection with 1 → 30 s back-off,
real fps measurement. HTTP/MJPEG phone streams and `file://` sample footage also supported.
`/stream.mjpeg` and `/snapshot.jpg` endpoints; the dashboard camera windows show live video,
fps and status; sample files are stamped and badged SAMPLE FOOTAGE.

## Phase 3 — Multiple cameras
`cameras/manager.py` runs one receiver per enabled camera, restarts only the camera whose
configuration changed, detects stale streams (no frame for 5 s → offline), enforces one
enabled camera per approach, exposes Reconnect. Tested: an unreachable phone stays
*offline — retrying* while a working one keeps streaming.

## Phase 4 — AI vehicle detection
`vision/detection/detector.py`: YOLO26-nano (verified to download and run on CPU here:
≈ 50–60 ms per 640 px frame), classes car/motorcycle/bus/truck + person/bicycle kept separate,
class-agnostic NMS, configurable confidence / inference size / device, model errors surfaced on
the dashboard. Boxes with class, track ID and confidence drawn on the live video.

## Phase 5 — Tracking and queue analytics
ByteTrack IDs; `vision/tracking/state.py` turns tracks into arrivals, queued vehicles, waiting
times, departures and queue length inside per-camera regions drawn in the new **region
editor** (Camera Management). On the synthetic sample: 16 arrivals/min measured vs ≈ 15
generated; waiting times build through the red phase to ≈ 19 s. Each finished vehicle stored
once in `vehicle_detections`.

## Phases 6–8 — Congestion, priority, simulation on camera data
The runtime picks per approach: camera measurement (AI) → demo (SIM, auto mode) → NO DATA
(cameras-only mode). Priority engine gained a **no-data fixed-time fallback** so an approach
whose camera fails is still served. Weights, timings, priority limits, AI settings and data-source
mode are **persisted** and reloaded at start. Every dashboard number shows its origin.

## Phase 9 — Historical analytics
Alembic migrations (auto-run at startup), PostgreSQL support verified against PostgreSQL 16,
time ranges 15 min – 30 days, CSV export, hourly retention, vehicle-track API.

## Phase 10 — Testing and optimisation
38 automated tests (unit, camera failure, API, end-to-end YOLO). `scripts/benchmark.py`
recommends per-camera fps and inference size for 2 and 4 feeds on the actual laptop.
Documentation: phone setup, database, testing protocol for real roads, limitations, licensing.

## Iteration 11 — Proposal alignment (v1.1)
Compared the project with the research proposal and added what it promised (docs/PROPOSAL-ALIGNMENT.md):
- **Study sites:** Kafue Roundabout, Hybrid Roundabout and City Market Cross seeded; one active
  site at a time; roundabouts labelled so signal results are read as hypothetical.
- **RQ2 — adaptive vs fixed-time evaluation:** counterfactual queue model on measured arrivals;
  delay, vehicle-hours, throughput, queues, stop rate; saved runs; reproducible script.
- **Controller correction:** the evaluation exposed that cutting greens while queues still
  discharged made the controller worse than fixed time under balanced heavy demand; replaced by
  queue-clearance actuated greens (regression-tested). Against a demand-tuned fixed plan the
  corrected controller lowers delay 12–62 % in six of seven synthetic patterns.
- **Scope change:** research question 3 was removed from the project and the report.
- **Benchmarking:** Congestion Index / TTI per approach, in history and peak periods.
- **Data ingestion:** Moving Car Method form and manual-count validation with accuracy.
- **Expected outcomes:** rule-based incident detection with log and alerts; simulated
  emergency pre-emption.
- **Predictive planning:** 15-minute Holt forecast with error.
- **Database:** migration 0002 (verified on SQLite and on PostgreSQL 16 with existing data).
- **Tests:** 58 automated tests.
- **Dashboard:** three pages added (Evaluation, Incidents & Alerts, Field Surveys) and
  extended Congestion, Analytics, Simulation and Settings pages — same visual design.

## What still needs you (cannot be done without the hardware / site)
1. Run `python scripts/benchmark.py` on the Windows laptop and set fps / inference size.
2. Connect the phones (docs/PHONE_SETUP.md) and draw regions for each.
3. Field validation: manual counts and stopwatch waits vs system (docs/TESTING.md) — this is
   the evidence the project report needs.
4. Calibrate congestion weights and signal timings from that data (all tunable in the UI).
5. Complete the field tasks listed in docs/PROPOSAL-ALIGNMENT.md §12.

## Main files added in Phases 2–10
```
cameras/receiver.py, cameras/manager.py (rewritten), cameras/configuration.py
vision/detection/detector.py, vision/tracking/state.py, vision/regions/config.py,
vision/processing/service.py, vision/processing/overlay.py
backend/app/services/runtime.py (rewritten), backend/app/api/routes.py (+stream, regions, vision, system, CSV)
backend/app/core/database.py (+migrations), backend/app/models/db.py (+regions, AppSetting, track rows)
alembic.ini, database/migrations/ (env.py, 0001_initial_schema.py), database/setup_postgres.sql
scripts/make_sample_video.py, scripts/benchmark.py
frontend: CameraPanel (live MJPEG), RegionEditor (new), Camera Management, System Settings,
          Live Monitoring, Analytics (CSV, 7/30 days), source badges everywhere
tests/test_tracking.py, test_cameras.py, test_vision_e2e.py (+ extended API/priority tests)
docs/PHONE_SETUP.md, DATABASE.md, TESTING.md, LIMITATIONS.md, PROJECT-REPORT.md
```

# Architecture

## 1. System overview

```
 ┌──────────── EYES ────────────┐      ┌───────────────────────── BRAIN (Windows 11 laptop) ─────────────────────────┐      ┌─ CONTROL CENTRE ─┐
 │ Android phone N  ── RTSP ──┐ │      │ cameras/receiver (P2)  →  vision/detection (P4) → tracking + regions (P5)    │      │                  │
 │ Android phone S  ── RTSP ──┼─┼─────▶│        │                                      │                              │      │  React dashboard │
 │ Android phone E  ── RTSP ──┤ │ Wi-Fi│        ▼                                      ▼                              │ WS   │  (Vite, TS,      │
 │ Android phone W  ── RTSP ──┘ │      │  ApproachMeasurement  ◀── DemoTrafficSource (P1, labelled "demo")            │─────▶│   Tailwind,      │
 └──────────────────────────────┘      │        │                                                                     │ REST │   Recharts)      │
                                       │        ▼                                                                     │◀────▶│                  │
                                       │  CongestionEngine ─▶ PriorityEngine ─▶ SignalSimulator (no hardware output)  │      │                  │
                                       │        │                                                                     │      └──────────────────┘
                                       │        ▼                                                                     │
                                       │  SQLite (P1) / PostgreSQL (P9): measurements, decisions, events               │
                                       └──────────────────────────────────────────────────────────────────────────────┘
```

**Key seam:** every measurement producer emits `intelligence.types.ApproachMeasurement`.
Phase 1 produces it from a stochastic demo model; Phase 5 produces it from tracked YOLO
detections. The intelligence layer, database and dashboard do not change when the source does,
and `source` ("demo" | "vision") travels with every value so the UI can label it honestly.

### Runtime loop (`backend/app/services/runtime.py`)
One asyncio task, 1 Hz by default (`TICK_SECONDS`):
1. read measurements (demo source now; vision pipeline later)
2. `CongestionEngine.evaluate_all`
3. `SignalSimulator.tick` (calls `PriorityEngine.decide`; asserts no conflicting greens)
4. build a snapshot → broadcast on `/ws/live`
5. every `PERSIST_EVERY_S` (5 s) → write to the database in a worker thread

### Threads
```
per camera:  CameraReceiver thread   grab() every frame, retrieve() ≤ 12 fps, keeps only the newest
             VisionWorker thread     at processing_fps: resize → YOLO+ByteTrack → ApproachTracker
shared:      INFERENCE_LOCK          cameras take turns on the CPU (faster than parallel on a laptop)
asyncio:     runtime loop (1 Hz), API, WebSocket, MJPEG streams (JPEG encode in a worker thread,
             only while a browser is watching)
```
A receiver that cannot connect retries with back-off (1 → 30 s) on its own thread; the
runtime simply sees no fresh measurement for that approach and falls back (demo in *auto*,
NO DATA in *vision* mode). One dead camera therefore cannot stall the system.

## 2. Separation of concerns

| Module | Knows about | Never knows about |
|---|---|---|
| `intelligence/congestion` | measurements | priority, signals, web |
| `intelligence/priority` | measurements, congestion, time-since-served | clocks, web, hardware |
| `intelligence/simulation` | priority engine, timing constraints | web, hardware (there is **no** output to real controllers) |
| `cameras/` | stream configuration and status | detection, congestion |
| `backend/app` | wiring, persistence, transport | algorithm internals |
| `frontend` | the snapshot contract (`src/types/traffic.ts`) | algorithm internals |

## 3. Dashboard component layout (matches the supplied reference)

```
┌ TopBar: SMART TRAFFIC ITS logo │ status · clock/date · notifications · operator ───────────────────────────────┐
├ Sidebar ────────┬ Breadcrumb strip (light) ─────────────────────────────────────────── [fullscreen] ──────┤
│ Smart Traffic ▾ │ [Intersection ▾][🔍] SIMULATED          [Traffic Situation][Signal Plan] ┌ Traffic Flow ──┐│
│  Overview       │ ┌Vehicles Detected┐┌Most Congested┐                                  │ bars+lines,    ││
│  Live Monitoring│ └─────────────────┘└──────────────┘                                  │ 3 tabs         ││
│  Intersection ▾ │   ┌ CAM North ┐   ║ NORTH ║   ┌ CAM East ┐                          ├ Queue Length ──┤│
│   Congestion    │   │ video/NO  │   ║ queue ║   │          │                          │ area + ring    ││
│   Priority      │   └───────────┘ ══╬═══════╬══ └──────────┘                          │ gauge N/E/S/W  ││
│   Signal Sim    │  WEST ══════════ ║ junction║ ═══════════ EAST                      ├ Congestion     ││
│  Analytics      │   ┌ CAM West ─┐   ║       ║   ┌ CAM South ┐                         │ Broadcast  ‹ › ││
│ Camera Mgmt     │   └───────────┘   ║ SOUTH ║   └───────────┘                         │ + Queue Overrun││
│ System Settings │                                                                     │ + Spillback    ││
│ v0.1      [‹]   │                                                                     └────────────────┘│
└─────────────────┴──────────────────────────────────────────────────────────────────────────────────────┘
```

Reusable components: `Panel`, `StatPanel`, `CameraPanel` (real `<img>` MJPEG slot + detection
canvas overlay + offline placeholder), `IntersectionMap` (custom SVG; left-hand traffic),
`DirectionGauge`, `SignalHead`, `StatusRow`, `CategoryTag`, `ScoreBar`.

Visual tokens live in `frontend/tailwind.config.js` (ink navy scale, sky accent, amber
numerals, green/amber/red states) and `src/index.css` (`.panel`, `.panel-head`, `.sim-badge`).
Numerals use **Bahnschrift** (ships with Windows 11, DIN-style, close to the reference).

## 4. Technology decisions

| Decision | Reason |
|---|---|
| React + Vite (not Next.js) | Purely client-side dashboard talking to a local FastAPI; no SSR needed; faster dev server on modest hardware |
| Hash router instead of react-router | 8 static pages; avoids a dependency, deep links still work |
| One WebSocket, 1 Hz snapshot | Simple, robust; the snapshot is ~6 kB. Video goes over a separate MJPEG endpoint (Phase 2) so JSON never carries frames |
| SQLite in Phase 1 via SQLAlchemy | Spec allows it; switching to PostgreSQL is a `DATABASE_URL` change (Phase 9) |
| Split phasing (one approach green at a time) | Safest default with four camera-monitored approaches; `compatible_pairs` allows N+S / E+W later after engineering review |
| Left-hand traffic in the map | Zambia drives on the left; inbound lanes are drawn on the driver's left |
| YOLO26-nano (Ultralytics, Jan 2026) | Smallest current Ultralytics detector, CPU-friendly. **AGPL-3.0** (checked against ultralytics.com/license): fine for research; internal/commercial deployment needs an Enterprise licence |
| ByteTrack via Ultralytics `model.track` | No extra dependency beyond `lap`; uses low-confidence boxes to keep IDs through occlusion |
| Overlay drawn server-side on the MJPEG | Boxes can never drift out of sync with the video; browser needs no canvas logic |
| Regions stored normalised (0–1) | Survive resolution / processing-width changes |
| Alembic migrations run at startup | Same code path for SQLite and PostgreSQL; no manual schema step |

## 5. Delivery approach (agile, iterative, prototype-first)

Each phase is a short iteration ending in something runnable and demonstrable:

| Iteration | Increment | Status |
|---|---|---|
| 1 Foundation | Backend skeleton, intelligence engines, demo source, full dashboard | ✅ |
| 2 One camera | `cameras/receiver.py` (OpenCV + back-off reconnect), MJPEG endpoint | ✅ |
| 3 Multi-camera | Receiver + worker per camera, shared inference lock, 4 feeds | ✅ |
| 4 Detection | YOLO26n, class filter, agnostic NMS, boxes on video | ✅ |
| 5 Tracking + regions | ByteTrack, region editor, queue/wait/arrival/departure | ✅ |
| 6–8 | Engines on vision data, persisted tuning, no-data fallback | ✅ (field calibration pending) |
| 9 Analytics | Alembic, PostgreSQL verified, 30-day ranges, CSV, retention | ✅ |
| 10 Hardening | Tests, benchmark, limitations, phone guide | ✅ |
| 11 Proposal alignment | Study nodes, evaluation (RQ2), CI, moving-car, validation, incidents, pre-emption, peak analysis, forecast | ✅ |

Every iteration ends with: what changed, files touched, how to run, how to test, what is not yet done.

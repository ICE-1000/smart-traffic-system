# Smart Traffic Management and Intelligent Transportation System for Lusaka CBD (prototype)

**Phones are the eyes. The laptop is the brain. The dashboard is the control centre.**

Android phones stream each approach of an intersection to a Windows laptop. The laptop
detects and tracks vehicles (YOLO26 + ByteTrack), measures queues and waiting times inside
configurable regions, scores congestion, decides which approach should be prioritised (with
fairness rules and a written reason), and runs a **simulated** demand-responsive signal plan.
A control-room dashboard shows all of it live.

> ⚠️ **Safety:** research and simulation only. This software has no output to traffic
> signals and must not be connected to any. Real deployment requires the road authority,
> qualified traffic engineers, approved equipment and formal safety validation.

## Getting started (step by step, Windows 11)

You do **not** need a phone to try it. The project comes with a sample traffic video and the AI
model, so it works straight away.

### 1. Install the tools (one time only)

| Tool | Where to get it | Check it worked (type in PowerShell) |
|---|---|---|
| Python 3.11, 3.12 or 3.13 | https://www.python.org/downloads/ — tick **"Add python.exe to PATH"** during install | `python --version` |
| Node.js 20 or newer (LTS) | https://nodejs.org | `node --version` |

You also need about **3 GB of free disk space** and an internet connection for step 2.

### 2. Set up the project (one time only, ~10 minutes)

With the project folder open, open a terminal in it (in VS Code: **Terminal → New Terminal**),
then copy and paste these lines one at a time, pressing Enter after each:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
copy backend\.env.example backend\.env
cd frontend
npm install
cd ..
```

> If `.venv\Scripts\activate` shows a red "running scripts is disabled" error, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer **Y**, and try again.

### 3. Start it (every time)

Double-click these two files in the project folder. Each opens a window — **leave both open**.

1. **`run-backend.bat`** — the "brain" (AI + logic). Wait until it shows
   `Uvicorn running on http://127.0.0.1:8000`.
2. **`run-frontend.bat`** — the dashboard. Wait until it shows `Local: http://localhost:5173/`.

Now open **http://localhost:5173** in your web browser.

To stop, close the two windows (or press `Ctrl + C` in each).

### 4. Check it is working

- On **Live Monitoring**, the North camera shows the sample video with coloured boxes around
  vehicles (allow ~30 seconds after starting). It is labelled **SAMPLE FOOTAGE**.
- North's numbers are tagged **AI** (measured by the camera). The other three approaches are
  tagged **SIM** because they have no camera yet — that is normal.
- Still not sure? Go to **System Settings → AI Detection → Test AI model**, or in PowerShell
  (with `.venv\Scripts\activate` done first) run:

```powershell
python scripts\check_ai.py
```
It checks Python, the AI libraries, the model file, detection, tracking and video decoding, and
prints the exact fix for anything marked **[FAIL]**.

### Common problems

| What you see | Fix |
|---|---|
| `python` is not recognised | Reinstall Python and tick "Add python.exe to PATH". |
| `npm` is not recognised | Install Node.js, then close and reopen PowerShell. |
| Dashboard opens but everything says **NO DATA** / offline | The backend window is closed or crashed — start `run-backend.bat` again and read its last lines. |
| Port 8000 or 5173 "already in use" | An old copy is still running. Close its window (or end `python.exe` / `node.exe` in Task Manager) and start again. |
| AI test says the DLL / torch failed to load | Install the Microsoft Visual C++ Redistributable (x64) and restart. `check_ai.py` prints the link. |
| Vehicles detected but numbers look slow | Your laptop is busy. Run `python scripts\benchmark.py` and lower the fps in Camera Management. |

## How it works (in simple terms)

```
 Phones / sample video  ──►  Laptop "brain"  ──►  Dashboard in your browser
   (the eyes)                (backend, port 8000)    (control centre, port 5173)
```

1. **See** — each phone films one road into the junction (North, South, East, West) and sends
   the video to the laptop over Wi-Fi.
2. **Detect** — the AI (YOLO) finds every car, bus, truck and motorcycle in each frame.
3. **Track** — each vehicle gets an ID so it is counted once, and the system notes how long it
   waits in the queue area before crossing the stop line.
4. **Score** — for each road it works out queue length, waiting time and a **congestion score**.
5. **Decide** — it picks which road should get green next, with fairness rules so no road waits
   too long, and writes a plain-English reason ("West prioritised: 6 queued, waiting 36 s…").
6. **Simulate** — a *pretend* traffic light follows those decisions so you can compare it with
   a normal fixed-time light. Nothing is connected to real signals.
7. **Show and save** — the dashboard updates live, and history is saved to a database for charts
   and CSV export.

What each dashboard page is for:

| Page | What it shows |
|---|---|
| Overview | The whole junction at a glance: congestion per road and current recommendation |
| Live Monitoring | Camera videos with AI boxes, counts and queues |
| Congestion Analysis | Congestion score per road and how it is calculated |
| Priority Decisions | Which road should go next and why |
| Signal Simulation | The simulated traffic light running on the measurements |
| Evaluation | Adaptive (this system) vs fixed-time signal: delay, throughput |
| Incidents & Alerts | Possible problems to check: a stalled vehicle, a blocked stop line, a very long queue, a camera offline |
| Traffic Analytics | History, peak vs off-peak, short-term forecast, CSV export |
| Field Surveys | Manual counts and Moving Car Method, to check the AI against people |
| Camera Management | Add phones, paste stream addresses, draw the road regions |
| System Settings | AI settings, data source (Auto / AI / Demo), AI self-test |

Every number is labelled with where it came from: **AI** (real camera), **SIM** (demo model,
used when a camera is missing) or **NO DATA**.

## Status — all 10 phases built + proposal alignment (v1.1)

| Phase | What works |
|---|---|
| 1 Foundation | FastAPI + WebSocket backend, React control-room dashboard (8 pages) |
| 2–3 Cameras | One OpenCV receiver thread per phone (RTSP or HTTP/MJPEG), automatic reconnect with back-off, live MJPEG to the dashboard, 4 feeds supported, one dead phone never affects others |
| 4 Detection | YOLO26-nano (COCO): car, motorcycle, bus, truck; person/bicycle kept separate; boxes and labels drawn on the live video |
| 5 Tracking | ByteTrack IDs (each vehicle counted once), region editor (approach area, queue area, stop line, real length), arrivals, queued vehicles, waiting times, departures, queue length |
| 6 Congestion | Multi-indicator score on real camera measurements, tunable weights saved to the DB |
| 7 Priority | Demand + fairness + empty-approach rules + no-data fallback, every decision explained |
| 8 Simulation | Safe split-phase signal simulation driven by the camera measurements |
| 9 Analytics | PostgreSQL (or SQLite) via Alembic migrations, history up to 30 days, CSV export, retention |
| 10 Hardening | Automated tests incl. camera failure and end-to-end YOLO, benchmark script, documented limitations |
| 11 Proposal alignment | Study nodes from the proposal, adaptive vs fixed-time evaluation (RQ2), Congestion Index, Moving Car Method, manual-count validation, incident detection, simulated emergency pre-emption, peak vs off-peak analysis, short-term forecast — see docs/PROPOSAL-ALIGNMENT.md |

Every value on the dashboard carries its origin: **AI** (camera measurement), **SIM** (demo
model, used where no camera is working in *Auto* mode) or **NO DATA**. Sample video files are
always labelled **SAMPLE FOOTAGE**.

## Connect the phones

See **docs/PHONE_SETUP.md** — install a camera-streaming app, put phones and laptop on the same
Wi-Fi (or the laptop's Mobile hotspot), paste each phone's stream address into Camera
Management, draw the regions, done.

## Reproduce the controller evaluation

```powershell
python scripts\evaluate_controller.py
```
Adaptive vs fixed-time (equal and demand-tuned splits) over seven demand patterns — the table in
docs/ALGORITHMS.md §4.

## Measure your laptop

```powershell
python scripts\benchmark.py
```
Prints milliseconds per frame and the frame rate you can afford per camera for 2 and 4 feeds.
Set those in Camera Management (processing fps) and System Settings (inference size).

## Tests

```powershell
python -m pytest                # 61 tests (a few minutes, includes one end-to-end YOLO run)
python -m pytest -m "not slow"  # skip the YOLO run
```

## Documentation

| File | Contents |
|---|---|
| docs/PHONE_SETUP.md | Android apps, network, stream addresses, phone placement |
| docs/ARCHITECTURE.md | Components, threads, data flow, dashboard layout, decisions |
| docs/ALGORITHMS.md | Tracking/queue rules, congestion score, priority rules, signal simulation |
| docs/API.md | REST + WebSocket endpoints |
| docs/DATABASE.md | SQLite vs PostgreSQL, migrations, retention |
| docs/TESTING.md | What is tested and how to test with real phones |
| docs/LIMITATIONS.md | What this prototype cannot do yet, licensing |
| docs/PROJECT-REPORT.md | Phase-by-phase delivery report |
| docs/PROPOSAL-ALIGNMENT.md | Proposal ↔ project matrix: objectives, research questions, methodology, CRISP-DM, study area, outcomes, budget |

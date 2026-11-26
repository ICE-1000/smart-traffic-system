# Proposal ↔ Project Alignment

**Proposal:** *Smart Traffic Management & ITS — A Data-Driven Framework for Mitigating Congestion in the
Lusaka Central Business District (CBD)*. BSc Computer Science, NIPA. Student: Bernard Musonda (29001530).
Supervisor: Mr. Benjamin Simwinga.

**Project:** Smart Traffic Management and Intelligent Transportation System for Lusaka CBD (prototype v1.1).

Status key: ✅ implemented and tested · 🟡 implemented, needs field data · ⬜ outside prototype scope (stated as future work)

---

## 1. Scope statement (use this wording in the final report)

The proposal describes a CBD-wide, data-driven ITS framework. This project delivers the framework's
**first operational component at intersection level**: a camera-and-AI system that measures demand at one
study node at a time, benchmarks congestion, makes explainable demand-responsive priority decisions,
and evaluates them against a fixed-time schedule. The same software is moved between the proposal's study
nodes. Corridor-level measurement is covered by the Moving
Car Method module; network-wide micro-simulation and city-wide deployment are future work.

## 2. Aim and objectives

| Proposal | Delivered by | Status |
|---|---|---|
| **Primary aim** — improve urban mobility through a smart traffic modelling and ITS framework | Whole system, quantified on *Evaluation* (delay, throughput, queues) | ✅ / 🟡 field data |
| **Modelling** — framework to simulate real-world congestion patterns in the CBD | Measurement models (`vision/`), congestion score + Congestion Index, queue model + signal simulation driven by **measured** arrivals (`intelligence/evaluation/comparison.py`), peak-period analysis, short-term forecast | ✅ intersection level · ⬜ network model |
| **ITS design** — ITS tailored to dynamic traffic flows at peak times | Adaptive priority engine + safe signal simulation, incident detection, simulated emergency pre-emption, control-room dashboard | ✅ |

## 3. Research questions → evidence

| Research question | Evidence produced by the system | Where | Status |
|---|---|---|---|
| **RQ1 Modelling patterns** — can empirical modelling represent and diagnose congestion in Lusaka? | Per-approach queues, waits, arrivals, Congestion Index from cameras; peak vs off-peak comparison; manual-count validation (accuracy %); moving-car corridor CI | *Traffic Analytics*, *Field Surveys*, `/api/analytics/periods`, `/api/surveys/*` | 🟡 needs site sessions |
| **RQ2 Flow optimisation** — to what extent can ITS optimise throughput and reduce bottlenecks? | Adaptive vs fixed-time counterfactual on the same measured arrivals: delay, vehicle-hours, throughput, queues, stop rate. Synthetic benchmark: 12–62 % lower delay than a demand-tuned fixed plan, except balanced demand at capacity (+8 %) | *Evaluation*, `scripts/evaluate_controller.py`, docs/ALGORITHMS.md §4 | ✅ method · 🟡 site runs |

**Scope change:** the proposal's third research question has been removed from the project and the final report. State this in the report's scope /
limitations section. The project therefore answers RQ1 and RQ2.

## 4. Problem statement → features

| Problem (proposal slide 4) | Response |
|---|---|
| Chronic shortage of empirical traffic data | Every measurement, vehicle track, decision, incident and survey is stored (SQLite/PostgreSQL) with CSV export; data source labelled AI / SIM / NO DATA |
| Inefficient, static management | Demand-responsive control: green duration follows the queue, phase order follows priority, empty approaches skipped |
| Lack of real-time responsiveness | 1-second analysis loop, live dashboard, incident alerts |
| Approaches with little or no demand still receive green | Empty-approach skip (with max-skip and pedestrian safeguards) |

## 5. Methodology (proposal slide 8: "Audit to Analysis")

| Step | Proposal | Implementation | Status |
|---|---|---|---|
| Route ID | Identify high-volume corridors and bottlenecks | Study sites register with the three proposal nodes; one active site at a time | ✅ |
| Data ingestion | Manual counts | *Field Surveys → Validation*: manual count vs system count, accuracy % | ✅ / 🟡 |
| | Video analysis | Phone cameras → YOLO26 detection + ByteTrack tracking → regions → measurements | ✅ |
| | "Moving Car Method" audits | *Field Surveys → Moving Car Method* (Wardrop & Charlesworth 1954): flow, journey time, speed, CI | ✅ / 🟡 |
| Benchmarking | Congestion Index (CI) for comparison | CI and TTI per approach (live, history, peak periods) and per corridor (moving-car) | ✅ / 🟡 |
| Modelling | Simulate traffic dynamics under ITS interventions | Counterfactual adaptive vs fixed-time model on measured arrivals; signal simulation; pre-emption | ✅ |

## 6. CRISP-DM (proposal slide 9)

CRISP-DM has **six** phases; the proposal slide lists five (Data Understanding is missing). Mapping:

| CRISP-DM phase | In this project |
|---|---|
| 1 Business understanding | Problem statement, objectives, research questions; study nodes; peak periods |
| 2 **Data understanding** | Camera feasibility at each node; region drawing; peak/off-peak profiles; validation of AI counts against manual counts |
| 3 Data preparation | Detection filtering (classes, confidence, class-agnostic NMS), tracking, ID-flicker suppression (3 sightings), class majority vote, region rules, 5-s aggregation, retention |
| 4 Modelling | Congestion score, Congestion Index, priority engine, signal simulation, evaluation queue model, Holt forecast |
| 5 Evaluation | Adaptive vs fixed-time comparison; count accuracy; 59 automated tests; benchmark script |
| 6 Deployment | Prototype dashboard on a Windows laptop with phones (research use only; not connected to real signals) |

Software development followed an **agile, iterative** sequence (10 phases + this alignment iteration);
CRISP-DM describes the data lifecycle inside those iterations.

## 7. Study area (proposal slide 10)

| Node | Proposal description | In system | Note for the report |
|---|---|---|---|
| Kafue Roundabout (CBD-01) | Southern gateway arterial, Cairo Road | Roundabout | Measurements, CI, incidents and surveys apply directly; signal plan and RQ2 results describe a **hypothetical signalised** operation |
| Hybrid Roundabout (CBD-02) | High-density junction, Great North Road | Roundabout | as above |
| City Market Cross (CBD-03) | Commercial hub, Lumumba Road | Unconfirmed | Confirm on site whether it is signal-controlled; update in *System Settings → Study Sites* |

The dashboard labels a roundabout site "Roundabout · signals hypothetical" so results are never presented
as real signal operation.

## 8. Expected outcomes (proposal slide 11)

| Outcome | Status | Wording to use |
|---|---|---|
| Real-time traffic monitoring | ✅ | — |
| Incident detection | ✅ rule-based | "Rule-based incident indicators (blocked discharge, stalled vehicle, spillback, camera failure) for operator verification" |
| Emergency response orchestration | ✅ simulated | "Simulated emergency-vehicle pre-emption"; no link to emergency services or real signals |
| "100 % Centralized Monitoring" | ⬜ | Do **not** claim. The prototype monitors one site at a time with up to four cameras |

## 9. Literature themes

| Theme (proposal slide 7) | Link |
|---|---|
| ITS as an alternative to road expansion (Nordstrom 2023; Ezell 2010) | Software + phones + laptop, no civil works |
| Predictive planning (Wang 2010; Milumbe 2018) | Baseline 15-minute forecast (Holt); stored history enables better models later |

## 10. Budget (proposal slide 12)

The five line items (49 000 + 33 000 + 11 000 + 7 000 + 500) total **ZMW 100 500**, not the ZMW 106 500
shown on the slide — correct this in the final report or identify the missing ZMW 6 000 item.

Actual prototype software cost: **ZMW 0** (Python, FastAPI, React, OpenCV, PostgreSQL and the IP Webcam
app are free; Ultralytics YOLO is AGPL-3.0, free for academic research). Present a *proposed vs actual*
table with your real hardware and travel costs.

## 11. Terminology (keep consistent between report and software)

| Term | Meaning in this project |
|---|---|
| Congestion score | 0–100 operational index (queue, wait, length, arrivals, growth) used by the priority engine |
| Congestion Index (CI) | (actual − free-flow travel time) / free-flow travel time — the proposal's benchmark |
| Travel Time Index (TTI) | 1 + CI |
| Adaptive control | Queue-clearance actuated greens + demand-based phase order + fairness rules |
| Fixed-time plan | Same phase order and green times every cycle regardless of demand |
| AI / SIM / NO DATA | Camera-measured / demo-model / no measurement |

## 12. To complete the evidence (field work)

1. Confirm the control type of each node; set it in *System Settings → Study Sites*.
2. Stopwatch the real signal timings at a signalised node and enter them as the fixed plan (*Evaluation*).
3. Off-peak moving-car runs → free-flow speed → set it on *Congestion Analysis*.
4. At each node: cameras + regions; AM peak, PM peak and one off-peak session; ≥ 2 manual-count validation sessions per camera.
5. Moving-car run pairs along each corridor in both directions, peak and off-peak.
6. Export CSVs and the *Evaluation* results for the report.

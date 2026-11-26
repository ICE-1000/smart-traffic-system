# Algorithms and assumptions

All parameters below are **starting assumptions for a prototype**, not calibrated values. They
are configurable at runtime and must be recalibrated on real camera measurements (Phases 6–8).

## 0. From video to measurements (`vision/`)

Per camera, at its processing rate (default 5 fps):

1. **Detection** — YOLO26-nano, COCO-pretrained. Kept classes: car, motorcycle, bus, truck
   (vehicles); person and bicycle (shown, never counted as vehicles). Class-agnostic NMS so one
   vehicle gets one box.
2. **Tracking** — ByteTrack (Ultralytics `bytetrack.yaml`). Detections down to confidence 0.1
   are passed to the tracker so it can keep existing tracks through occlusion; new tracks still
   need the tracker's `new_track_thresh`, and unconfirmed boxes below the configured minimum
   confidence are dropped. A track's class is the confidence-weighted majority over its life.
3. **Anchor point** — bottom-centre of the box (where the vehicle meets the road), normalised 0–1.
4. **Rules per tracked vehicle** (regions drawn per camera):

| Event / state | Rule |
|---|---|
| Arrival (counted once) | anchor inside approach or queue area, after ≥ 3 sightings (suppresses ID flicker) |
| Queued | anchor inside queue area and speed < 0.06 frame-widths/s (≈ stationary); stays queued while creeping inside the area |
| Waiting time | from first becoming queued until crossing the stop line |
| Departure (counted once) | anchor crosses the stop line to the side opposite the queue area; without a stop line: track lost after being in the approach |
| Lost | not seen for 2 s → stored as one `vehicle_detections` row |

5. **ApproachMeasurement** (what the engines consume):
   - queue_count = queued vehicles now; avg/max wait over them
   - queue_length_m = with stop line + measured length: projection of the furthest queued
     vehicle along the queue axis × length; otherwise Σ class lengths (car 7 m, motorcycle
     3.5 m, bus 14 m, truck 13 m incl. gaps)
   - arrival/departure rate = events in the last 60 s, per minute
   - moving_ratio, vehicles_in_view, heavy (bus+truck) / light, pedestrians_in_view

Measured on the synthetic sample (`tests/test_vision_e2e.py` and manual runs): arrivals
16/min against ≈ 15/min generated; waiting times rise through the 25 s red phase to ≈ 19 s for
the first vehicle. Real-road accuracy must be checked against manual counts (docs/TESTING.md).

## 0b. Which measurement each approach uses (`backend/app/services/runtime.py`)

| Mode | Camera online with fresh AI measurement | Otherwise |
|---|---|---|
| auto (default) | vision | demo model (badged SIM) |
| vision | vision | **none** — no fabricated values; priority gives fixed-time fallback service |
| demo | demo | demo |

## 1. Congestion score (`intelligence/congestion/engine.py`)

```
score = 100 × Σ wᵢ · clamp(xᵢ / normᵢ, 0, 1)
```

| Indicator xᵢ | Weight wᵢ | Saturates at normᵢ | Why |
|---|---|---|---|
| Vehicles waiting in queue region | 0.30 | 30 veh | Primary demand signal |
| Average waiting time of queued vehicles | 0.30 | 120 s | Captures delay, not just volume (a short queue waiting long matters) |
| Queue length | 0.20 | 180 m | Physical extent; buses/trucks occupy more road; spill-back risk |
| Arrival rate | 0.10 | 30 veh/min | Upcoming pressure |
| Net growth (arrivals − departures) | 0.10 | 15 veh/min | Queue is building, not discharging |

Categories: free < 10 ≤ light < 30 ≤ moderate < 55 ≤ heavy < 75 ≤ critical.

Count alone never determines the score: two approaches with 10 vehicles score differently if
one has waited 10 s and the other 110 s (tested in `tests/test_congestion.py`).

## 2. Priority decision (`intelligence/priority/engine.py`)

```
priority_index = 0.7 × congestion_score + 0.3 × 100 × clamp(time_since_served / starvation_s, 0, 1)
```

Rules, in order (approaches with **no data** are only eligible once unserved for
`starvation_s`, and are then served like a fixed-time plan — rule `no_data`):
1. **Starvation guard (fairness).** An approach with demand that has not had green for
   ≥ `starvation_s` (90 s) is served next, longest-starved first — prevents any approach
   monopolising green.
2. **Empty-approach skip.** No queued vehicles and no pedestrian call → not eligible…
   **unless** unserved for ≥ `max_skip_s` (180 s). Empty is never skipped forever: cameras can
   miss turning vehicles, cyclists and pedestrians.
3. Otherwise the highest index wins; ties go to the longest unserved.

Each decision returns a `reason` string built from the actual numbers, e.g.
*"North approach prioritised: highest priority index (54) from 25 queued vehicles, congestion
score 72, average wait 48s. Next: South (index 41, 18 queued)."*

## 3. Signal simulation (`intelligence/simulation/signal.py`)

```
GREEN(a) ──▶ YELLOW(a) [3 s] ──▶ ALL-RED [2 s] ──▶ GREEN(b)
```

**Queue-clearance actuated control with demand-based phase order.**
After `min_green` (10 s) a green ends only when:
- its queue has cleared and there is no pedestrian call (gap-out), or
- `max_green` (45 s) is reached, or
- the fairness (starvation) rule names another approach.

The next green goes to the approach with the highest priority index (§2); empty approaches
are skipped. If no other approach has demand, the current approach rests in green.

*Design change, documented:* the first version also ended a green whenever another approach's
priority index exceeded the current one by a margin, even while the current queue was still
discharging. The evaluation engine (§4) showed this was wrong: every switch costs yellow +
all-red + start-up time (≈ 7 s), and under balanced heavy demand the controller became far
worse than fixed time (661 s vs 144 s mean delay in a 1-hour test). The rule was removed;
`tests/test_evaluation.py::test_adaptive_not_worse_than_fixed_below_capacity_balanced` guards
against regressions.

**Emergency pre-emption (simulated).** An operator can request priority for an approach. The
current green ends after at least `preempt_min_green_s` (5 s), always through yellow and
all-red; the requested approach is then held green for the requested time.

Safety invariant checked on **every tick**: no two conflicting approaches may be non-red
(`ConflictError` otherwise). Default phasing is split (every approach conflicts with every other).
Pedestrian phases are placeholders: a call marks demand on an approach so it cannot be skipped;
dedicated walk/clearance intervals are future work.

Note: with real cameras the simulated lights do not change real traffic (the real signals do).
The simulation shows what this controller *would* do with the measured demand — decision
support, not control.

## 4. Adaptive vs fixed-time evaluation (`intelligence/evaluation/comparison.py`) — research question 2

Counterfactual design: each second, arrivals are drawn from every approach's **measured**
arrival rate (camera + AI, or the labelled demo model where no camera works) and the measured
heavy-vehicle share (smoothed over ≈ 2 min). The **same** arrivals enter two identical queue
models: one controlled by this system (§2–3), one by a fixed-time plan (order N → E → S → W,
greens configurable, default 25 s each, cycle 120 s with yellow + all-red). Differences are
therefore caused only by the signal plan.

Queue model: saturation flow 0.5 veh/s per approach (1 800 veh/h, configurable), 2 s start-up
lost time, half discharge rate during yellow. Delay = time from joining the queue to crossing
the stop line. Reported per plan: mean delay per departed vehicle, vehicle-hours of delay
(including vehicles still queued, so a plan cannot hide delay in its queue), throughput, stop
rate and maximum queues. A run restarts whenever tuning changes, so
runs are never mixed; results are saved every minute (`evaluation_snapshots`). Read results after
≈ 10 minutes.

Reproducible evidence — `python scripts/evaluate_controller.py` (5 seeds × 1 h per pattern,
synthetic demand in veh/min per approach). Mean delay per vehicle:

| Demand pattern | Adaptive | Fixed, equal split (25 s each) | Fixed, demand-tuned split |
|---|---|---|---|
| Dominant approach (14 / 3 / 1 / 0) | 29.5 s | 624.8 s (−95.3 %) | 33.4 s (−11.7 %) |
| Unbalanced (9 / 6 / 2.5 / 0.8) | 35.8 s | 280.2 s (−87.2 %) | 45.4 s (−21.3 %) |
| Mixed (8 / 2 / 5 / 3) | 33.6 s | 204.6 s (−83.6 %) | 48.7 s (−31.0 %) |
| Balanced moderate (4 each) | 28.4 s | 46.2 s (−38.5 %) | 46.2 s (−38.5 %) |
| Balanced heavy (5 each) | 40.3 s | 58.5 s (−31.1 %) | 58.5 s (−31.1 %) |
| Balanced at capacity (6 each) | 136.9 s | 126.5 s (+8.2 %) | 126.5 s (+8.2 %) |
| Light (2 / 2 / 1 / 1) | 15.3 s | 40.0 s (−61.7 %) | 40.0 s (−61.7 %) |

(percentages = adaptive relative to that fixed plan; negative = adaptive lower.)

Interpretation for the report: the largest gains come from **uneven demand** — the situation
described in the proposal's problem statement. Even against a fixed plan already tuned to the
demand, the adaptive controller reduces delay by 12–62 %, because it also skips empty approaches
and ends greens as soon as queues clear. With perfectly balanced demand at capacity both are
limited by capacity and the adaptive plan is slightly worse (more switching). For field
evaluation, set the fixed plan to the **real signal timings observed on site** (stopwatch the
cycle) so the comparison reflects the existing schedule.

## 5. Congestion Index (`intelligence/evaluation/indices.py`) — proposal benchmark

CI = (actual − free-flow travel time) / free-flow travel time; TTI = 1 + CI (Travel Time Index as
used by FHWA/TTI). At an approach, actual = free-flow + junction delay, so
CI = mean delay of departed vehicles (last 5 min) ÷ free-flow time over the monitored section
(camera queue-area length, else 100 m) at the free-flow speed (default 40 km/h — **replace with
the off-peak speed measured by moving-car runs**). Vehicles that never queued count as 0 s delay.
Delays from the demo model and from cameras are never mixed. No congested/uncongested thresholds
are imposed; CI is compared between periods and sites.

The **congestion score** (§1, 0–100) remains the operational input to priority decisions; the
**CI** is the benchmarking measure named in the proposal's methodology.

## 6. Moving-car method (`intelligence/evaluation/surveys.py`)

Wardrop & Charlesworth (1954). Test car runs with the stream (time tw; y = vehicles overtaking
minus overtaken) and against it (time ta; x = stream vehicles met):
q = (x + y)/(ta + tw); t̄ = tw − y/q; v = distance / t̄; CI = (t̄ − t_free)/t_free.
Check: q = 600 veh/h at 30 km/h over 1 km with tw = 3 min, ta = 1.5 min gives x = 35, y = 10 and
the formulas return q = 600 veh/h, t̄ = 2.0 min, v = 30 km/h (unit-tested).

## 7. Validation against manual counts

System count = vehicle tracks that entered the approach area during the session (one per
ByteTrack ID). Error % = (system − manual)/manual; accuracy = 100 − |error %|. Optional
stopwatch mean wait is compared with tracked waiting times of the same window.

## 8. Incident detection (`intelligence/incidents/detector.py`)

| Rule | Condition (defaults) |
|---|---|
| Blocked discharge (critical) | green ≥ 15 s, queue ≥ 2, no stop-line crossing for 12 s |
| Stalled vehicle | a queued vehicle stationary ≥ 240 s |
| Queue spillback | queue length ≥ 180 m |
| Camera failure | configured camera offline ≥ 30 s |

An incident opens after its condition holds 5 s and closes after 20 s of normal conditions.
Approaches without data never raise traffic incidents. Indicators for an operator to verify —
not confirmed incidents.

## 9. Peak periods and forecasting

Peak periods follow the proposal: AM 07:00–09:00, PM 16:00–19:00 (local time, Africa/Lusaka),
off-peak 06:00–22:00 otherwise, night 22:00–06:00. Short-term forecast: Holt's linear
exponential smoothing (α 0.4, β 0.2) on 1-minute mean arrival rates, 15 minutes ahead, with the
in-sample one-step mean absolute error reported — a baseline for the proposal's "predictive
planning" theme.

## 10. Demo traffic model (`backend/app/services/demo_source.py`) — SIMULATED

Used for approaches without camera data in *auto* mode and in *demo* mode. Poisson arrivals per approach
(default 9 / 6 / 2.5 / 0.8 veh/min for N/S/E/W, ±35 % slow wave), vehicle mix 70 % car, 12 %
motorcycle, 8 % bus, 10 % truck, discharge 0.6 veh/s on green after 2 s start-up loss.
These are illustrative values, **not Lusaka measurements**. Everything it produces is tagged
`source="demo"` and badged SIMULATED in the UI.

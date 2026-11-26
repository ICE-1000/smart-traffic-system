# Testing

## Automated (`python -m pytest`) — 58 tests

| File | Covers |
|---|---|
| test_congestion.py | score bounds, categories, waiting time matters (not count alone), weight validation |
| test_priority_and_signal.py | spec example (N25/S18/E2/W0 → North), empty-approach skip, pedestrian call, starvation, max-skip, **no-data fixed-time fallback**, never two non-red approaches, yellow → all-red → green order, min/max green, no monopolisation |
| test_tracking.py | polygon/line geometry, region validation, one vehicle = one arrival, queued wait ≈ real time, departure on stop-line crossing, pedestrians never counted, ID-flicker suppression, class majority vote, queue length (geometric and class-based), departure without stop line |
| test_cameras.py | sample file goes online and loops, **unreachable phone goes offline without affecting a working one**, disable/unconfigure stops receivers, stale stream → offline, URL validation, Windows file paths, credential masking |
| test_api.py | all endpoints + WebSocket, one camera per approach, regions round-trip and validation, data-source modes (vision mode never fabricates data), AI config validation, CSV export |
| test_evaluation.py | identical arrivals in both plans, adaptive beats fixed under unbalanced demand, **regression test for the controller fix**, fixed-time cycle, total delay includes vehicles still queued, Congestion Index definition, no mixing of demo/camera delays, moving-car consistency case, invalid survey input, count accuracy, incident open/clear hysteresis, no incidents without data, camera-failure timing, stalled vehicle, spillback, safe emergency pre-emption |
| test_api.py (additions) | study sites seeded and switchable, evaluation endpoints and validation, surveys + CSV, validation sessions, peak periods, forecast, incidents, pre-emption, CI config, **migration 0001→0002 keeps existing rows** |
| test_vision_e2e.py (slow) | sample video → receiver → YOLO26 + ByteTrack → queued vehicles measured |

`python -m pytest -m "not slow"` skips the end-to-end YOLO test.

## Field protocol (uses the Field Surveys page)
1. Off-peak moving-car runs on each corridor → free-flow speed → *Congestion Analysis → Congestion Index*.
2. Peak sessions (07:00–09:00, 16:00–19:00) at each node with cameras running.
3. During each session, a 10–15 min tally count per camera → *Field Surveys → Validation*.
4. At signalised nodes, stopwatch the real signal cycle → *Evaluation* fixed plan → run ≥ 30 min.
5. Export CSVs (Analytics, moving-car) and the Evaluation results for the report.

## Manual checks with real phones (do these on site)
| # | Test | Expected |
|---|---|---|
| 1 | Turn one phone's Wi-Fi off | Its window → OFFLINE within ~5 s; others keep running; turn back on → ONLINE again without touching the laptop |
| 2 | Close the app on a phone in *Cameras only* mode | That approach shows NO DATA; Priority page shows "fixed-time fallback" for it |
| 3 | Count manually for 10 minutes (tally counter) | Compare with `/api/vision/detections` rows for that camera; record the error % |
| 4 | Stopwatch the waiting time of 5 cars | Compare with the Live Monitoring avg wait / stored `wait_s` |
| 5 | Two feeds, then four feeds | System Settings → processing fps holds the configured rate; CPU below ~85 % |
| 6 | Stop the backend while the dashboard is open | Status turns red "Backend offline"; restart → reconnects automatically |
| 7 | Invalid stream address / region polygon with 2 points | Rejected with a clear message |

Record results in a table for the project report — real-road accuracy is the main open
question (docs/LIMITATIONS.md).

## Performance
`python scripts/benchmark.py` — on the development machine here (2 vCPU, no GPU):
YOLO26n ≈ 20 ms @320 px, 36 ms @480 px, 60 ms @640 px per frame. At 320 px most vehicles in
the sample were missed, so 480–640 px is the practical range. **Re-run on your laptop**; Intel
integrated graphics can be faster with an OpenVINO export (see the script's output).

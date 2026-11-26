# vision/ — computer-vision pipeline

| Module | Responsibility |
|---|---|
| `detection/detector.py` | `YoloTracker`: Ultralytics YOLO26n + ByteTrack per camera, COCO class filter, agnostic NMS, weights auto-download to `models/`, global inference lock |
| `tracking/state.py` | `ApproachTracker`: per-track state (passing / approaching / queued / departed), arrivals, departures, waits, queue length → `ApproachMeasurement(source="vision")` |
| `regions/config.py` | `RegionConfig` (approach polygon, queue polygon, stop line, real length) + geometry helpers |
| `processing/service.py` | `VisionService` / `VisionWorker`: one thread per online camera at its processing fps |
| `processing/overlay.py` | Draws regions and labelled boxes onto frames for the MJPEG stream |

Rules and assumptions: docs/ALGORITHMS.md §0.

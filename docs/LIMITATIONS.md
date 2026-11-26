# Known limitations

## Not validated on real Lusaka traffic yet
Everything was tested with synthetic sample footage and unit tests. Detection, tracking and
queue estimation must be checked against manual counts on real roads (docs/TESTING.md) before
any conclusions are drawn. Expect lower accuracy:
- at night, in rain, or into low sun;
- with heavy occlusion (camera too low, long queues hiding each other);
- for minibuses and vehicle types underrepresented in the COCO training data (a Hiace minibus
  may be labelled car/bus/truck). Fine-tuning on local images would help.

## Measurement assumptions
- "Queued" = nearly stationary inside the queue area. Slow-moving congested traffic that keeps
  creeping may be classified as approaching.
- Queue length without a measured region length is estimated from vehicle types.
- One camera per approach; vehicles beyond the camera's view are not counted (queues longer
  than the view are under-estimated — the score saturates at the configured norm anyway).
- Turning movements are not distinguished; split phasing serves all movements of an approach.
- Pedestrian demand is a manual placeholder (button); detected pedestrians are shown but do not
  create calls.

## Evaluation (RQ2)
- The adaptive vs fixed-time comparison is a **model** (queue model driven by measured arrival rates),
  not a field trial. It does not include driver behaviour, lane changes, turning conflicts,
  pedestrians or downstream blocking.
- Saturation flow (0.5 veh/s) is an assumption — calibrate from discharge counts at the stop line.
- Gains are largest with unbalanced demand; with balanced demand at capacity the adaptive plan is
  slightly worse than fixed time (docs/ALGORITHMS.md §4).
- At roundabouts, signal-related results describe a hypothetical signalised operation.

## Congestion Index, incidents, forecast
- CI depends on the free-flow speed and section length; measure them (moving-car, tape/pacing).
- Incident rules are indicators; thresholds need tuning per site; no automatic link to
  emergency services. Emergency pre-emption is simulated only.
- The forecast is a baseline (Holt smoothing on recent minutes); it does not learn daily or weekly
  patterns.
- One active study site at a time; data from different sites is kept separate.

## Signal simulation
- Simulated only. With real cameras the simulated lights do not change the real traffic, so the
  live simulation shows what the controller *would* decide; the effect of its decisions is
  estimated by the evaluation model (above), not observed.
- Split phasing only by default; compatible movements (e.g. N+S together) need an engineering
  review before `compatible_pairs` is used.
- Timings (min/max green, yellow, all-red) are illustrative, not RTSA/local standards.

## System
- Single intersection, single laptop, no user accounts ("operator" is a placeholder). Do not
  expose port 8000 or 5173 to the internet.
- Phone streams are unencrypted on the local network; credentials in URLs are masked in the UI
  but stored in the database in clear text.
- Phone heat, battery and app crashes are the most likely field failures — use chargers and
  shade.

## Licensing
- Ultralytics YOLO (and YOLO26 weights) are **AGPL-3.0**: fine for academic research and
  open-source publication of the whole project. Internal government/business use or a
  commercial product requires an Ultralytics Enterprise licence (or replacing the detector with
  a permissively licensed model).
- The synthetic sample video is generated from an image bundled with Ultralytics; it is for
  testing only.

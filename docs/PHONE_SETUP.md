# Connecting Android phones

## 1. Network
Phones and laptop must be on the **same network**:
- **Laptop hotspot (recommended for field tests):** Windows Settings → Network & internet →
  Mobile hotspot → On. Connect each phone to it. Laptop is usually `192.168.137.1`; phones get
  `192.168.137.x`.
- **Router Wi-Fi:** all devices on the same router. Some public/campus networks block
  device-to-device traffic ("client isolation") — use the hotspot then.

## 2. Streaming app
Any app that shows an **RTSP** or **HTTP/MJPEG** address works; the system does not depend on a
particular app. Common choice: *IP Webcam* (Pavel Khlebovich, Google Play). Start the server in
the app and note the address it displays, e.g. `http://192.168.137.21:8080`.

| App shows | Paste into Camera Management |
|---|---|
| IP Webcam `http://IP:8080` | `http://IP:8080/video` (MJPEG — simplest) or `rtsp://IP:8080/h264_ulaw.sdp` (H.264, less Wi-Fi bandwidth) |
| Other RTSP apps | the full `rtsp://…` address they display (add `user:password@` if the app requires login — it is masked on the dashboard) |

Test the address first in VLC (Media → Open Network Stream). If VLC can't play it, the
dashboard can't either.

Recommended app settings: 640×480 or 1280×720, 10–15 fps, keep screen on / disable battery
optimisation for the app, phone on a charger.

## 3. In the dashboard
1. **Camera Management** → select CAM-01 (North) → paste the address → Save.
   Status goes *connecting* → *online* (it retries automatically every 1–30 s if not).
2. **Detection Regions** (same page): click *Approach area* and outline the road coming
   towards the junction; *Queue area* — the stretch where cars wait; *Stop line* — two points
   across the lanes; enter the real length of the queue area in metres (pace it out). Save.
3. Repeat for CAM-02 (South), CAM-03 (East), CAM-04 (West).
4. **Live Monitoring** shows each feed with boxes: amber = queued, blue = approaching,
   green = departed, white = pedestrian.

## 4. Mounting the phone
- High and looking **along** the approach towards the stop line, so waiting vehicles don't hide
  each other (a footbridge, first-floor window or pole mount — with permission, and never
  obstructing traffic or pedestrians).
- Landscape, steady (tripod/clamp); wind shake breaks the "stationary vehicle" rule.
- Avoid pointing into low sun; at night street lighting matters.
- Respect privacy: the system stores counts and track summaries only, not video. Check local
  rules and get permission before filming public roads.

## Troubleshooting
| Symptom | Check |
|---|---|
| *offline — Cannot open stream* | Address typo; phone screen off / app in background; different network; Windows firewall is not the issue (the laptop makes outgoing connections) |
| Online but choppy | Lower app resolution/fps; prefer the RTSP (H.264) address on busy Wi-Fi |
| Vehicles not detected | Camera too far/too high; raise inference size to 640 in System Settings; lower min confidence to 0.25 |
| Queue never forms | Queue area doesn't cover where cars stop; camera shaking |
| CPU at 100 % | Run `python scripts/benchmark.py`; lower processing fps (2–3 is enough) or width |

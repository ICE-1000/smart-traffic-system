"""Benchmark detection + tracking on THIS machine and recommend settings.

    python scripts/benchmark.py                       # sample video, yolo26n, 320/480/640
    python scripts/benchmark.py --video path/to/phone_clip.mp4 --frames 60
    python scripts/benchmark.py --model models/yolo26n_openvino_model --device intel:gpu

Prints ms/frame per inference size, CPU load, and the processing fps you can
afford per camera for 2 and 4 feeds (keeping 30 % headroom for decoding,
the API and the dashboard). Numbers are only valid for the machine it runs on.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(ROOT / "samples" / "synthetic_approach.mp4"))
    ap.add_argument("--model", default="yolo26n.pt")
    ap.add_argument("--device", default=None)
    ap.add_argument("--frames", type=int, default=40)
    ap.add_argument("--sizes", default="320,480,640")
    ap.add_argument("--width", type=int, default=640, help="frame width fed to the model (processing_width)")
    args = ap.parse_args()

    import cv2
    import psutil

    from vision.detection.detector import YoloTracker

    if not Path(args.video).exists():
        print(f"Video not found: {args.video}\nRun: python scripts/make_sample_video.py")
        sys.exit(1)
    cap = cv2.VideoCapture(args.video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or args.frames
    # consecutive frames from the middle of the clip (tracking needs continuity; the start may be empty)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total // 3))
    frames = []
    while len(frames) < args.frames:
        ok, f = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            if not frames and not cap.read()[0]:
                print("Could not read frames")
                sys.exit(1)
            continue
        if f.shape[1] > args.width:
            f = cv2.resize(f, (args.width, int(f.shape[0] * args.width / f.shape[1])))
        frames.append(f)

    print(f"CPU: {psutil.cpu_count(logical=False)} cores / {psutil.cpu_count()} threads · RAM {psutil.virtual_memory().total / 1e9:.1f} GB")
    print(f"Model {args.model} · device {args.device or 'auto'} · frame width {args.width}px · {len(frames)} frames\n")
    print(f"{'imgsz':>6} {'mean ms':>8} {'p90 ms':>7} {'CPU %':>6}   max fps/camera @2 feeds  @4 feeds   detections/frame")
    results = []
    for size in [int(s) for s in args.sizes.split(",")]:
        trk = YoloTracker(args.model, imgsz=size, device=args.device)
        trk.track(frames[0])  # warm-up
        psutil.cpu_percent(None)
        times, dets = [], []
        for f in frames:
            d = trk.track(f)
            times.append(trk.last_ms)
            dets.append(len(d))
        cpu = psutil.cpu_percent(None)
        mean = statistics.mean(times)
        p90 = sorted(times)[int(0.9 * (len(times) - 1))]
        budget = 0.7 * 1000.0  # 30 % headroom
        fps2, fps4 = budget / (p90 * 2), budget / (p90 * 4)
        results.append((size, mean, fps2, fps4))
        print(f"{size:>6} {mean:>8.1f} {p90:>7.1f} {cpu:>6.0f}   {fps2:>18.1f}  {fps4:>8.1f}   {statistics.mean(dets):>8.1f}")

    print("\nRecommendation (Camera Management → processing fps; System Settings → inference size):")
    good = [r for r in results if r[3] >= 2.0] or [results[0]]
    size, _, fps2, fps4 = max(good, key=lambda r: r[0])
    print(f"  inference size {size}px · {min(fps2, 8):.0f} fps per camera with 2 feeds · {min(fps4, 8):.1f} fps with 4 feeds")
    print("  2–5 fps per approach is enough for queue counting; vehicles waiting at a light move slowly.")
    print("  If 4 feeds fall below ~2 fps, try OpenVINO on Intel graphics:")
    print("    yolo export model=models/yolo26n.pt format=openvino")
    print("    then set model = models/yolo26n_openvino_model and device = intel:gpu, and re-run this benchmark.")


if __name__ == "__main__":
    main()

"""Generate SYNTHETIC sample footage for development and testing.

No real traffic footage ships with the project. This script animates the
sample bus photo bundled with Ultralytics along a drawn road with a simple
red/green cycle, so the receiver → YOLO → tracking → queue → priority chain
can be exercised end-to-end without phones. The video is stamped
"SYNTHETIC SAMPLE" and the dashboard labels any file:// source as SAMPLE FOOTAGE.

    python scripts/make_sample_video.py                    # samples/synthetic_approach.mp4
    python scripts/make_sample_video.py --seconds 90 --seed 2 --out samples/other.mp4

Suggested regions for this video are printed at the end (paste in Camera Management).
"""
from __future__ import annotations

import argparse
import os
import random
from pathlib import Path

import cv2
import numpy as np

W, H, FPS = 960, 540, 15
STOP_Y = 470
LANES = (400, 560)


def bus_sprite() -> np.ndarray:
    import ultralytics

    img = cv2.imread(os.path.join(os.path.dirname(ultralytics.__file__), "assets", "bus.jpg"))
    return img[228:745, 15:805]  # the bus in the sample photo (BGR)


def background() -> np.ndarray:
    bg = np.full((H, W, 3), (70, 92, 60), np.uint8)  # verge
    cv2.rectangle(bg, (300, 0), (660, H), (64, 64, 64), -1)  # road
    rng = np.random.default_rng(0)
    noise = rng.integers(-6, 6, (H, 360, 3), dtype=np.int16)
    bg[:, 300:660] = np.clip(bg[:, 300:660].astype(np.int16) + noise, 0, 255).astype(np.uint8)
    for y in range(0, STOP_Y - 10, 40):
        cv2.line(bg, (480, y), (480, y + 22), (220, 220, 220), 3)
    cv2.line(bg, (300, STOP_Y), (660, STOP_Y), (240, 240, 240), 6)
    for x in range(310, 650, 26):  # zebra after the stop line
        cv2.rectangle(bg, (x, STOP_Y + 14), (x + 14, STOP_Y + 52), (225, 225, 225), -1)
    return bg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="samples/synthetic_approach.mp4")
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    random.seed(args.seed)
    sprite = bus_sprite()
    bg = background()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    n = args.seconds * FPS
    cycle = 40 * FPS  # red 25 s, green 15 s
    vehicles: list[dict] = []
    next_arrival = 0
    for f in range(n):
        green = (f % cycle) >= 25 * FPS
        if f >= next_arrival:
            vehicles.append({"lane": random.choice(LANES), "y": -60.0, "v": 5.0 + random.random() * 2})
            next_arrival = f + int(FPS * random.uniform(2.5, 5.5))
        frame = bg.copy()
        for lane in LANES:
            lane_v = sorted([v for v in vehicles if v["lane"] == lane], key=lambda v: -v["y"])
            front_limit = None
            for v in lane_v:
                scale = 0.5 + 0.5 * max(0.0, v["y"]) / H
                h = int(115 * scale)
                limit = STOP_Y - 6 if not green and v["y"] <= STOP_Y - 6 else 10_000
                if front_limit is not None:
                    limit = min(limit, front_limit)
                v["y"] = min(v["y"] + v["v"], limit)
                front_limit = v["y"] - h - 14
                v["h"] = h
        vehicles = [v for v in vehicles if v["y"] - v.get("h", 100) < H]
        for v in sorted(vehicles, key=lambda v: v["y"]):
            h = v["h"]
            w = int(h * sprite.shape[1] / sprite.shape[0])
            img = cv2.resize(sprite, (w, h), interpolation=cv2.INTER_AREA)
            x0, y0 = v["lane"] - w // 2, int(v["y"]) - h
            ys, ye = max(0, y0), min(H, y0 + h)
            xs, xe = max(0, x0), min(W, x0 + w)
            if ye > ys and xe > xs:
                frame[ys:ye, xs:xe] = img[ys - y0:ye - y0, xs - x0:xe - x0]
        col = (60, 220, 60) if green else (60, 60, 230)
        cv2.circle(frame, (700, STOP_Y - 30), 14, col, -1)
        cv2.putText(frame, "SYNTHETIC SAMPLE", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2, cv2.LINE_AA)
        vw.write(frame)
    vw.release()
    print(f"wrote {out} ({args.seconds}s @ {FPS} fps)")
    print('Suggested regions: {"approach": [[0.31,0],[0.69,0],[0.69,0.87],[0.31,0.87]], '
          '"queue": [[0.31,0.3],[0.69,0.3],[0.69,0.87],[0.31,0.87]], '
          '"stop_line": [[0.31,0.875],[0.69,0.875]], "queue_length_m": 45}')


if __name__ == "__main__":
    main()

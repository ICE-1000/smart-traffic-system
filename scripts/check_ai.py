"""Step-by-step AI diagnostic. Run from the project folder with the venv active:

    python scripts\\check_ai.py

Checks Python, every AI library, the model file, detection on a test image,
tracking on the sample video, and video decoding. Each failed step prints the
exact fix. Saves the detected test image as check_ai_result.jpg.
"""
from __future__ import annotations

import importlib
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"
failed = False


def step(ok: bool | None, label: str, detail: str = "", fix: str = "") -> None:
    global failed
    tag = OK if ok else (WARN if ok is None else BAD)
    print(f"{tag} {label}" + (f" — {detail}" if detail else ""))
    if fix and not ok:
        print(f"       FIX: {fix}")
    if ok is False:
        failed = True


def main() -> None:
    print("Smart Traffic Management and ITS — AI check\n")
    v = sys.version_info
    step(v[:2] in ((3, 11), (3, 12), (3, 13)) or None if v[:2] >= (3, 10) else False, "Python",
         f"{platform.python_version()} ({sys.executable})",
         "Install Python 3.12 from python.org and recreate the venv: python -m venv .venv")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    step(True if in_venv else None, "Virtual environment", "active" if in_venv else "NOT active",
         "Run .venv\\Scripts\\activate first")

    from vision.detection.selftest import VC_REDIST, hint_for

    mods = {}
    for name, pip in (("numpy", "numpy"), ("cv2", "opencv-python-headless"), ("torch", "torch"),
                      ("ultralytics", "ultralytics"), ("lap", "lap")):
        try:
            m = importlib.import_module(name)
            mods[name] = m
            step(True, f"import {name}", getattr(m, "__version__", ""))
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            fix = hint_for(msg)
            if name == "torch" and ("dll" in msg.lower() or "winerror" in msg.lower()):
                fix = f"Install the Microsoft Visual C++ Redistributable (x64): {VC_REDIST} — then restart Windows."
            elif "No module named" in msg:
                fix = f"pip install {pip}   (or: pip install -r backend\\requirements.txt)"
            if name == "lap":
                step(None, f"import {name}", msg, fix + "  — optional: the system uses a fallback tracker without it")
            else:
                step(False, f"import {name}", msg[:200], fix)

    if "torch" in mods:
        t = mods["torch"]
        step(True, "PyTorch device", "CUDA GPU available" if t.cuda.is_available() else "CPU (normal for this laptop)")

    model = ROOT / "models" / "yolo26n.pt"
    if model.exists():
        size = model.stat().st_size
        step(size > 4_000_000, "Model file", f"{model} ({size / 1e6:.1f} MB)",
             "File looks incomplete — replace models\\yolo26n.pt with the one from the project zip")
    else:
        step(None, "Model file", "models\\yolo26n.pt missing — will try to download",
             "Copy yolo26n.pt from the project zip into the models folder")

    if failed or "ultralytics" not in mods:
        print("\nStopped: fix the [FAIL] items above, then run this check again.")
        sys.exit(1)

    from vision.detection.selftest import run_selftest

    info, jpg = run_selftest("yolo26n.pt")
    if info["ok"]:
        step(True, "Detection on test image", f"{info['detections']} objects {info['classes']} in {info['infer_ms']} ms "
                                              f"(model load {info['load_ms']} ms)")
        if jpg:
            (ROOT / "check_ai_result.jpg").write_bytes(jpg)
            print(f"       Saved {ROOT / 'check_ai_result.jpg'} — open it to see the boxes")
    else:
        step(False, "Detection on test image", info.get("error", ""), info.get("hint", ""))

    import cv2

    from vision.detection.detector import YoloTracker

    video = ROOT / "samples" / "synthetic_approach.mp4"
    cap = cv2.VideoCapture(str(video))
    ok, _ = cap.read()
    step(bool(ok), "Video decoding (OpenCV)", str(video) if ok else "cannot read sample video",
         "Run: python scripts\\make_sample_video.py   (or reinstall opencv-python-headless)")
    if ok and info["ok"]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 300)
        trk = YoloTracker("yolo26n.pt")
        ids: set[int] = set()
        t0 = time.perf_counter()
        for _ in range(10):
            ok, f = cap.read()
            if not ok:
                break
            ids |= {d.track_id for d in trk.track(f) if d.track_id is not None}
        ms = (time.perf_counter() - t0) * 100
        step(bool(ids), "Tracking on sample video", f"{len(ids)} tracked objects, mode {trk.mode}, ~{ms:.0f} ms/frame",
             "Send this output for help")
        if trk.mode != "bytetrack":
            print(f"       note: ByteTrack unavailable ({trk.fallback_reason}); using the IoU fallback tracker")

    print("\nRESULT:", "AI is working. Start the backend and set a camera to file://samples/synthetic_approach.mp4"
          if not failed else "Fix the [FAIL] items above and run again.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

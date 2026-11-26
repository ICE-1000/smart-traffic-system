"""AI self-test: proves the YOLO model works on this machine, without any camera.

Loads the configured model, runs detection on samples/test_image.jpg (a street
photo bundled with the project), and returns the result, timing and an
annotated image. Common failures are translated into a concrete fix.
"""
from __future__ import annotations

import platform
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_IMAGE = ROOT / "samples" / "test_image.jpg"

VC_REDIST = "https://aka.ms/vs/17/release/vc_redist.x64.exe"


def hint_for(err: str) -> str:
    e = err.lower()
    if "winerror 126" in e or "winerror 193" in e or "dll load failed" in e or "c10.dll" in e or "fbgemm" in e:
        return ("PyTorch cannot load its Windows DLLs. Install the Microsoft Visual C++ Redistributable (x64) from "
                f"{VC_REDIST}, restart the computer, then start the backend again.")
    if "no module named 'torch'" in e or "no module named 'ultralytics'" in e or "no module named 'cv2'" in e:
        return "AI libraries are not installed in this environment. Activate the venv and run: pip install -r backend\\requirements.txt"
    if "lap" in e and ("module" in e or "import" in e):
        return "The tracking helper 'lap' is missing: pip install lap  (the system falls back to a simpler tracker meanwhile)."
    if "numpy" in e and ("version" in e or "abi" in e or "compiled" in e):
        return "NumPy version conflict: pip install --force-reinstall -r backend\\requirements.txt"
    if "no such file" in e or "not found" in e or "does not exist" in e or "download" in e:
        return ("Model weights not found and could not be downloaded. Put yolo26n.pt in the project's models folder "
                "(it is included in the project zip).")
    if "cuda" in e or "device" in e:
        return "The configured device is not available. In System Settings → AI Detection, clear the Device field (auto) and Apply."
    if "memory" in e:
        return "Not enough memory. Close other programs, or set the inference size to 480 in System Settings."
    return "Run  python scripts\\check_ai.py  in the project folder and send the output."


def run_selftest(model_name: str, device: str | None = None, imgsz: int = 640, conf: float = 0.35) -> tuple[dict, bytes | None]:
    info: dict = {"ok": False, "ts": time.time(), "model": model_name, "device": device or "auto", "imgsz": imgsz,
                  "python": platform.python_version(), "platform": platform.platform(terse=True)}
    try:
        import cv2

        t0 = time.perf_counter()
        from vision.detection.detector import COCO_CLASSES, resolve_model_path

        from ultralytics import YOLO

        import torch

        info["torch"] = torch.__version__
        info["model_path"] = resolve_model_path(model_name)
        model = YOLO(info["model_path"])
        info["load_ms"] = round((time.perf_counter() - t0) * 1000)
        img = cv2.imread(str(TEST_IMAGE))
        if img is None:
            raise FileNotFoundError(f"Test image not found: {TEST_IMAGE}")
        kw = dict(classes=list(COCO_CLASSES), conf=conf, imgsz=imgsz, verbose=False)
        if device:
            kw["device"] = device
        model.predict(img, **kw)  # warm-up
        t1 = time.perf_counter()
        res = model.predict(img, **kw)[0]
        info["infer_ms"] = round((time.perf_counter() - t1) * 1000, 1)
        names = [COCO_CLASSES.get(int(c), str(int(c))) for c in res.boxes.cls.cpu().numpy()] if res.boxes is not None else []
        info["detections"] = len(names)
        info["classes"] = {n: names.count(n) for n in sorted(set(names))}
        try:  # tracking support (ByteTrack needs the 'lap' package)
            import lap  # noqa: F401

            info["tracker"] = "bytetrack"
        except Exception:
            info["tracker"] = "iou-fallback"
            info["tracker_note"] = "Package 'lap' unavailable — the simpler IoU tracker will be used (pip install lap)."
        info["ok"] = len(names) > 0
        if not info["ok"]:
            info["error"] = "Model loaded but detected nothing on the test image."
            info["hint"] = "Check that the model file is the official yolo26n.pt (about 5.5 MB)."
        ok, jpg = cv2.imencode(".jpg", res.plot(), [cv2.IMWRITE_JPEG_QUALITY, 80])
        return info, (jpg.tobytes() if ok else None)
    except Exception as e:  # report, never crash the backend
        info["error"] = f"{type(e).__name__}: {e}"[:500]
        info["trace"] = traceback.format_exc(limit=3)[-1500:]
        info["hint"] = hint_for(info["error"] + info["trace"])
        return info, None


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    r, _ = run_selftest("yolo26n.pt")
    print(r)

"""OpenCV stream receiver — one thread per camera.

* Connects to RTSP / HTTP (MJPEG) phone streams, or loops a local file
  (sample footage).
* Keeps only the most recent frame (no growing buffers / latency build-up).
* grab()s every frame to stay current, but only retrieve()s (colour-converts)
  frames at the rate somebody actually needs them.
* On failure: reports the error and reconnects with exponential back-off
  (1 s → 30 s). A dead camera never affects the others.
"""
from __future__ import annotations

import os

# Must be set before cv2 opens any FFmpeg capture: RTSP over TCP is far more
# reliable than UDP on phone hotspots / busy Wi-Fi.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import logging  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from cameras.configuration import file_url_to_path, is_sample  # noqa: E402

log = logging.getLogger("cameras.receiver")


@dataclass
class Frame:
    image: np.ndarray
    ts: float
    seq: int


class CameraReceiver(threading.Thread):
    BACKOFF_MAX_S = 30.0
    READ_FAILS_BEFORE_RECONNECT = 25

    def __init__(self, camera: dict, manager, retrieve_fps: float = 12.0) -> None:
        super().__init__(name=f"rx-{camera['id']}", daemon=True)
        self.camera = camera
        self.camera_id = camera["id"]
        self.url = camera["stream_url"]
        self.sample = is_sample(self.url)
        self.manager = manager
        self.retrieve_interval = 1.0 / max(retrieve_fps, camera.get("processing_fps", 5.0))
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frame: Frame | None = None
        self._seq = 0
        self.fps = 0.0
        self.resolution: tuple[int, int] | None = None
        self.reconnects = 0

    # ---------------------------------------------------------------- api
    def latest(self) -> Frame | None:
        with self._lock:
            return self._frame

    def stop(self) -> None:
        self._stop.set()

    # ---------------------------------------------------------------- loop
    def _open(self) -> cv2.VideoCapture:
        if self.sample:
            return cv2.VideoCapture(file_url_to_path(self.url))
        params = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000]
        try:
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG, params)
        except TypeError:  # very old OpenCV without params overload
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            self.manager.report_connecting(self.camera_id)
            cap = self._open()
            if not cap.isOpened():
                cap.release()
                self.manager.report_error(self.camera_id, f"Cannot open stream — retrying in {backoff:.0f}s")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, self.BACKOFF_MAX_S)
                self.reconnects += 1
                continue
            backoff = 1.0
            self._read_loop(cap)
            cap.release()
            if not self._stop.is_set():
                self.reconnects += 1
                self.manager.report_error(self.camera_id, "Stream lost — reconnecting")
                self._stop.wait(1.0)
        self.manager.report_stopped(self.camera_id)

    def _read_loop(self, cap: cv2.VideoCapture) -> None:
        fails = 0
        last_retrieve = 0.0
        frames_in_window, window_start = 0, time.monotonic()
        file_fps = cap.get(cv2.CAP_PROP_FPS) if self.sample else 0
        frame_period = 1.0 / file_fps if self.sample and file_fps and file_fps < 120 else 0.0
        next_due = time.monotonic()
        while not self._stop.is_set():
            if not cap.grab():
                if self.sample:  # loop sample footage
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    if cap.grab():
                        fails = 0
                    else:
                        return
                else:
                    fails += 1
                    if fails >= self.READ_FAILS_BEFORE_RECONNECT:
                        return
                    time.sleep(0.02)
                    continue
            fails = 0
            now = time.monotonic()
            frames_in_window += 1
            if now - window_start >= 2.0:
                self.fps = frames_in_window / (now - window_start)
                frames_in_window, window_start = 0, now
            if now - last_retrieve >= self.retrieve_interval:
                ok, img = cap.retrieve()
                if ok and img is not None:
                    last_retrieve = now
                    self._seq += 1
                    with self._lock:
                        self._frame = Frame(img, time.time(), self._seq)
                    self.resolution = (img.shape[1], img.shape[0])
                    self.manager.report_frame(self.camera_id, self.fps)
            if frame_period:  # play files in real time
                next_due += frame_period
                delay = next_due - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_due = time.monotonic()

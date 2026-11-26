"""Camera manager: owns one CameraReceiver thread per enabled camera and
tracks honest connection status for the dashboard.

Status values:
    not_configured  no stream address
    disabled        switched off in configuration
    connecting      opening the stream
    online          frames arriving (last frame < STALE_S ago)
    offline         open failed / stream lost / frames stopped
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Literal

Status = Literal["not_configured", "disabled", "offline", "connecting", "online"]
STALE_S = 5.0


@dataclass
class CameraStatus:
    camera_id: str
    status: Status
    detail: str
    last_seen: float | None = None
    camera_fps: float = 0.0
    is_sample: bool = False
    resolution: list[int] | None = None
    reconnects: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class CameraManager:
    def __init__(self, start_receivers: bool = True) -> None:
        self._status: dict[str, CameraStatus] = {}
        self._receivers: dict[str, "CameraReceiver"] = {}  # noqa: F821
        self._config: dict[str, dict] = {}
        self._lock = threading.RLock()
        self.start_receivers = start_receivers

    # ------------------------------------------------------------ lifecycle
    def sync(self, cameras: list[dict]) -> None:
        """Start, restart or stop receivers so they match the configuration."""
        from cameras.configuration import is_sample
        from cameras.receiver import CameraReceiver

        with self._lock:
            wanted = {c["id"]: c for c in cameras}
            for cid in list(self._receivers):
                c = wanted.get(cid)
                old = self._config.get(cid)
                key = lambda x: (x["stream_url"], x["enabled"], x["processing_fps"])  # noqa: E731
                if c is None or not c["enabled"] or not c["stream_url"] or (old and key(old) != key(c)):
                    self._receivers.pop(cid).stop()
            for cid in list(self._status):
                if cid not in wanted:
                    del self._status[cid]
            for cid, c in wanted.items():
                self._config[cid] = c
                if not c["enabled"]:
                    self._status[cid] = CameraStatus(cid, "disabled", "Camera disabled in configuration")
                elif not c["stream_url"]:
                    self._status[cid] = CameraStatus(cid, "not_configured", "No stream address configured")
                elif cid not in self._receivers:
                    self._status[cid] = CameraStatus(cid, "connecting", "Starting receiver", is_sample=is_sample(c["stream_url"]))
                    if self.start_receivers:
                        rx = CameraReceiver(c, self)
                        self._receivers[cid] = rx
                        rx.start()
            for cid in list(self._config):
                if cid not in wanted:
                    del self._config[cid]

    def reconnect(self, camera_id: str) -> bool:
        with self._lock:
            rx = self._receivers.pop(camera_id, None)
            if rx:
                rx.stop()
            cams = list(self._config.values())
        self.sync(cams)
        return camera_id in self._receivers

    def stop_all(self) -> None:
        with self._lock:
            for rx in self._receivers.values():
                rx.stop()
            self._receivers.clear()

    def receiver(self, camera_id: str):
        return self._receivers.get(camera_id)

    # ------------------------------------------------------------ hooks (receiver threads)
    def _get(self, cid: str) -> CameraStatus | None:
        return self._status.get(cid)

    def report_connecting(self, camera_id: str) -> None:
        with self._lock:
            st = self._get(camera_id)
            if st and st.status != "online":
                st.status, st.detail = "connecting", "Opening stream"

    def report_frame(self, camera_id: str, fps: float) -> None:
        st = self._get(camera_id)
        if not st:
            return
        rx = self._receivers.get(camera_id)
        st.status = "online"
        st.detail = "Sample footage (not live)" if st.is_sample else "Receiving frames"
        st.last_seen = time.time()
        st.camera_fps = round(fps, 1)
        if rx:
            st.resolution = list(rx.resolution) if rx.resolution else None
            st.reconnects = rx.reconnects

    def report_error(self, camera_id: str, detail: str) -> None:
        with self._lock:
            st = self._get(camera_id)
            if st:
                st.status, st.detail, st.camera_fps = "offline", detail, 0.0

    def report_stopped(self, camera_id: str) -> None:
        pass

    # ------------------------------------------------------------ views
    def statuses(self) -> dict[str, dict]:
        now = time.time()
        out = {}
        for k, v in list(self._status.items()):
            if v.status == "online" and v.last_seen and now - v.last_seen > STALE_S:
                v.status, v.detail, v.camera_fps = "offline", f"No frames for {now - v.last_seen:.0f}s", 0.0
            out[k] = v.to_dict()
        return out

    def is_online(self, camera_id: str) -> bool:
        st = self.statuses().get(camera_id)
        return bool(st and st["status"] == "online")

    def online_count(self) -> int:
        return sum(1 for s in self.statuses().values() if s["status"] == "online")

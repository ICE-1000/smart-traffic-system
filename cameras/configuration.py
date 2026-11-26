"""Camera configuration schema and helpers.

Stream addresses differ per phone/app (for example IP Webcam shows
rtsp://<phone-ip>:8080/h264_ulaw.sdp and also http://<phone-ip>:8080/video),
so every camera is configured individually and nothing is hard-coded.

file:// URLs point at local video files. They are treated as SAMPLE
FOOTAGE and labelled as such on the dashboard — never as live feeds.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, Field, field_validator

ApproachName = Literal["north", "south", "east", "west"]
ALLOWED_SCHEMES = ("rtsp://", "rtsps://", "http://", "https://", "file://")


class CameraConfig(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    name: str = Field(min_length=1, max_length=80)
    approach: ApproachName
    stream_url: str = ""
    enabled: bool = True
    processing_width: int = Field(640, ge=160, le=1920)
    processing_fps: float = Field(5.0, gt=0, le=30)

    @field_validator("stream_url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        v = v.strip()
        if v and not v.lower().startswith(ALLOWED_SCHEMES):
            raise ValueError("stream_url must start with rtsp://, rtsps://, http://, https:// or file://")
        return v


_CRED = re.compile(r"^(?P<scheme>[a-z]+://)(?P<user>[^:@/]+):(?P<pw>[^@/]+)@", re.I)


def mask_credentials(url: str) -> str:
    """Hide passwords embedded in stream URLs before they leave the backend."""
    return _CRED.sub(lambda m: f"{m['scheme']}{m['user']}:***@", url)


def is_sample(url: str) -> bool:
    return url.lower().startswith("file://")


def file_url_to_path(url: str) -> str:
    """file:///C:/videos/a.mp4 -> C:/videos/a.mp4 ; file:///home/x/a.mp4 -> /home/x/a.mp4.
    Relative paths (file://samples/a.mp4) resolve against the repository root."""
    p = urlparse(url)
    path = unquote((p.netloc or "") + p.path)
    if re.match(r"^/[A-Za-z]:", path):  # Windows drive letter: already absolute
        return path[1:]
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path(__file__).resolve().parents[1] / path
    return str(candidate)

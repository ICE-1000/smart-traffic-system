"""Application settings, read from environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load_dotenv() -> None:
    env = ROOT / "backend" / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Smart Traffic Management and Intelligent Transportation System for Lusaka CBD")
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'traffic.db').as_posix()}")
    # auto   = camera/vision measurements where available, demo model elsewhere (labelled per approach)
    # vision = cameras only; approaches without a working camera report "no data"
    # demo   = demo model only (no cameras / AI started)
    data_source: str = os.getenv("DATA_SOURCE", "auto")
    vision_enabled: bool = os.getenv("VISION_ENABLED", "true").lower() == "true"
    yolo_model: str = os.getenv("YOLO_MODEL", "yolo26n.pt")
    yolo_conf: float = float(os.getenv("YOLO_CONF", "0.35"))
    yolo_imgsz: int = int(os.getenv("YOLO_IMGSZ", "640"))
    yolo_device: str | None = os.getenv("YOLO_DEVICE") or None
    retention_days: int = int(os.getenv("RETENTION_DAYS", "30"))
    timezone: str = os.getenv("TIMEZONE", "Africa/Lusaka")  # peak periods are defined in local time
    tick_seconds: float = float(os.getenv("TICK_SECONDS", "1.0"))
    persist_every_s: float = float(os.getenv("PERSIST_EVERY_S", "5"))
    demo_seed: int = int(os.getenv("DEMO_SEED", "7"))
    intersection_id: str = os.getenv("INTERSECTION_ID", "INT-001")
    intersection_name: str = os.getenv("INTERSECTION_NAME", "Demo Intersection — Lusaka")
    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    )


settings = Settings()

"""MattingEngine protocol and shared result types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np


class EngineMode(str, Enum):
    GYORS = "gyors"
    MAX = "max"


ProgressCb = Callable[[float, str], None]


@dataclass(frozen=True)
class EngineCapabilities:
    mode: EngineMode
    name: str
    backend: str
    available: bool
    license_note: str
    vram_hint_gb: float
    detail: str = ""
    weights_path: Optional[str] = None


@dataclass(frozen=True)
class MediaInfo:
    path: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration_sec: float


@dataclass
class MatteFrame:
    bgr: np.ndarray
    alpha: np.ndarray  # HxW float32 0..1 soft alpha
    t_sec: float
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreviewFrame:
    t_sec: float
    width: int
    height: int
    jpeg_b64: str
    alpha_png_b64: str
    engine: str
    backend: str
    meta: dict[str, Any] = field(default_factory=dict)
    # Original video frame (no matte) — seed paint underlay; optional for older callers.
    source_jpeg_b64: str = ""


@dataclass
class BakeResult:
    ok: bool
    out_dir: str
    frames_written: int
    engine: str
    backend: str
    message: str
    alpha_preview: Optional[str] = None
    preview_mp4: Optional[str] = None
    prores_mov: Optional[str] = None
    bake_range: Optional[dict[str, Any]] = None


class MattingEngine(ABC):
    """One session per open media; mode selects Fast vs Max quality path."""

    mode: EngineMode

    @abstractmethod
    def capabilities(self) -> EngineCapabilities:
        ...

    @abstractmethod
    def reset(self) -> None:
        ...

    @abstractmethod
    def open_media(self, path: Path) -> MediaInfo:
        ...

    @abstractmethod
    def preview_frame(self, t_sec: float) -> PreviewFrame:
        ...

    @abstractmethod
    def bake(
        self,
        out_dir: Path,
        *,
        max_frames: Optional[int] = None,
        progress: Optional[ProgressCb] = None,
        in_sec: float = 0.0,
        out_sec: Optional[float] = None,
    ) -> BakeResult:
        ...

    def close(self) -> None:
        return None

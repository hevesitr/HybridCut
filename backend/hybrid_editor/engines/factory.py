"""Create MattingEngine for the selected mode."""

from __future__ import annotations

from hybrid_editor.engines.base import EngineMode, MattingEngine
from hybrid_editor.engines.fast_rvm import FastEngine
from hybrid_editor.engines.max_quality import MaxQualityEngine


def resolve_mode(value: str | EngineMode) -> EngineMode:
    if isinstance(value, EngineMode):
        return value
    key = str(value).strip().lower().replace(" ", "_")
    aliases = {
        "gyors": EngineMode.GYORS,
        "fast": EngineMode.GYORS,
        "gyors_mod": EngineMode.GYORS,
        "max": EngineMode.MAX,
        "max_minoseg": EngineMode.MAX,
        "max_quality": EngineMode.MAX,
        "minoseg": EngineMode.MAX,
    }
    if key not in aliases:
        raise ValueError(f"Unknown mode: {value!r} (use 'gyors' or 'max')")
    return aliases[key]


def create_engine(mode: str | EngineMode) -> MattingEngine:
    m = resolve_mode(mode)
    if m is EngineMode.GYORS:
        return FastEngine()
    if m is EngineMode.MAX:
        return MaxQualityEngine()
    raise ValueError(f"Unsupported mode: {m}")

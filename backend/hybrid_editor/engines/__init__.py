"""Matting engines: Fast (ORT RVM) and Max quality (MatAnyone2 adapter / pipeline)."""

from hybrid_editor.engines.base import (
    BakeResult,
    EngineCapabilities,
    EngineMode,
    MatteFrame,
    MediaInfo,
    MattingEngine,
    PreviewFrame,
)

__all__ = [
    "BakeResult",
    "EngineCapabilities",
    "EngineMode",
    "MatteFrame",
    "MediaInfo",
    "MattingEngine",
    "PreviewFrame",
    "create_engine",
    "resolve_mode",
]


def __getattr__(name: str):
    if name in ("create_engine", "resolve_mode"):
        from hybrid_editor.engines.factory import create_engine, resolve_mode

        return create_engine if name == "create_engine" else resolve_mode
    raise AttributeError(name)

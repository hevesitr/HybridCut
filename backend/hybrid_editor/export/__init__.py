"""Export / bake helpers — alpha sequence + Windows-openable H.264 preview + audio."""

from hybrid_editor.export.bgcut import (
    default_bgcut_dir,
    ensure_bgcut_dir,
    nobg_mov_path,
    nobg_preview_path,
    nobg_stem,
)
from hybrid_editor.export.composer import (
    AudioSegment,
    ExportResult,
    media_has_audio,
    mux_audio_onto_video,
    try_prores_alpha,
    write_preview_mp4,
    write_windows_companion,
)

__all__ = [
    "AudioSegment",
    "ExportResult",
    "default_bgcut_dir",
    "ensure_bgcut_dir",
    "media_has_audio",
    "mux_audio_onto_video",
    "nobg_mov_path",
    "nobg_preview_path",
    "nobg_stem",
    "try_prores_alpha",
    "write_preview_mp4",
    "write_windows_companion",
]

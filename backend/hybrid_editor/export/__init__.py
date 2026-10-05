"""Export / bake helpers — alpha MOV primary + Windows-openable H.264 preview + audio."""

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
    finalize_bgcut_exports,
    media_has_audio,
    mux_audio_onto_video,
    try_prores_alpha,
    write_preview_mp4,
    write_windows_companion,
)
from hybrid_editor.export.ffmpeg_bin import ffmpeg_bin, resolve_ffmpeg

__all__ = [
    "AudioSegment",
    "ExportResult",
    "default_bgcut_dir",
    "ensure_bgcut_dir",
    "ffmpeg_bin",
    "finalize_bgcut_exports",
    "media_has_audio",
    "mux_audio_onto_video",
    "nobg_mov_path",
    "nobg_preview_path",
    "nobg_stem",
    "resolve_ffmpeg",
    "try_prores_alpha",
    "write_preview_mp4",
    "write_windows_companion",
]

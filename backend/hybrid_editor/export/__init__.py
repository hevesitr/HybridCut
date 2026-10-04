"""Export / bake helpers — alpha sequence + Windows-openable H.264 preview + audio."""

from hybrid_editor.export.composer import (
    AudioSegment,
    ExportResult,
    media_has_audio,
    mux_audio_onto_video,
    write_preview_mp4,
    write_windows_companion,
)

__all__ = [
    "AudioSegment",
    "ExportResult",
    "media_has_audio",
    "mux_audio_onto_video",
    "write_preview_mp4",
    "write_windows_companion",
]

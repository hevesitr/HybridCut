"""Resolve ffmpeg/ffprobe like Videoeditor — PATH alone is not enough on Windows."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _candidate_ffmpeg_paths(name: str = "ffmpeg") -> list[Path]:
    """PATH + `where` + FFMPEG_* env + common Windows install locations."""
    exe = f"{name}.exe" if sys.platform == "win32" else name
    found: list[Path] = []

    which = shutil.which(name)
    if which:
        found.append(Path(which))

    if sys.platform == "win32":
        # `where` often sees installs that shutil.which misses (GUI / stale PATH).
        try:
            proc = subprocess.run(
                ["where.exe", name],
                capture_output=True,
                text=True,
                check=False,
                timeout=8,
            )
            for line in (proc.stdout or "").splitlines():
                line = line.strip().strip('"')
                if line:
                    found.append(Path(line))
        except (OSError, subprocess.TimeoutExpired):
            pass

        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        home = os.environ.get("USERPROFILE", "")
        fixed = [
            Path(r"C:\ffmpeg\bin") / exe,
            Path(r"C:\tools\ffmpeg\bin") / exe,
            Path(pf) / "ffmpeg" / "bin" / exe,
            Path(pf) / "FFmpeg" / "bin" / exe,
            Path(pf) / "Gyan" / "FFmpeg" / "bin" / exe,
            Path(pf86) / "ffmpeg" / "bin" / exe,
            Path(r"C:\ProgramData\chocolatey\bin") / exe,
        ]
        if local:
            fixed.extend(
                [
                    Path(local) / "Microsoft" / "WinGet" / "Links" / exe,
                    Path(local) / "Programs" / "ffmpeg" / "bin" / exe,
                ]
            )
        if home:
            fixed.extend(
                [
                    Path(home) / "scoop" / "shims" / exe,
                    Path(home) / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / exe,
                    Path(home) / "ffmpeg" / "bin" / exe,
                ]
            )
        found.extend(fixed)

        for env_key in ("FFMPEG_PATH", "FFMPEG_HOME"):
            raw = (os.environ.get(env_key) or "").strip().strip('"')
            if not raw:
                continue
            p = Path(raw)
            found.append(p)
            found.append(p / exe)
            found.append(p / "bin" / exe)

    out: list[Path] = []
    seen: set[str] = set()
    for p in found:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def resolve_ffmpeg(name: str = "ffmpeg") -> Optional[str]:
    """Return absolute path to ffmpeg/ffprobe, or None if not found."""
    for cand in _candidate_ffmpeg_paths(name):
        try:
            if cand.is_file():
                return str(cand.resolve())
        except OSError:
            continue
    return None


def ffmpeg_bin() -> str:
    path = resolve_ffmpeg("ffmpeg")
    if not path:
        raise RuntimeError(
            "FFmpeg not found. Add ffmpeg to PATH, install to C:\\ffmpeg\\bin "
            "(Chocolatey / Scoop / WinGet), or set FFMPEG_PATH to ffmpeg.exe."
        )
    return path


def ffprobe_bin() -> str:
    return resolve_ffmpeg("ffprobe") or ffmpeg_bin()

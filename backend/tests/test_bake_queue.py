"""Phase 5b: bake queue when a bake is already running."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.session import EditorSession  # noqa: E402


def _write_sample(path: Path, n: int = 6) -> None:
    w, h = 120, 90
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for i in range(n):
        frame = np.zeros((h, w, 3), np.uint8)
        frame[:] = (20, 70, 35)
        cv2.circle(frame, (30 + i * 4, 45), 18, (40, 50, 200), -1)
        writer.write(frame)
    writer.release()


def test_bake_queues_when_busy(tmp_path: Path):
    sample = tmp_path / "q.mp4"
    _write_sample(sample)
    session = EditorSession()
    session.open_media(sample)

    out1 = tmp_path / "bake1"
    out2 = tmp_path / "bake2"
    st1 = session.bake(out1, max_frames=2, async_job=True, queue_if_busy=True, label="a")
    assert isinstance(st1, dict)
    assert st1.get("bake_running") is True

    st2 = session.bake(out2, max_frames=2, async_job=True, queue_if_busy=True, label="b")
    assert isinstance(st2, dict)
    assert st2.get("queued") is True or st2.get("bake_queue_len", 0) >= 1

    # Wait for both to finish
    deadline = time.time() + 60
    while time.time() < deadline:
        st = session.status()
        if not st["bake_running"] and st.get("bake_queue_len", 0) == 0:
            break
        time.sleep(0.1)
    st = session.status()
    assert st["bake_running"] is False
    assert st.get("bake_queue_len", 0) == 0
    assert st["last_bake"] is not None

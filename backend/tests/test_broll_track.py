"""Phase 4: V2 B-roll / multi-track FramePlan stub."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.timeline.frame_plan import TimelineDoc, plan_frame  # noqa: E402


def test_broll_does_not_pack_into_v1():
    doc = TimelineDoc.from_media(
        path="/a.mp4",
        duration_sec=4.0,
        fps=25.0,
        width=320,
        height=240,
        out_sec=4.0,
    )
    doc.set_playhead(1.0)
    b = doc.add_broll(
        media_path="/b.mp4",
        duration_sec=2.0,
        fps=25.0,
        width=320,
        height=240,
        out_sec=2.0,
        label="B-roll",
    )
    assert int(b.track) == 1
    assert abs(b.timeline_start_sec - 1.0) < 1e-6
    # V1 duration unchanged by overlay placement
    assert abs(doc.clips_on(0)[0].timeline_end() - 4.0) < 1e-6
    # Total duration may extend if B-roll ends later — here 1+2=3 < 4
    assert abs(doc.duration_sec() - 4.0) < 1e-6

    plan = plan_frame(doc, 1.5)
    assert not plan.empty
    assert len(plan.layers) == 2
    assert plan.layers[0].track == 0
    assert plan.layers[1].track == 1
    assert plan.layers[1].clip_id == b.clip_id


def test_promote_and_to_dict_tracks():
    doc = TimelineDoc.from_media(
        path="/a.mp4",
        duration_sec=3.0,
        fps=25.0,
        width=100,
        height=100,
    )
    doc.add_clip(
        media_path="/c.mp4",
        duration_sec=2.0,
        fps=25.0,
        width=100,
        height=100,
    )
    assert len(doc.clips_on(0)) == 2
    second = doc.clips[1]
    second.track = 1
    second.timeline_start_sec = 0.5
    doc.relayout_sequential()
    assert len(doc.clips_on(0)) == 1
    assert len(doc.clips_on(1)) == 1
    d = doc.to_dict()
    assert d["tracks"][1]["label"] == "V2 B-roll"
    assert any(c["track"] == 1 for c in d["clips"])

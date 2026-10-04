"""Tests for multi-clip TimelineDoc + pure FramePlan."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.timeline.frame_plan import TimelineDoc, plan_frame


def test_frame_plan_source_mapping():
    doc = TimelineDoc.from_media(
        path="/tmp/clip.mp4",
        duration_sec=10.0,
        fps=25.0,
        width=640,
        height=360,
        in_sec=2.0,
        out_sec=6.0,
    )
    assert abs(doc.duration_sec() - 4.0) < 1e-6
    plan = plan_frame(doc, 1.0)
    assert not plan.empty
    assert abs(plan.layers[0].source_t_sec - 3.0) < 1e-6
    empty = plan_frame(doc, 5.0)
    assert empty.empty


def test_trim_and_playhead():
    doc = TimelineDoc.from_media(
        path="/x.mp4",
        duration_sec=8.0,
        fps=24.0,
        width=100,
        height=100,
    )
    doc.set_trim(in_sec=1.0, out_sec=5.0)
    doc.set_playhead(9.0)
    assert doc.playhead_sec <= doc.duration_sec()
    d = doc.to_dict()
    assert d["clips"][0]["in_sec"] == 1.0
    assert d["duration_sec"] == 4.0


def test_multi_clip_add_cut_reorder():
    doc = TimelineDoc.from_media(
        path="/a.mp4",
        duration_sec=6.0,
        fps=25.0,
        width=320,
        height=240,
        in_sec=0.0,
        out_sec=4.0,
    )
    c2 = doc.add_clip(
        media_path="/b.mp4",
        duration_sec=5.0,
        fps=25.0,
        width=320,
        height=240,
        in_sec=1.0,
        out_sec=3.0,
    )
    assert len(doc.clips) == 2
    assert abs(doc.duration_sec() - 6.0) < 1e-6  # 4 + 2
    assert c2.timeline_start_sec == 4.0

    # Plan into second clip
    plan = plan_frame(doc, 4.5)
    assert not plan.empty
    assert plan.layers[0].clip_id == c2.clip_id
    assert abs(plan.layers[0].source_t_sec - 1.5) < 1e-6

    # Cut first clip at t=2
    doc.set_playhead(2.0)
    assert doc.cut_at_playhead()
    assert len(doc.clips) == 3
    assert abs(doc.duration_sec() - 6.0) < 1e-6

    first_id = doc.clips[0].clip_id
    assert doc.move_clip(first_id, direction=1)
    assert doc.clips[1].clip_id == first_id

    assert doc.remove_clip(doc.clips[-1].clip_id)
    assert len(doc.clips) == 2


def test_duplicate_and_select():
    doc = TimelineDoc.from_media(
        path="/z.mp4",
        duration_sec=3.0,
        fps=30.0,
        width=100,
        height=100,
    )
    dup = doc.duplicate_selected()
    assert dup is not None
    assert len(doc.clips) == 2
    assert abs(doc.duration_sec() - 6.0) < 1e-6
    doc.select_clip(dup.clip_id)
    assert doc.selected_clip_id == dup.clip_id
    d = doc.to_dict()
    assert d["selected_clip_id"] == dup.clip_id
    assert "display_label" in d["clips"][0]

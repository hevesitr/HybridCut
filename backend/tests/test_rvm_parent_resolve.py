"""Phase 5: FastEngine resolves parent Videoeditor RVM ONNX + open-folder API."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.engines.fast_rvm import (  # noqa: E402
    parent_videoeditor_roots,
    probe_ort_runtime,
    resolve_rvm_onnx,
)
from hybrid_editor.session import EditorSession  # noqa: E402


def test_resolve_rvm_onnx_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = tmp_path / "rvm_mobilenetv3_fp16.onnx"
    fake.write_bytes(b"fake-onnx")
    monkeypatch.setenv("HYBRID_RVM_ONNX", str(fake))
    monkeypatch.delenv("VIDEOEDITOR_RVM_ONNX", raising=False)
    assert resolve_rvm_onnx() == fake


def test_resolve_rvm_onnx_parent_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HYBRID_RVM_ONNX", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_RVM_ONNX", raising=False)
    monkeypatch.delenv("HYBRID_MODELS_DIR", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_MODELS", raising=False)
    monkeypatch.delenv("VIDEOEDITOR_MODELS_DIR", raising=False)

    # Simulate Documents\Videoeditor\models next to a nested hybrid_cut ROOT
    import hybrid_editor.engines.fast_rvm as fr

    hybrid_root = tmp_path / "Videoeditor" / "hybrid_cut"
    hybrid_root.mkdir(parents=True)
    parent_models = tmp_path / "Videoeditor" / "models"
    parent_models.mkdir(parents=True)
    onnx = parent_models / "rvm_resnet50_fp16.onnx"
    onnx.write_bytes(b"x")

    monkeypatch.setattr(fr, "ROOT", hybrid_root)
    hit = resolve_rvm_onnx()
    assert hit == onnx
    roots = parent_videoeditor_roots()
    assert any(r.name.lower() == "videoeditor" for r in roots)


def test_probe_ort_runtime_shape(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HYBRID_RVM_ONNX", raising=False)
    info = probe_ort_runtime()
    assert "onnx_found" in info
    assert "ort_available" in info
    assert "cuda_ep" in info
    assert "providers" in info
    assert isinstance(info["providers"], list)


def test_session_status_includes_rvm():
    session = EditorSession()
    st = session.status()
    assert "rvm" in st
    assert "onnx_found" in st["rvm"]
    assert st["intelligence"].get("open_output_folder") is True
    assert st["intelligence"].get("bake_queue") is True


def test_open_output_folder_returns_path(tmp_path: Path):
    session = EditorSession()
    # Force a known folder without requiring a display
    os.environ.pop("DISPLAY", None)
    os.environ.pop("WAYLAND_DISPLAY", None)
    res = session.open_output_folder(str(tmp_path / "bake_out"))
    assert res["ok"] is True
    assert Path(res["out_dir"]).is_dir()
    assert res["out_dir"].endswith("bake_out") or "bake_out" in res["out_dir"]

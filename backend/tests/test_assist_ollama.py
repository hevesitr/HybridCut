"""Phase 5 stub: Ollama assist status fails closed when daemon down."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from hybrid_editor.assist import ollama  # noqa: E402


def test_status_down():
    with mock.patch.object(ollama, "_request_json", side_effect=ollama.urllib.error.URLError("down")):
        st = ollama.status()
    assert st.ok is False
    assert "11434" in st.message or "Ollama" in st.message


def test_chat_without_llama3():
    fake = ollama.OllamaStatus(ok=False, message="no model", has_llama3=False)
    with mock.patch.object(ollama, "status", return_value=fake):
        res = ollama.chat("hello")
    assert res["ok"] is False
    assert res["reply"] is None

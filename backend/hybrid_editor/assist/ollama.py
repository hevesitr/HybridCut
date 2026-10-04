"""Minimal local Ollama client — no paid APIs.

Host: http://127.0.0.1:11434
Chat model: llama3
Embed model: nomic-embed-text
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

OLLAMA_HOST = "http://127.0.0.1:11434"
CHAT_MODEL = "llama3"
EMBED_MODEL = "nomic-embed-text"
DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True)
class OllamaStatus:
    ok: bool
    message: str
    host: str = OLLAMA_HOST
    chat_model: str = CHAT_MODEL
    embed_model: str = EMBED_MODEL
    models: tuple[str, ...] = ()
    has_llama3: bool = False
    has_nomic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "host": self.host,
            "chat_model": self.chat_model,
            "embed_model": self.embed_model,
            "models": list(self.models),
            "has_llama3": self.has_llama3,
            "has_nomic": self.has_nomic,
        }


def _url(path: str) -> str:
    return f"{OLLAMA_HOST.rstrip('/')}{path}"


def _request_json(
    method: str,
    path: str,
    payload: Optional[dict[str, Any]] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(_url(path), data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    if not raw:
        return None
    return json.loads(raw)


def status() -> OllamaStatus:
    try:
        body = _request_json("GET", "/api/tags", timeout=4.0)
    except urllib.error.URLError:
        return OllamaStatus(
            ok=False,
            message="Ollama nem elérhető — indítsd: ollama serve (localhost:11434)",
        )
    except Exception as exc:  # noqa: BLE001
        return OllamaStatus(ok=False, message=f"Ollama hiba: {exc}")

    names: list[str] = []
    for m in (body or {}).get("models") or []:
        name = str(m.get("name") or m.get("model") or "")
        if name:
            names.append(name)
    has_llama3 = any(n.startswith("llama3") for n in names)
    has_nomic = any("nomic-embed-text" in n for n in names)
    if not has_llama3:
        msg = "Ollama fut, de nincs llama3 — futtasd: ollama pull llama3"
        ok = False
    else:
        msg = "Ollama OK · llama3"
        if has_nomic:
            msg += " + nomic-embed-text"
        ok = True
    return OllamaStatus(
        ok=ok,
        message=msg,
        models=tuple(names),
        has_llama3=has_llama3,
        has_nomic=has_nomic,
    )


def chat(prompt: str, *, system: Optional[str] = None) -> dict[str, Any]:
    """One-shot chat via /api/chat — fails closed if Ollama/llama3 missing."""
    st = status()
    if not st.has_llama3:
        return {"ok": False, "reply": None, "status": st.to_dict(), "error": st.message}
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        body = _request_json(
            "POST",
            "/api/chat",
            {
                "model": CHAT_MODEL,
                "messages": messages,
                "stream": False,
            },
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "reply": None,
            "status": st.to_dict(),
            "error": f"chat failed: {exc}",
        }
    msg = (body or {}).get("message") or {}
    reply = msg.get("content") or (body or {}).get("response") or ""
    return {"ok": True, "reply": reply, "status": st.to_dict(), "error": None}

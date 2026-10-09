"""Client minimal pour Ollama (LLM local, gratuit, http://localhost:11434)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not HOST.startswith("http"):
    HOST = "http://" + HOST


class LLMUnavailable(RuntimeError):
    pass


def _request(path: str, payload: dict | None = None, timeout: float = 5) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        HOST + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def check(model: str) -> None:
    try:
        tags = _request("/api/tags")
    except (urllib.error.URLError, OSError) as exc:
        raise LLMUnavailable(
            "Ollama ne répond pas. Lance-le avec : brew services start ollama"
        ) from exc
    names = {m.get("name", "") for m in tags.get("models", [])}
    wanted = model if ":" in model else model + ":latest"
    if wanted not in names and model not in names:
        raise LLMUnavailable(f"Le modèle « {model} » n'est pas téléchargé. Fais : ollama pull {model}")


def chat_json(model: str, system: str, user: str, num_ctx: int = 16384) -> dict:
    """Envoie une requête et renvoie la réponse JSON parsée."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0.3, "num_ctx": num_ctx},
    }
    try:
        resp = _request("/api/chat", payload, timeout=900)
    except urllib.error.HTTPError as exc:
        # Anciennes versions d'Ollama / modèles sans « think » : on réessaie sans
        if exc.code == 400 and "think" in payload:
            payload.pop("think")
            resp = _request("/api/chat", payload, timeout=900)
        else:
            raise
    content = resp.get("message", {}).get("content", "")
    return _parse_json(content)


def _parse_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {}

"""Transcription locale avec horodatage au mot.

Sur Mac Apple Silicon : mlx-whisper (GPU de la puce M, très rapide).
Ailleurs : faster-whisper (CPU).
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
FASTER_MODEL = "large-v3-turbo"


def _backend() -> str:
    if sys.platform == "darwin" and platform.machine() == "arm64":
        try:
            import mlx_whisper  # noqa: F401
            return "mlx"
        except ImportError:
            pass
    try:
        import faster_whisper  # noqa: F401
        return "faster"
    except ImportError:
        pass
    raise RuntimeError(
        "Aucun moteur Whisper installé. Sur Mac : pip install mlx-whisper ; "
        "ailleurs : pip install faster-whisper"
    )


def _clean_words(raw: list[dict]) -> list[dict]:
    words = []
    for w in raw:
        text = str(w.get("word", "")).strip()
        if not text:
            continue
        start, end = float(w["start"]), float(w["end"])
        if end < start:
            end = start
        words.append({"w": text, "s": round(start, 3), "e": round(end, 3)})
    words.sort(key=lambda x: x["s"])
    return words


def transcribe(wav: Path, cache: Path, language: str | None, model: str | None) -> list[dict]:
    """Renvoie la liste des mots : [{"w": texte, "s": début, "e": fin}, …]."""
    if cache.exists():
        return json.loads(cache.read_text())["words"]

    backend = _backend()
    raw: list[dict] = []
    if backend == "mlx":
        import mlx_whisper  # type: ignore

        result = mlx_whisper.transcribe(
            str(wav),
            path_or_hf_repo=model or MLX_MODEL,
            word_timestamps=True,
            language=language,
            condition_on_previous_text=False,  # limite les hallucinations sur la musique
            verbose=False,
        )
        for seg in result.get("segments", []):
            raw.extend(seg.get("words", []))
    else:
        from faster_whisper import WhisperModel  # type: ignore

        wm = WhisperModel(model or FASTER_MODEL, device="auto", compute_type="int8")
        segments, _ = wm.transcribe(
            str(wav), language=language, word_timestamps=True,
            vad_filter=True, condition_on_previous_text=False,
        )
        for seg in segments:
            for w in seg.words or []:
                raw.append({"word": w.word, "start": w.start, "end": w.end})

    words = _clean_words(raw)
    cache.write_text(json.dumps({"backend": backend, "words": words}, ensure_ascii=False))
    return words

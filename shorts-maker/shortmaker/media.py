"""Accès à ffmpeg/ffprobe : infos vidéo, extraction audio, énergie sonore, changements de plan."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ENERGY_STEP = 0.25  # secondes par fenêtre d'énergie audio


class MediaError(RuntimeError):
    pass


def require_tools() -> None:
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if missing:
        raise MediaError(
            f"Introuvable : {', '.join(missing)}. Installe-le avec : brew install ffmpeg"
        )


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise MediaError(f"Échec de la commande : {' '.join(cmd[:4])} …\n{tail}")
    return proc


def probe(path: Path) -> dict:
    out = run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]).stdout
    data = json.loads(out)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError(f"Aucune piste vidéo dans {path}")
    has_audio = any(s.get("codec_type") == "audio" for s in data["streams"])
    width, height = int(video["width"]), int(video["height"])
    # Vidéos tournées au téléphone : la rotation est stockée à part
    rotation = 0
    for side in video.get("side_data_list", []):
        if "rotation" in side:
            rotation = abs(int(side["rotation"]))
    if rotation in (90, 270):
        width, height = height, width
    return {
        "duration": float(data["format"]["duration"]),
        "width": width,
        "height": height,
        "has_audio": has_audio,
    }


def extract_audio(video: Path, wav: Path) -> None:
    """WAV mono 16 kHz : le format attendu par Whisper, réutilisé pour l'énergie."""
    if wav.exists():
        return
    tmp = wav.with_suffix(".tmp.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1",
         "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)])
    tmp.rename(wav)


def audio_energy(wav: Path) -> np.ndarray:
    """Niveau sonore (dB) par fenêtre de ENERGY_STEP secondes."""
    with wave.open(str(wav), "rb") as w:
        rate = w.getframerate()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    samples = samples.astype(np.float32) / 32768.0
    hop = int(rate * ENERGY_STEP)
    n = len(samples) // hop
    if n == 0:
        return np.zeros(1, dtype=np.float32)
    frames = samples[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    return (20 * np.log10(rms)).astype(np.float32)


def scene_changes(video: Path, threshold: float = 0.3) -> list[float]:
    """Horodatages des changements de plan (montage nerveux = moment dynamique)."""
    cmd = ["ffmpeg", "-v", "error"]
    if sys.platform == "darwin":
        cmd += ["-hwaccel", "videotoolbox"]
    cmd += [
        "-i", str(video), "-an", "-sn",
        "-vf", f"scale=320:-2,select='gt(scene,{threshold})',metadata=print:file=-",
        "-f", "null", "-",
    ]
    out = run(cmd).stdout
    return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", out)]


def has_filter(name: str) -> bool:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                         capture_output=True, text=True).stdout
    return re.search(rf"^\s*\S+\s+{re.escape(name)}\s", out, re.M) is not None


def best_video_encoder() -> list[str]:
    """Encodeur matériel Apple si dispo (très rapide sur puce M), sinon x264."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                         capture_output=True, text=True).stdout
    if sys.platform == "darwin" and "h264_videotoolbox" in out:
        return ["-c:v", "h264_videotoolbox", "-b:v", "10M", "-maxrate", "14M",
                "-bufsize", "20M", "-profile:v", "high"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high"]

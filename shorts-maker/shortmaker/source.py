"""Résout l'entrée : fichier local ou URL YouTube (téléchargée avec yt-dlp)."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

URL_RE = re.compile(r"^https?://", re.I)


def is_url(value: str) -> bool:
    return bool(URL_RE.match(value))


def cache_key(value: str) -> str:
    if is_url(value):
        # Même vidéo = même clé, quelle que soit la forme de l'URL
        m = re.search(r"(?:v=|youtu\.be/|shorts/|live/|embed/)([\w-]{11})", value)
        ident = m.group(1) if m else value
    else:
        p = Path(value).expanduser().resolve()
        st = p.stat()
        ident = f"{p}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.sha1(ident.encode()).hexdigest()[:12]


def download(url: str, workdir: Path) -> tuple[Path, str]:
    """Télécharge la vidéo (≤ 1440p, mp4). Renvoie (chemin, titre)."""
    existing = sorted(workdir.glob("source.*"))
    title_file = workdir / "title.txt"
    if existing and title_file.exists():
        return existing[0], title_file.read_text().strip()

    fmt = "bv*[height<=1440][ext=mp4]+ba[ext=m4a]/bv*[height<=1440]+ba/b[height<=1440]/b"
    outtmpl = str(workdir / "source.%(ext)s")
    try:
        import yt_dlp  # type: ignore

        opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": False,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title") or "video"
    except ImportError:
        if shutil.which("yt-dlp") is None:
            raise RuntimeError("yt-dlp n'est pas installé : pip install yt-dlp")
        subprocess.run(["yt-dlp", "-f", fmt, "--merge-output-format", "mp4",
                        "--no-playlist", "-o", outtmpl, url], check=True)
        title = subprocess.run(["yt-dlp", "--get-title", "--no-playlist", url],
                               capture_output=True, text=True).stdout.strip() or "video"

    files = sorted(p for p in workdir.glob("source.*") if not p.name.endswith(".part"))
    if not files:
        raise RuntimeError("Le téléchargement n'a produit aucun fichier.")
    title_file.write_text(title)
    return files[0], title


def resolve(value: str, workdir: Path) -> tuple[Path, str]:
    if is_url(value):
        return download(value, workdir)
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    return path, path.stem

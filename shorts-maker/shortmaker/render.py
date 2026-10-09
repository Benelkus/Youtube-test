"""Montage d'un Short vertical 1080×1920 avec ffmpeg."""

from __future__ import annotations

from pathlib import Path

from .media import run

LAYOUTS = ("blur", "crop")


def video_graph(layout: str, ass_name: str | None) -> str:
    subs = f",ass={ass_name}" if ass_name else ""
    if layout == "crop":
        # Plein écran : recadrage au centre de l'image
        return (f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,setsar=1{subs},format=yuv420p[v]")
    # « blur » : l'image entière au centre, fond flouté — le rendu classique des
    # Shorts de reportage, rien n'est coupé (cartes, incrustations, plans larges).
    return ("[0:v]split=2[a][b];"
            "[a]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
            "boxblur=10:2,scale=1080:1920,eq=brightness=-0.12:saturation=0.85[bg];"
            "[b]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1{subs},format=yuv420p[v]")


def render_clip(src: Path, start: float, end: float, out: Path, *, layout: str,
                ass_name: str | None, workdir: Path, encoder: list[str], has_audio: bool) -> None:
    dur = end - start
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
        "-filter_complex", video_graph(layout, ass_name),
        "-map", "[v]",
    ]
    if has_audio:
        fade_out = max(0.0, dur - 0.3)
        cmd += ["-map", "0:a:0",
                "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:d=0.05,"
                       f"afade=t=out:st={fade_out:.3f}:d=0.3",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    cmd += encoder + ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out.resolve())]
    # cwd = dossier de travail : le .ass est passé par son seul nom (pas d'échappement de chemin)
    run(cmd, cwd=workdir)

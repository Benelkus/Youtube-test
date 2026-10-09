"""Sous-titres animés façon Shorts : groupes de quelques mots, mot prononcé surligné.

Génère un fichier ASS (format lu par ffmpeg/libass) en 1080×1920.
"""

from __future__ import annotations

import re
from pathlib import Path

W, H = 1080, 1920

# Couleurs ASS : &HAABBGGRR
WHITE = "&H00FFFFFF"
YELLOW = "&H0000D7FF"
BLACK = "&H00000000"
SHADOW = "&H80000000"
TITLE_BOX = "&H002828D6"  # rouge (#D62828)

PUNCT_BREAK = re.compile(r"[.,;:!?…]$")


def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def _chunks(words: list[dict], max_words: int, max_chars: int) -> list[list[dict]]:
    out, cur = [], []
    for k, w in enumerate(words):
        if cur:
            gap = w["s"] - cur[-1]["e"]
            length = sum(len(x["w"]) + 1 for x in cur) + len(w["w"])
            if len(cur) >= max_words or length > max_chars or gap > 0.6 \
                    or PUNCT_BREAK.search(cur[-1]["w"]):
                out.append(cur)
                cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def build_ass(words: list[dict], clip_start: float, clip_end: float, out: Path, *,
              title: str | None, title_full: bool, layout: str, font: str,
              uppercase: bool = True, max_words: int = 3, max_chars: int = 22) -> None:
    dur = clip_end - clip_start
    local = []
    for w in words:
        if w["e"] <= clip_start + 0.02 or w["s"] >= clip_end - 0.02:
            continue
        text = w["w"].upper() if uppercase else w["w"]
        local.append({"w": text, "s": max(0.0, w["s"] - clip_start),
                      "e": min(dur, w["e"] - clip_start)})

    # Zone vidéo 16:9 en mode « blur » : 1080×608 centrée (y 656 → 1264).
    # Sous-titres juste en dessous, titre au-dessus ; hors de la zone couverte par l'interface YouTube.
    sub_y = 1330 if layout == "blur" else 1240
    title_y = 380 if layout == "blur" else 230

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font},84,{WHITE},{WHITE},{BLACK},{SHADOW},-1,0,0,0,100,100,1,0,1,7,3,8,70,70,{sub_y},1
Style: Title,{font},62,{WHITE},{WHITE},{TITLE_BOX},{SHADOW},-1,0,0,0,100,100,0,0,3,18,0,8,90,90,{title_y},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if title:
        t_end = dur if title_full else min(dur, 4.0)
        fade = r"{\fad(250,0)}" if title_full else r"{\fad(250,300)}"
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(t_end)},Title,,0,0,0,,{fade}{_esc(title.upper())}")

    groups = _chunks(local, max_words, max_chars)
    for g, chunk in enumerate(groups):
        nxt = groups[g + 1][0]["s"] if g + 1 < len(groups) else None
        chunk_end = nxt if (nxt is not None and nxt - chunk[-1]["e"] < 0.6) else chunk[-1]["e"] + 0.25
        chunk_end = min(chunk_end, dur)
        for k, w in enumerate(chunk):
            a = chunk[0]["s"] if k == 0 else w["s"]
            b = chunk[k + 1]["s"] if k + 1 < len(chunk) else chunk_end
            if b - a < 0.01:
                continue
            parts = []
            for m, x in enumerate(chunk):
                txt = _esc(x["w"])
                parts.append(rf"{{\c{YELLOW}}}{txt}{{\c{WHITE}}}" if m == k else txt)
            pop = r"{\fscx108\fscy108\t(0,80,\fscx100\fscy100)}" if k == 0 else ""
            lines.append(f"Dialogue: 0,{_ts(a)},{_ts(b)},Sub,,0,0,0,,{pop}{' '.join(parts)}")

    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")

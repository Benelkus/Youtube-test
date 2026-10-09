"""Tout ce qu'il faut pour publier vite sur YouTube.

- Le fichier vidéo porte le titre du Short : YouTube pré-remplit le titre avec le nom du fichier.
- Une description prête à coller (texte + lien vers la vidéo complète + hashtags).
- Une page « publier.html » avec un bouton Copier pour chaque titre et chaque description.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import quote

TEXTS = {
    "en": {"full": "🎥 Full video:", "tags": ["#defense", "#military"]},
    "fr": {"full": "🎥 Vidéo complète :", "tags": ["#defense", "#militaire"]},
}


def file_title(title: str, used: set[str]) -> str:
    """Nom de fichier = titre YouTube (caractères interdits sur Mac retirés), sans doublon."""
    name = re.sub(r"[/:\\\x00-\x1f]", " ", title)
    name = re.sub(r"\s+", " ", name).strip(" .") or "Short"
    name = name[:95].rstrip(" .")
    base, n = name, 2
    while name.lower() in used:
        name = f"{base} ({n})"
        n += 1
    used.add(name.lower())
    return name + ".mp4"


def build_description(m: dict, source_url: str | None, meta_lang: str) -> str:
    texts = TEXTS.get(meta_lang, TEXTS["en"])
    desc = (m.get("description") or "").strip()
    if not desc:  # sélection sans IA : on prend la première phrase de l'extrait
        desc = re.split(r"(?<=[.!?…])\s", m["text"].strip(), maxsplit=1)[0]
    tags, seen = [], set()
    for t in [*(m.get("hashtags") or []), *texts["tags"], "#shorts"]:
        t = "#" + re.sub(r"[^\w]", "", t.lstrip("#"))
        if len(t) > 1 and t.lower() not in seen:
            seen.add(t.lower())
            tags.append(t)
    parts = [desc]
    if source_url:
        parts.append(f"{texts['full']} {source_url}")
    parts.append(" ".join(tags[:6]))
    return "\n\n".join(parts)


PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Publier — {video}</title>
<style>
:root {{ --bg:#f4f5f0; --card:#fff; --text:#1d2414; --muted:#6b7262; --line:#dfe2d8;
        --accent:#d62828; --ok:#3d7a2a; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#14180f; --card:#1f2618; --text:#eef0e8; --muted:#a3ab97; --line:#343d2b; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text);
       font:15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
header {{ padding:28px 24px 8px; max-width:1100px; margin:auto; }}
h1 {{ margin:0 0 4px; font-size:24px; }}
header p {{ margin:0; color:var(--muted); }}
main {{ max-width:1100px; margin:auto; padding:16px 24px 48px; display:grid; gap:18px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px;
        display:grid; grid-template-columns:170px 1fr; gap:20px; }}
video {{ width:170px; aspect-ratio:9/16; border-radius:10px; background:#000; }}
.rank {{ color:var(--muted); font-size:13px; }}
label {{ display:block; font-weight:600; margin:10px 0 4px; }}
.field {{ display:flex; gap:8px; align-items:flex-start; }}
.field textarea {{ flex:1; resize:vertical; font:inherit; color:var(--text); background:transparent;
                  border:1px solid var(--line); border-radius:8px; padding:8px 10px; }}
button {{ flex:none; font:inherit; font-weight:600; border:0; border-radius:8px; padding:8px 14px;
         background:var(--accent); color:#fff; cursor:pointer; min-width:96px; }}
button.done {{ background:var(--ok); }}
.file {{ color:var(--muted); font-size:13px; margin-top:8px; word-break:break-all; }}
@media (max-width:640px) {{ .card {{ grid-template-columns:1fr; }} video {{ width:100%; max-width:240px; }} }}
</style></head><body>
<header>
  <h1>Publier les Shorts</h1>
  <p>{video} — glisse chaque vidéo dans YouTube Studio : le titre se remplit tout seul
  (c'est le nom du fichier). Copie ensuite la description.</p>
</header>
<main>
{cards}
</main>
<script>
document.querySelectorAll("button[data-copy]").forEach(btn => {{
  btn.addEventListener("click", async () => {{
    const area = document.getElementById(btn.dataset.copy);
    try {{ await navigator.clipboard.writeText(area.value); }}
    catch (e) {{ area.select(); document.execCommand("copy"); }}
    const label = btn.textContent;
    btn.textContent = "Copié ✓"; btn.classList.add("done");
    setTimeout(() => {{ btn.textContent = label; btn.classList.remove("done"); }}, 1500);
  }});
}});
</script>
</body></html>
"""

CARD = """<section class="card">
  <video src="{src}" controls preload="metadata" playsinline></video>
  <div>
    <div class="rank">#{rank} · score {score}/100 · {dur} s</div>
    <label for="t{rank}">Titre</label>
    <div class="field"><textarea id="t{rank}" rows="2">{title}</textarea>
      <button data-copy="t{rank}">Copier</button></div>
    <label for="d{rank}">Description</label>
    <div class="field"><textarea id="d{rank}" rows="7">{desc}</textarea>
      <button data-copy="d{rank}">Copier</button></div>
    <div class="file">Fichier : {file}</div>
  </div>
</section>"""


def write_page(out_dir: Path, video_title: str, moments: list[dict]) -> Path:
    cards = [
        CARD.format(
            src=quote(m["file"]), rank=m["rank"], score=f"{m['score']:.0f}",
            dur=f"{m['end'] - m['start']:.0f}", title=html.escape(m["yt_title"]),
            desc=html.escape(m["yt_description"]), file=html.escape(m["file"]),
        )
        for m in moments
    ]
    page = out_dir / "publier.html"
    page.write_text(PAGE.format(video=html.escape(video_title), cards="\n".join(cards)), encoding="utf-8")
    return page

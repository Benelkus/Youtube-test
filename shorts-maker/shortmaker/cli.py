"""Point d'entrée : make_shorts <URL ou fichier.mp4> [options]."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

from . import analyze, media, publish, render, source, subtitles, transcribe

ROOT = Path(__file__).resolve().parent.parent
MODEL_FILE = ROOT / ".ollama_model"  # écrit par install.sh selon la RAM du Mac
DEFAULT_MODEL = MODEL_FILE.read_text().strip() if MODEL_FILE.exists() else "qwen3:8b"


def log(msg: str) -> None:
    print(msg, flush=True)


def slug(text: str, n: int = 50) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:n].rstrip("-") or "short"


def fmt(t: float) -> str:
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="make_shorts",
        description="Génère des YouTube Shorts à partir des meilleurs moments d'une vidéo, en local.",
    )
    p.add_argument("input", help="URL YouTube ou chemin d'un fichier vidéo (.mp4, .mov…)")
    p.add_argument("-n", "--count", type=int, default=10, help="nombre de Shorts (défaut : 10)")
    p.add_argument("--min", dest="min_d", type=float, default=20, help="durée minimale en s (défaut : 20)")
    p.add_argument("--max", dest="max_d", type=float, default=60, help="durée maximale en s (défaut : 60)")
    p.add_argument("--layout", choices=render.LAYOUTS, default="blur",
                   help="blur = image entière sur fond flouté (défaut) ; crop = plein écran recadré au centre")
    p.add_argument("--lang", default="auto",
                   help="langue parlée : auto (défaut, détectée), en, fr… — les sous-titres restent dans cette langue")
    p.add_argument("--meta-lang", default="en",
                   help="langue des titres et descriptions YouTube (défaut : en = anglais ; fr, es…)")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"modèle Ollama (défaut : {DEFAULT_MODEL})")
    p.add_argument("--no-ai", action="store_true", help="sélection sans LLM (heuristique seule)")
    p.add_argument("--whisper-model", default=None, help="modèle Whisper (défaut : large-v3-turbo)")
    p.add_argument("--no-subs", action="store_true", help="pas de sous-titres incrustés")
    p.add_argument("--no-title", action="store_true", help="pas de titre incrusté en haut")
    p.add_argument("--font", default="Arial Black", help="police des sous-titres (défaut : Arial Black)")
    p.add_argument("--words", type=int, default=3, help="mots max affichés à la fois (défaut : 3)")
    p.add_argument("--no-upper", action="store_true", help="sous-titres en casse normale")
    p.add_argument("-o", "--output", default=str(ROOT / "shorts"), help="dossier de sortie")
    p.add_argument("--plan-only", action="store_true",
                   help="affiche les moments choisis sans générer les vidéos")
    p.add_argument("--open", action="store_true", help="ouvre le dossier des Shorts à la fin (Mac)")
    args = p.parse_args(argv)
    if args.min_d <= 0 or args.max_d <= args.min_d:
        p.error("il faut 0 < --min < --max")
    if args.count < 1:
        p.error("--count doit être ≥ 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    t0 = time.time()
    try:
        media.require_tools()
        if not args.no_subs and not (media.has_filter("ass") or media.has_filter("subtitles")):
            raise media.MediaError(
                "Ton ffmpeg n'a pas libass (sous-titres). Installe la version complète :\n"
                "  brew uninstall ffmpeg && brew tap homebrew-ffmpeg/ffmpeg && "
                "brew install homebrew-ffmpeg/ffmpeg/ffmpeg\n"
                "ou relance avec --no-subs."
            )

        work = ROOT / ".cache" / source.cache_key(args.input)
        work.mkdir(parents=True, exist_ok=True)

        log("① Récupération de la vidéo…")
        src, title = source.resolve(args.input, work)
        src = src.resolve()
        info = media.probe(src)
        log(f"   {title} — {fmt(info['duration'])} — {info['width']}×{info['height']}")
        if not info["has_audio"]:
            raise media.MediaError("La vidéo n'a pas de piste audio : impossible de trouver les moments forts.")

        log("② Extraction de l'audio…")
        wav = work / "audio.wav"
        media.extract_audio(src, wav)

        log("③ Transcription (Whisper, en local)… la première fois, le modèle se télécharge (~1,5 Go).")
        lang = None if args.lang == "auto" else args.lang
        words = transcribe.transcribe(wav, work / f"transcript_{args.lang}.json", lang, args.whisper_model)
        log(f"   {len(words)} mots transcrits.")

        log("④ Analyse du rythme : pics sonores et changements de plan…")
        energy = media.audio_energy(wav)
        cuts_file = work / "scenes.json"
        if cuts_file.exists():
            cuts = json.loads(cuts_file.read_text())
        else:
            cuts = media.scene_changes(src)
            cuts_file.write_text(json.dumps(cuts))
        log(f"   {len(cuts)} changements de plan détectés.")

        log("⑤ Sélection des moments forts" + (" (heuristique)…" if args.no_ai else f" (IA locale : {args.model})…"))
        moments = analyze.find_moments(
            words, info["duration"], energy, cuts,
            count=args.count, min_d=args.min_d, max_d=args.max_d,
            model=None if args.no_ai else args.model,
            video_title=title, workdir=work, log=log, meta_lang=args.meta_lang,
        )
        if not moments:
            raise RuntimeError("Aucun moment exploitable trouvé. Essaie --min plus petit.")

        out_dir = Path(args.output).expanduser().resolve() / slug(title, 60)
        out_dir.mkdir(parents=True, exist_ok=True)
        source_url = args.input if source.is_url(args.input) else None
        used: set[str] = set()
        for rank, m in enumerate(moments, 1):
            m["rank"] = rank
            if not m["title"]:
                m["title"] = analyze._short_title(m["text"])
            m["yt_title"] = m["title"][:100]
            # Le nom du fichier = le titre : YouTube Studio le reprend tel quel à l'import
            m["file"] = publish.file_title(m["yt_title"], used)
            m["yt_description"] = publish.build_description(m, source_url, args.meta_lang)
            log(f"   #{rank:02d} {fmt(m['start'])}→{fmt(m['end'])} ({m['end'] - m['start']:.0f}s)"
                f"  score {m['score']:.0f}  {m['title']}")

        if not args.plan_only:
            log(f"⑥ Montage de {len(moments)} Shorts verticaux…")
            encoder = media.best_video_encoder()
            for m in moments:
                ass_name = None
                if not args.no_subs or not args.no_title:
                    ass_name = f"clip_{m['rank']:02d}.ass"
                    subtitles.build_ass(
                        words if not args.no_subs else [], m["start"], m["end"], work / ass_name,
                        title=None if args.no_title else (m["title"] or None),
                        title_full=args.layout == "blur", layout=args.layout, font=args.font,
                        uppercase=not args.no_upper, max_words=args.words,
                    )
                log(f"   [{m['rank']}/{len(moments)}] {m['file']}")
                render.render_clip(src, m["start"], m["end"], out_dir / m["file"],
                                   layout=args.layout, ass_name=ass_name, workdir=work,
                                   encoder=encoder, has_audio=info["has_audio"])

        write_report(out_dir, title, args.input, moments)
        page = publish.write_page(out_dir, title, moments)
        log(f"\n✅ Terminé en {fmt(time.time() - t0)} → {out_dir}")
        log("   Titres et descriptions à copier : publier.html")
        if args.open and sys.platform == "darwin":
            subprocess.run(["open", str(out_dir)])
            subprocess.run(["open", str(page)])
        return 0
    except KeyboardInterrupt:
        log("\nInterrompu.")
        return 130
    except Exception as exc:
        log(f"\n❌ {exc}")
        return 1


def write_report(out_dir: Path, title: str, origin: str, moments: list[dict]) -> None:
    keep = ("rank", "file", "start", "end", "yt_title", "yt_description", "hashtags",
            "score", "llm", "dynamic", "loudness_db", "cuts_per_min", "reason", "text")
    (out_dir / "shorts.json").write_text(json.dumps(
        {"video": title, "source": origin, "shorts": [{k: m.get(k) for k in keep} for m in moments]},
        ensure_ascii=False, indent=2))

    lines = [f"# Shorts — {title}", "", f"Source : {origin}", ""]
    for m in moments:
        lines += [
            f"## {m['rank']:02d}. {m['title'] or '(sans titre)'}",
            "",
            f"- Fichier : `{m['file']}`",
            f"- Extrait : {fmt(m['start'])} → {fmt(m['end'])} ({m['end'] - m['start']:.0f} s)",
            f"- Score : {m['score']:.0f}/100 (contenu {m['llm']:.0f}, rythme {m['dynamic']:.0f})",
        ]
        if m.get("reason"):
            lines.append(f"- Pourquoi : {m['reason']}")
        lines += ["", "**Description à copier :**", "", "```", m["yt_description"], "```"]
        lines += ["", "<details><summary>Transcription</summary>", "", m["text"], "", "</details>", ""]
    (out_dir / "shorts.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

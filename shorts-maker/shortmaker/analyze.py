"""Sélection des moments forts.

1. La transcription est découpée en phrases.
2. Un LLM local (Ollama) lit la transcription par fenêtres et propose des extraits
   (début/fin = numéros de phrases, donc toujours calés sur des phrases complètes).
   Sans LLM, une heuristique prend le relais (mots-clés, chiffres, accroche).
3. Chaque extrait reçoit un bonus « spectaculaire » mesuré sur le média lui-même :
   pics sonores (tirs, explosions, moteurs) et densité de changements de plan.
4. On garde les meilleurs extraits qui ne se chevauchent pas.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np

from . import llm
from .media import ENERGY_STEP

SENTENCE_END = re.compile(r"[.!?…]+[»\"')]*$")
SOFT_END = re.compile(r"[,;:]$")

# Débuts de phrase qui supposent un contexte précédent : mauvaise accroche
WEAK_STARTS = {
    "et", "mais", "donc", "alors", "puis", "ensuite", "car", "parce", "or", "ni",
    "aussi", "sinon", "enfin", "bref", "ainsi", "cependant", "pourtant", "lui",
    "elle", "ils", "elles", "celui", "celle", "ceux", "cela", "ça", "ce", "cet",
    "and", "but", "so", "then", "because", "which", "it", "they", "this", "that",
}

LEXICON = [
    # défense / militaire
    "missile", "missiles", "drone", "drones", "char", "chars", "tank", "frappe", "frappes",
    "explos", "bombe", "bombard", "obus", "artillerie", "torpille", "nucléaire", "atomique",
    "hypersonique", "furtif", "radar", "porte-avions", "sous-marin", "frégate", "destroyer",
    "chasseur", "rafale", "f-35", "su-", "mig", "himars", "patriot", "s-400", "javelin",
    "kamikaze", "munition", "balistique", "intercept", "abattu", "détruit", "anéanti",
    "offensive", "contre-offensive", "attaque", "assaut", "front", "tranchée", "soldat",
    "soldats", "troupes", "armée", "forces spéciales", "commando", "otan", "guerre",
    "conflit", "invasion", "riposte", "dissuasion", "menace", "escalade", "cible",
    "secret", "classifié", "renseignement", "espion",
    # intensité / surprise
    "jamais", "premier", "première", "seul", "seule", "record", "plus puissant",
    "le plus", "la plus", "incroyable", "terrifiant", "redoutable", "inédit", "historique",
    "choc", "révél", "personne", "impossible", "invisible", "vitesse", "mach",
    # chiffres
    "mille", "million", "milliard", "kilomètre", "km", "tonnes", "%", "pour cent",
]
NUMBER_RE = re.compile(r"\d")


# --------------------------------------------------------------------------- phrases

def build_sentences(words: list[dict], max_len: float = 20.0) -> list[dict]:
    sentences: list[dict] = []
    cur: list[int] = []

    def flush() -> None:
        if not cur:
            return
        ws = [words[k] for k in cur]
        sentences.append({
            "id": len(sentences),
            "s": ws[0]["s"],
            "e": ws[-1]["e"],
            "text": " ".join(w["w"] for w in ws),
            "wi": cur[0],
            "wj": cur[-1] + 1,
        })
        cur.clear()

    for k, w in enumerate(words):
        cur.append(k)
        nxt = words[k + 1] if k + 1 < len(words) else None
        dur = w["e"] - words[cur[0]]["s"]
        gap = (nxt["s"] - w["e"]) if nxt else 99
        if (SENTENCE_END.search(w["w"]) or gap > 0.9
                or (dur > max_len and SOFT_END.search(w["w"]))
                or dur > max_len * 1.6):
            flush()
    flush()
    return sentences


def _fmt(t: float) -> str:
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _first_word(text: str) -> str:
    m = re.search(r"[^\W\d_]+", text.lower())
    return m.group(0) if m else ""


# ----------------------------------------------------------------- bornes et durée

def fit_bounds(sents: list[dict], i: int, j: int, min_d: float, max_d: float) -> tuple[int, int] | None:
    n = len(sents)
    i, j = max(0, min(i, n - 1)), max(0, min(j, n - 1))
    if j < i:
        i, j = j, i
    # Trop court : on prolonge jusqu'à la durée minimale
    while j + 1 < n and sents[j]["e"] - sents[i]["s"] < min_d \
            and sents[j + 1]["e"] - sents[i]["s"] <= max_d:
        j += 1
    # Trop long : on retire des phrases à la fin
    while j > i and sents[j]["e"] - sents[i]["s"] > max_d:
        j -= 1
    if sents[j]["e"] - sents[i]["s"] < min_d * 0.75:
        return None
    return i, j


def clip_times(sents: list[dict], words: list[dict], i: int, j: int,
               max_d: float, duration: float) -> tuple[float, float]:
    s, e = sents[i]["s"], sents[j]["e"]
    if e - s > max_d:  # une seule phrase très longue : coupe sur une fin de mot
        ends = [w["e"] for w in words[sents[i]["wi"]: sents[j]["wj"]] if w["e"] <= s + max_d]
        e = ends[-1] if ends else s + max_d
    prev_end = words[sents[i]["wi"] - 1]["e"] if sents[i]["wi"] > 0 else 0.0
    nxt = [w for w in words[sents[i]["wi"]:] if w["s"] >= e - 0.01]
    next_start = nxt[0]["s"] if nxt else duration
    start = max(0.0, s - 0.15, min(s, prev_end + 0.02))
    end = min(duration, e + 0.45, max(e + 0.05, next_start - 0.05))
    return round(start, 2), round(end, 2)


# ------------------------------------------------------------------- proposition LLM

SYSTEM_PROMPT = """Tu es un monteur expert en YouTube Shorts pour une chaîne de \
reportages sur la défense, l'armée et la géopolitique militaire.
On te donne un extrait de transcription. Chaque ligne : [numéro] horodatage (durée) texte.
Ta mission : repérer les passages qui feront les Shorts les plus captivants et spectaculaires.

Ce qui fait un excellent Short pour ce type de chaîne :
- une accroche immédiate dès la première phrase : chiffre choc, révélation, affirmation forte, question intrigante, tension ;
- des capacités d'armes ou d'équipements impressionnantes, des records, des comparaisons entre puissances ;
- des moments de combat, de tension, de bascule, des anecdotes surprenantes ou méconnues, des coulisses ;
- une fin nette sur une phrase complète, idéalement une chute ou une phrase qui marque.

Règles strictes :
- l'extrait doit se comprendre SEUL, sans avoir vu la vidéo : ne commence jamais par « et », « mais », \
« donc », « il », « elle », « ce », « cela » qui renvoient à une phrase précédente ;
- durée entre {min_d} et {max_d} secondes (calcule avec les horodatages) ; la durée peut varier selon le moment ;
- évite l'introduction, la conclusion, les appels à s'abonner, les sponsors et les transitions ;
- les extraits ne doivent pas se chevaucher ;
- le score (0 à 100) est le potentiel viral réel : sois exigeant, 90+ seulement pour l'exceptionnel.

Réponds UNIQUEMENT avec ce JSON :
{{"clips": [{{"start_id": 12, "end_id": 19, "title": "titre accrocheur de 60 caractères max", \
"description": "1 à 2 phrases pour la description du Short", "hashtags": ["#defense", "#militaire"], \
"score": 78, "reason": "pourquoi ce moment fonctionne"}}]}}
Le titre, la description et les hashtags sont dans la langue de la vidéo."""


def _windows(sents: list[dict], span: float = 300.0, step: float = 240.0) -> list[list[dict]]:
    if not sents:
        return []
    out, t0, end = [], sents[0]["s"], sents[-1]["e"]
    while True:
        win = [s for s in sents if s["s"] >= t0 and s["s"] < t0 + span]
        if win:
            out.append(win)
        if t0 + span >= end:
            break
        t0 += step
    return out


def _score(value) -> float:
    try:
        return float(max(0.0, min(100.0, float(value))))
    except (TypeError, ValueError):
        return 50.0


def llm_candidates(sents: list[dict], model: str, video_title: str, count: int,
                   min_d: float, max_d: float, cache: Path, log) -> list[dict]:
    key = {"model": model, "min": min_d, "max": max_d, "count": count}
    if cache.exists():
        data = json.loads(cache.read_text())
        if data.get("key") == key:
            return data["clips"]

    windows = _windows(sents)
    per_window = max(3, math.ceil(count * 2.5 / max(1, len(windows))))
    system = SYSTEM_PROMPT.format(min_d=int(min_d), max_d=int(max_d))
    clips: list[dict] = []
    for n, win in enumerate(windows, 1):
        log(f"   LLM : fenêtre {n}/{len(windows)} ({_fmt(win[0]['s'])} → {_fmt(win[-1]['e'])})")
        lines = [f"[{s['id']}] {_fmt(s['s'])} ({s['e'] - s['s']:.0f}s) {s['text']}" for s in win]
        user = (f"Titre de la vidéo : {video_title}\n\nTranscription :\n" + "\n".join(lines)
                + f"\n\nPropose jusqu'à {per_window} extraits, du meilleur au moins bon.")
        try:
            resp = llm.chat_json(model, system, user)
        except Exception as exc:  # une fenêtre en échec ne bloque pas tout
            log(f"   ⚠️  fenêtre ignorée : {exc}")
            continue
        ids = {s["id"] for s in win}
        for c in resp.get("clips", []) if isinstance(resp, dict) else []:
            try:
                i, j = int(c["start_id"]), int(c["end_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if i not in ids:
                continue
            tags = c.get("hashtags") or []
            if isinstance(tags, str):
                tags = tags.split()
            clips.append({
                "i": i, "j": j,
                "title": str(c.get("title", "")).strip()[:90],
                "description": str(c.get("description", "")).strip(),
                "hashtags": [t if t.startswith("#") else "#" + t for t in map(str, tags) if t][:6],
                "llm": _score(c.get("score")),
                "reason": str(c.get("reason", "")).strip(),
            })
    cache.write_text(json.dumps({"key": key, "clips": clips}, ensure_ascii=False, indent=1))
    return clips


# --------------------------------------------------------------- heuristique sans LLM

def _keyword_hits(text: str) -> int:
    low = text.lower()
    return sum(low.count(k) for k in LEXICON) + len(NUMBER_RE.findall(low)) // 2


def _short_title(text: str, limit: int = 60) -> str:
    text = text.strip().rstrip(".!…")
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return cut + "…"


def heuristic_candidates(sents: list[dict], min_d: float, max_d: float) -> list[dict]:
    targets = sorted({max(min_d, min(max_d, t)) for t in (25.0, 40.0, 55.0)})
    clips = []
    for i, first in enumerate(sents):
        if _first_word(first["text"]) in WEAK_STARTS:
            continue
        for target in targets:
            j = i
            while j + 1 < len(sents) and sents[j + 1]["e"] - first["s"] <= target:
                j += 1
            fitted = fit_bounds(sents, i, j, min_d, max_d)
            if not fitted:
                continue
            i2, j2 = fitted
            text = " ".join(s["text"] for s in sents[i2: j2 + 1])
            dur = sents[j2]["e"] - sents[i2]["s"]
            density = _keyword_hits(text) / max(1.0, dur / 10)
            hook = min(3, _keyword_hits(first["text"])) + (1.5 if "?" in first["text"] else 0)
            clean_end = 1.0 if SENTENCE_END.search(sents[j2]["text"]) else 0.0
            raw = density * 2 + hook + clean_end
            title = _short_title(first["text"])
            clips.append({"i": i2, "j": j2, "title": title, "description": "",
                          "hashtags": [], "llm": raw, "reason": "sélection heuristique"})
    if clips:  # remet le score brut sur 0-100
        vals = np.array([c["llm"] for c in clips])
        ranks = vals.argsort().argsort() / max(1, len(vals) - 1)
        for c, r in zip(clips, ranks):
            c["llm"] = float(r * 100)
    return clips


# ----------------------------------------------------------------- score dynamique

def _rank(values: list[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2:
        return np.full(len(arr), 0.5)
    return arr.argsort().argsort() / (len(arr) - 1)


def score_and_select(clips: list[dict], energy: np.ndarray, cuts: list[float],
                     count: int, llm_weight: float) -> list[dict]:
    if not clips:
        return []
    baseline = float(np.median(energy)) if len(energy) else -40.0
    cuts_arr = np.asarray(cuts)
    loud, pace = [], []
    for c in clips:
        a, b = int(c["start"] / ENERGY_STEP), max(int(c["end"] / ENERGY_STEP), int(c["start"] / ENERGY_STEP) + 1)
        seg = energy[a:b] if len(energy) else np.zeros(1)
        loud.append(float(np.percentile(seg, 90)) - baseline if len(seg) else 0.0)
        dur = max(1.0, c["end"] - c["start"])
        n_cuts = int(((cuts_arr >= c["start"]) & (cuts_arr <= c["end"])).sum()) if len(cuts_arr) else 0
        pace.append(n_cuts / dur)
    dyn = (_rank(loud) + _rank(pace)) * 50
    for c, d, l, p in zip(clips, dyn, loud, pace):
        c["dynamic"] = round(float(d), 1)
        c["loudness_db"] = round(l, 1)
        c["cuts_per_min"] = round(p * 60, 1)
        c["score"] = round(llm_weight * c["llm"] + (1 - llm_weight) * float(d), 1)

    chosen: list[dict] = []
    for c in sorted(clips, key=lambda x: x["score"], reverse=True):
        if all(c["end"] <= o["start"] + 0.5 or c["start"] >= o["end"] - 0.5 for o in chosen):
            chosen.append(c)
        if len(chosen) == count:
            break
    return chosen


# ------------------------------------------------------------------------- façade

def find_moments(words: list[dict], duration: float, energy: np.ndarray, cuts: list[float],
                 *, count: int, min_d: float, max_d: float, model: str | None,
                 video_title: str, workdir: Path, log) -> list[dict]:
    sents = build_sentences(words)
    if not sents:
        raise RuntimeError("La transcription est vide : aucune parole détectée dans la vidéo.")

    raw: list[dict] = []
    llm_weight = 0.5
    if model:
        try:
            llm.check(model)
            raw = llm_candidates(sents, model, video_title, count, min_d, max_d,
                                 workdir / f"llm_{re.sub(r'[^A-Za-z0-9]+', '_', model)}.json", log)
            llm_weight = 0.7
        except llm.LLMUnavailable as exc:
            log(f"   ⚠️  {exc}\n   → sélection heuristique (sans IA) à la place.")
        if model and not raw:
            log("   ⚠️  Le LLM n'a rien proposé → sélection heuristique.")
            llm_weight = 0.5
    if not raw:
        raw = heuristic_candidates(sents, min_d, max_d)
    else:
        # Réserve : si l'IA propose trop peu de moments, l'heuristique complète
        # (avec un score réduit, elle ne passe jamais devant les choix de l'IA)
        for c in heuristic_candidates(sents, min_d, max_d):
            raw.append({**c, "llm": c["llm"] * 0.4, "reason": "complément heuristique"})

    clips = []
    for c in raw:
        fitted = fit_bounds(sents, c["i"], c["j"], min_d, max_d)
        if not fitted:
            continue
        i, j = fitted
        start, end = clip_times(sents, words, i, j, max_d, duration)
        clips.append({**c, "i": i, "j": j, "start": start, "end": end,
                      "text": " ".join(s["text"] for s in sents[i: j + 1])})
    chosen = score_and_select(clips, energy, cuts, count, llm_weight)
    if len(chosen) < count:
        log(f"   ℹ️  {len(chosen)} moments distincts trouvés (demandé : {count}).")
    return chosen

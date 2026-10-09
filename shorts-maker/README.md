# Shorts Maker

Tu donnes une vidéo YouTube (URL) ou un fichier `.mp4`, l'outil sort **10 Shorts verticaux**
des moments les plus forts : sous-titres animés, titre incrusté, son normalisé,
et un fichier avec les titres, descriptions et hashtags à copier-coller.

**Tout tourne sur ton Mac.** Pas d'abonnement, pas de clé API, pas de tokens : la transcription
(Whisper) et l'IA qui choisit les moments (Ollama) sont des modèles gratuits exécutés en local.
Seul le téléchargement de la vidéo depuis YouTube utilise Internet.

## Installation (une seule fois, ~10 min)

Dans le Terminal :

```bash
cd chemin/vers/Youtube-test/shorts-maker
./install.sh
```

Le script installe ffmpeg, Python, Ollama, les bibliothèques, et télécharge le modèle d'IA
adapté à la mémoire de ton Mac (`qwen3:8b` jusqu'à 16 Go, `qwen3:14b` à partir de 18 Go,
`qwen3:30b` à partir de 32 Go). Au premier lancement, Whisper télécharge aussi son modèle (~1,5 Go).

## Utilisation

### Avec l'icône du Bureau (le plus simple)

`install.sh` crée l'application **Shorts Maker** sur ton Bureau. Double-clique dessus :

1. colle l'URL YouTube **ou** clique sur *Choisir un fichier…* ;
2. choisis la mise en page : *Image entière (fond flouté)* ou *Plein écran* ;
3. indique le nombre de Shorts (10 par défaut).

Une fenêtre Terminal affiche la progression. À la fin, le dossier des Shorts s'ouvre tout seul.

> Au premier lancement, macOS demande si « Shorts Maker » peut contrôler Terminal : clique sur **OK**.
> Si tu déplaces le dossier `shorts-maker`, recrée l'icône avec `./create_app.sh`.

### Dans le Terminal

```bash
./make_shorts "https://www.youtube.com/watch?v=XXXXXXXXXXX"
./make_shorts ~/Movies/mon_reportage.mp4
```

Les Shorts arrivent dans `shorts/<titre-de-la-vidéo>/` :

```
01_le-missile-que-personne-ne-peut-arreter.mp4   ← classés du meilleur au moins bon
02_…
shorts.md     ← titre, description, hashtags et explication pour chaque Short
shorts.json
```

Compte quelques minutes pour une vidéo de 20-30 min sur une puce M5.
Relancer sur la même vidéo est quasi instantané : transcription et analyse sont gardées en cache.

## Comment les moments sont choisis

1. **Transcription** mot à mot avec Whisper (accéléré par le GPU de la puce M).
2. **Lecture par l'IA locale** : la transcription est lue par blocs de 5 minutes ; l'IA a pour
   consigne de repérer ce qui marche sur une chaîne défense/reportage (accroche immédiate,
   capacités d'armement, chiffres chocs, records, moments de tension, révélations, comparaisons
   entre puissances) et d'écarter l'intro, l'outro, les sponsors et les passages qui ne se
   comprennent pas sans contexte.
3. **Mesure du spectaculaire** sur la vidéo elle-même : pics sonores (tirs, explosions, moteurs)
   et rythme du montage (changements de plan).
4. **Score final** = 70 % contenu + 30 % spectaculaire. Les 10 meilleurs extraits sans
   chevauchement sont gardés.

Chaque Short commence et finit sur une **phrase complète**, avec une **durée variable**
(20 à 60 s par défaut) selon le moment.

## Mise en page

| `--layout` | Rendu | Quand l'utiliser |
|---|---|---|
| `blur` *(défaut)* | image 16:9 entière au centre, fond flouté, titre au-dessus, sous-titres en dessous | reportages : rien n'est coupé (cartes, incrustations, plans larges) |
| `crop` | plein écran, recadré au centre | images où l'action est au centre |

## Options utiles

| Option | Effet |
|---|---|
| `-n 15` | générer 15 Shorts au lieu de 10, pour avoir du choix |
| `--min 15 --max 90` | durées minimale et maximale (en secondes) |
| `--layout crop` | plein écran recadré |
| `--open` | ouvrir le dossier des Shorts dans le Finder à la fin |
| `--plan-only` | afficher les moments choisis sans monter les vidéos (rapide, pour vérifier) |
| `--no-title` | pas de titre incrusté en haut |
| `--no-subs` | pas de sous-titres |
| `--words 2` | 2 mots à l'écran à la fois (3 par défaut) |
| `--no-upper` | sous-titres en casse normale plutôt qu'en majuscules |
| `--font "Impact"` | changer la police |
| `--model qwen3:14b` | choisir un autre modèle Ollama |
| `--no-ai` | sélection sans IA (mots-clés + rythme), si Ollama n'est pas lancé |
| `--lang en` | forcer la langue parlée (par défaut elle est détectée : les sous-titres restent en anglais pour une vidéo en anglais) |
| `-o ~/Desktop/shorts` | changer le dossier de sortie |

Toutes les options : `./make_shorts --help`

## En cas de problème

- **« Ollama ne répond pas »** → `brew services start ollama`
  (sans Ollama, l'outil passe automatiquement en sélection sans IA).
- **« Ton ffmpeg n'a pas libass »** → relance `./install.sh`, il installe la version complète.
- **Échec du téléchargement YouTube** → mets yt-dlp à jour :
  `.venv/bin/pip install -U yt-dlp` (YouTube change régulièrement).
- **Un Short ne te plaît pas** → `-n 15` pour avoir plus de choix ; ils sont classés par score.

## Limites

- Les moments sont trouvés surtout à partir de **ce qui est dit** (voix off, interviews).
  Une séquence spectaculaire mais sans parole n'est repérée que par son volume sonore et son
  rythme de montage.
- Un modèle local est un peu moins fin qu'une grosse IA en ligne : sur 10 Shorts, attends-toi à
  en écarter un ou deux.

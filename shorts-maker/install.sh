#!/usr/bin/env bash
# Installation en une commande sur Mac (Apple Silicon). Tout tourne en local, rien de payant.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

say() { printf "\n\033[1m▶ %s\033[0m\n" "$1"; }

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Ce script vise macOS. Sous Linux : installe ffmpeg, python3, ollama, puis pip install -r requirements.txt"
fi

# 1. Homebrew
if ! command -v brew >/dev/null 2>&1; then
  say "Installation de Homebrew"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# 2. ffmpeg (avec libass pour les sous-titres), Python, Ollama
say "Installation de ffmpeg, Python et Ollama"
brew install python@3.12 ollama
if ! command -v ffmpeg >/dev/null 2>&1; then
  brew install ffmpeg
fi
# Liste capturée d'abord : avec pipefail, « ffmpeg | grep -q » échoue même quand libass est là
FILTERS=$(ffmpeg -hide_banner -filters 2>/dev/null || true)
if ! grep -qE '^\s*\S+\s+ass\s' <<<"$FILTERS"; then
  say "Ton ffmpeg n'a pas libass : installation de la version complète"
  brew uninstall --ignore-dependencies ffmpeg || true
  brew tap homebrew-ffmpeg/ffmpeg
  brew install homebrew-ffmpeg/ffmpeg/ffmpeg
fi

# 3. Environnement Python
say "Création de l'environnement Python"
PY="$(brew --prefix python@3.12)/bin/python3.12"
"$PY" -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt

# 4. Modèle d'IA local, choisi selon la mémoire du Mac
RAM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 17179869184) / 1073741824 ))
if   [ "$RAM_GB" -ge 32 ]; then MODEL="qwen3:30b"
elif [ "$RAM_GB" -ge 18 ]; then MODEL="qwen3:14b"
else                            MODEL="qwen3:8b"
fi
echo "$MODEL" > .ollama_model
say "Mac avec ${RAM_GB} Go de RAM → modèle $MODEL"
brew services start ollama >/dev/null 2>&1 || true
for _ in $(seq 1 20); do curl -s http://localhost:11434/api/tags >/dev/null && break; sleep 1; done
ollama pull "$MODEL"

chmod +x make_shorts create_app.sh
say "Création de l'icône « Shorts Maker » sur le Bureau"
./create_app.sh

say "Installation terminée ✅"
echo "Double-clique sur « Shorts Maker » sur ton Bureau, ou dans le Terminal :"
echo "  ./make_shorts \"https://www.youtube.com/watch?v=...\"   ou   ./make_shorts ma_video.mp4"

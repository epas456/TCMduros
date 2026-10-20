#!/usr/bin/env bash
# Instalador de durosTCM para Linux y macOS.
#
#   ./scripts/install.sh            instalación básica (editor + IA procedural + conexión a ComfyUI/Ollama)
#   ./scripts/install.sh --gpu      añade diffusers/torch para generar sin ComfyUI
#   ./scripts/install.sh --audio    añade voces neuronales Kokoro
#   ./scripts/install.sh --all      todo lo anterior + recorte de fondo (rembg)
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
EXTRAS=""
for arg in "$@"; do
  case "$arg" in
    --gpu) EXTRAS="${EXTRAS:+$EXTRAS,}gpu" ;;
    --audio) EXTRAS="${EXTRAS:+$EXTRAS,}audio" ;;
    --matting) EXTRAS="${EXTRAS:+$EXTRAS,}matting" ;;
    --all) EXTRAS="gpu,audio,matting" ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
  esac
done

say() { printf "\033[1;38;5;208m▶ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m⚠ %s\033[0m\n" "$*"; }

say "durosTCM · instalación en $ROOT"

PY=""
for cand in python3.12 python3.11 python3.13 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then PY="$cand"; break; fi
  fi
done
if [ -z "$PY" ]; then
  warn "Necesitas Python 3.10 o superior."
  if [ "$(uname)" = "Darwin" ]; then echo "  brew install python@3.12"; else echo "  sudo apt install python3 python3-venv"; fi
  exit 1
fi
say "Python: $($PY --version)"

if ! command -v ffmpeg >/dev/null 2>&1; then
  warn "FFmpeg no está instalado (es obligatorio)."
  if [ "$(uname)" = "Darwin" ]; then
    command -v brew >/dev/null && { say "Instalando FFmpeg con Homebrew…"; brew install ffmpeg; } || echo "  Instala Homebrew (https://brew.sh) y ejecuta: brew install ffmpeg"
  elif command -v apt-get >/dev/null; then
    say "Instalando FFmpeg con apt (puede pedir tu contraseña)…"; sudo apt-get update && sudo apt-get install -y ffmpeg
  elif command -v dnf >/dev/null; then
    sudo dnf install -y ffmpeg || echo "  Activa RPM Fusion y ejecuta: sudo dnf install ffmpeg"
  elif command -v pacman >/dev/null; then
    sudo pacman -S --noconfirm ffmpeg
  fi
fi
command -v ffmpeg >/dev/null && say "FFmpeg: $(ffmpeg -version | head -1)"

if [ ! -d .venv ]; then
  say "Creando entorno virtual .venv"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel >/dev/null
if [ -n "$EXTRAS" ]; then
  say "Instalando durosTCM con extras: $EXTRAS"
  pip install -e ".[$EXTRAS]"
else
  say "Instalando durosTCM"
  pip install -e .
fi

if [ ! -f durostcm/web/index.html ]; then
  if command -v npm >/dev/null 2>&1; then
    say "Compilando la interfaz web"
    npm --prefix frontend install --no-audit --no-fund && npm --prefix frontend run build
  else
    warn "No se encontró la interfaz compilada ni Node.js. Instala Node 18+ y ejecuta: npm --prefix frontend install && npm --prefix frontend run build"
  fi
fi

cat > durostcm.sh <<'EOS'
#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
exec python -m durostcm serve "$@"
EOS
chmod +x durostcm.sh

say "¡Listo! Arranca el estudio con:  ./durostcm.sh"
echo
echo "  Siguientes pasos recomendados (opcionales):"
echo "   • IA de imagen/vídeo fotorrealista: instala ComfyUI → ./scripts/setup_comfyui.sh"
echo "   • Guionista/director local: instala Ollama (https://ollama.com) y ejecuta: ollama pull qwen3:8b"
echo "   • Diagnóstico: source .venv/bin/activate && durostcm doctor"

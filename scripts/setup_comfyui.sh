#!/usr/bin/env bash
# Instala ComfyUI junto a durosTCM y lo deja configurado.
#
#   ./scripts/setup_comfyui.sh [carpeta]     (por defecto ~/ComfyUI)
#
# Después, desde durosTCM → Motores → Catálogo, pulsa «Descargar» en los modelos que
# quieras (Wan 2.2, FLUX, Qwen-Image…). Se guardan directamente en ComfyUI/models.
set -euo pipefail
DEST="${1:-$HOME/ComfyUI}"
say() { printf "\033[1;38;5;208m▶ %s\033[0m\n" "$*"; }

if [ ! -d "$DEST/.git" ]; then
  say "Clonando ComfyUI en $DEST"
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "$DEST"
fi
cd "$DEST"
PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
[ -d venv ] || "$PY" -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip wheel
if [ "$(uname)" = "Darwin" ]; then
  say "Instalando PyTorch (Apple Silicon / MPS)"
  pip install torch torchvision torchaudio
elif command -v nvidia-smi >/dev/null 2>&1; then
  say "Instalando PyTorch con CUDA 12.4"
  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
elif command -v rocm-smi >/dev/null 2>&1; then
  say "Instalando PyTorch con ROCm"
  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2
else
  say "Sin GPU detectada: PyTorch CPU (sólo útil para pruebas)"
  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
fi
pip install -r requirements.txt

cat > run_comfyui.sh <<'EOS'
#!/usr/bin/env bash
cd "$(dirname "$0")"
source venv/bin/activate
exec python main.py --listen 127.0.0.1 --port 8188 "$@"
EOS
chmod +x run_comfyui.sh

# Configurar durosTCM para que use esta instalación
CFG="${DUROSTCM_HOME:-$HOME/durosTCM}/config.yaml"
if [ -f "$CFG" ] && command -v python3 >/dev/null; then
  python3 - "$CFG" "$DEST" <<'EOP'
import sys, yaml
cfg, dest = sys.argv[1], sys.argv[2]
data = yaml.safe_load(open(cfg)) or {}
data.setdefault("endpoints", {})["comfyui_path"] = dest
yaml.safe_dump(data, open(cfg, "w"), allow_unicode=True, sort_keys=False)
print("durosTCM configurado: comfyui_path =", dest)
EOP
fi
say "Listo. Arranca ComfyUI con: $DEST/run_comfyui.sh  (y durosTCM lo detectará solo)"

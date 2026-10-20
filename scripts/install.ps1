# Instalador de durosTCM para Windows (PowerShell).
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1 [-Gpu] [-Audio] [-All]
param([switch]$Gpu, [switch]$Audio, [switch]$Matting, [switch]$All)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$Root = Get-Location

function Say($m) { Write-Host "> $m" -ForegroundColor DarkYellow }
function Warn($m) { Write-Host "! $m" -ForegroundColor Yellow }
function Invoke-Py([string]$cmd, [string[]]$rest) {
  $parts = $cmd.Split(" ")
  $pre = @()
  if ($parts.Length -gt 1) { $pre = $parts[1..($parts.Length - 1)] }
  & $parts[0] @pre @rest
}

Say "durosTCM · instalación en $Root"

$py = $null
foreach ($cand in @("py -3.12", "py -3.11", "py -3.13", "py -3.10", "python")) {
  try {
    $ok = Invoke-Py $cand @("-c", "import sys; print(sys.version_info >= (3,10))") 2>$null
    if ($ok -eq "True") { $py = $cand; break }
  } catch {}
}
if (-not $py) {
  Warn "Necesitas Python 3.10+. Instalándolo con winget…"
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  $py = "py -3.12"
}
Say "Python: $py"

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Warn "FFmpeg no está instalado. Instalándolo con winget (Gyan.FFmpeg)…"
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
  Warn "Cierra y vuelve a abrir la terminal si 'ffmpeg' no se reconoce todavía."
}

if (-not (Test-Path ".venv")) {
  Say "Creando entorno virtual .venv"
  Invoke-Py $py @("-m", "venv", ".venv")
}
$pip = ".\.venv\Scripts\python.exe"
& $pip -m pip install --upgrade pip wheel | Out-Null

$extras = @()
if ($All) { $extras = @("gpu", "audio", "matting") } else {
  if ($Gpu) { $extras += "gpu" }
  if ($Audio) { $extras += "audio" }
  if ($Matting) { $extras += "matting" }
}
if ($extras.Count -gt 0) {
  $spec = ".[" + ($extras -join ",") + "]"
  if ($extras -contains "gpu") {
    Say "Instalando PyTorch con CUDA 12.4"
    & $pip -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
  }
  Say "Instalando durosTCM $spec"
  & $pip -m pip install -e $spec
} else {
  Say "Instalando durosTCM"
  & $pip -m pip install -e .
}

if (-not (Test-Path "durostcm\web\index.html")) {
  if (Get-Command npm -ErrorAction SilentlyContinue) {
    Say "Compilando la interfaz"
    npm --prefix frontend install --no-audit --no-fund
    npm --prefix frontend run build
  } else { Warn "Falta la interfaz compilada: instala Node.js 18+ y ejecuta 'npm --prefix frontend install; npm --prefix frontend run build'" }
}

@"
@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m durostcm serve %*
"@ | Set-Content -Encoding ASCII durostcm.bat

Say "¡Listo! Arranca el estudio con doble clic en durostcm.bat"
Write-Host ""
Write-Host "  Opcional: ComfyUI portable (https://github.com/comfyanonymous/ComfyUI/releases) para IA fotorrealista"
Write-Host "  Opcional: Ollama (https://ollama.com) y 'ollama pull qwen3:8b' para el guionista local"

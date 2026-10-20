# durosTCM · estudio de cine con IA local

**durosTCM** es un estudio completo de producción de vídeo que se ejecuta en tu propio equipo:
editor profesional multipista + un equipo creativo de IA que escribe, dirige, genera cada plano,
pone voces y música, y exporta hasta **8K** en ProRes, DNxHR, HEVC, AV1 y más.

Pensado para una productora que necesita, por ejemplo, **un personaje hiperrealista en 4K en 2 horas**,
un anuncio para redes esta tarde o un cortometraje de prueba para un cliente — sin enviar nada a la nube.

> 🖥️ Sin GPU también funciona: el editor, el render, la exportación y un motor procedural de bocetos
> permiten maquetar storyboards y montar piezas. Con una GPU y ComfyUI/Ollama, la misma interfaz pasa a
> generar imágenes y vídeos fotorrealistas automáticamente.

---

## Qué incluye

| Área | Funciones |
|---|---|
| **Editor (NLE)** | Línea de tiempo multipista (vídeo, texto, audio), arrastrar y soltar, recorte por bordes, cuchilla, imantado, marcadores, entrada/salida, copiar/pegar, duplicar, eliminación con cierre de hueco, deshacer/rehacer ilimitado, autoguardado e historial de versiones |
| **Visor** | Compositor en tiempo real (Canvas) con transformaciones, keyframes, transiciones, etalonaje, textos animados y mezcla de audio · guías de zona segura · fotograma exacto y «previa exacta» renderizada con FFmpeg |
| **Inspector** | Posición/escala/rotación/opacidad con **keyframes** y curvas de suavizado, recorte, volteo, movimiento de cámara virtual (Ken Burns, paneos, cámara en mano), **etalonaje** (exposición, contraste, saturación, temperatura, matiz, sombras/altas luces, viñeta, grano, nitidez, LUT .cube) con 14 *looks* de cine, 15 efectos (croma, glow, VHS, película antigua, estabilizar, bandas cinemascope…), 44 transiciones, fundidos, volumen con keyframes |
| **Rotulación** | Títulos, subtítulos y rótulos inferiores con fuentes del sistema, contorno, sombra, caja, y animaciones (fundido, subir, bajar, zoom, máquina de escribir) |
| **Estudio IA** | Texto→imagen, texto→vídeo, imagen→vídeo (animar), variaciones con identidad del personaje (FLUX Kontext), voz (Kokoro/Piper), música, escalado a 4K/8K, interpolación a 60 fps / cámara lenta, quitar fondo · botón **«Imaginar»** que convierte una idea en un prompt de cine |
| **Director IA** | Pipelines automáticos: **Personaje hiperrealista 4K**, **Anuncio**, **Cortometraje** y **Storyboard**; con estimación de tiempo según tu hardware |
| **Reparto** | Biblias de personaje (rasgos, vestuario, voz, semilla, imágenes de referencia) y de localización reutilizables entre proyectos |
| **Rostros** | Búsqueda de rostros de inspiración con **licencia libre** (Openverse, Wikimedia Commons, Pexels, Unsplash), atribución automática, descripción de rasgos por visión IA, registro de **consentimientos** de personas reales |
| **Exportación** | MP4 H.264/H.265 10-bit, AV1, ProRes 422 HQ/4444 (alfa)/Proxy, DNxHR HQ/444, WebM VP9 (con alfa), GIF, secuencias PNG/JPG, WAV/MP3/FLAC/AAC · aceleración NVENC / VideoToolbox / Quick Sync · 480p→**8K**, DCI 4K · 11 presets de plataforma (YouTube 4K, TikTok, Reels, TV EBU R128, cine DCI…) · reencuadre automático a vertical con fondo difuminado · normalización de sonoridad (LUFS) · FCPXML (DaVinci Resolve/Final Cut), EDL, OpenTimelineIO, SRT |
| **Legal y ética** | Metadatos «generado con IA» y manifiesto de procedencia por render (Reglamento europeo de IA, art. 50), marca visible opcional, aviso de parecido con personas reales, licencias recalculadas en el servidor |

---

## Instalación

Requisitos: **Python 3.10+** y **FFmpeg** (los instaladores intentan instalarlo). Node.js sólo hace falta
si modificas la interfaz (ya viene compilada en `durostcm/web`).

### Windows
```powershell
git clone <este repositorio> durosTCM
cd durosTCM
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Audio
durostcm.bat
```

### macOS / Linux
```bash
git clone <este repositorio> durosTCM && cd durosTCM
./scripts/install.sh --audio        # --gpu añade diffusers/torch · --all instala todo
./durostcm.sh
```

Se abrirá **http://127.0.0.1:7777**. Tus proyectos se guardan en `~/durosTCM` (cámbialo con la variable `DUROSTCM_HOME`).

Diagnóstico de tu equipo y motores:
```bash
source .venv/bin/activate && durostcm doctor
```

### Docker (estudio completo con GPU NVIDIA)
```bash
cd docker && docker compose up -d --build
# durosTCM → http://localhost:7777 · ComfyUI → :8188 · Ollama → :11434
docker compose exec ollama ollama pull qwen3:8b
```

---

## Activar la IA fotorrealista

durosTCM detecta automáticamente qué tienes instalado y usa lo mejor disponible (con respaldo automático si algo falla).

1. **ComfyUI** (recomendado para imagen y vídeo):
   `./scripts/setup_comfyui.sh` (o ComfyUI Portable en Windows) y arráncalo.
   Después ve a **Motores → Catálogo** y pulsa **Descargar** en los modelos que quieras:

   | Tu GPU | Imagen | Vídeo |
   |---|---|---|
   | 8 GB | FLUX.1 schnell fp8 · SDXL | LTX-Video 2B · Wan 2.2 5B (con offload) |
   | 12–16 GB | FLUX.1 dev fp8 · FLUX Kontext | **Wan 2.2 TI2V 5B** (720p, 24 fps) |
   | 24 GB | **Qwen-Image** · FLUX.1 dev | **Wan 2.2 A14B** (calidad cine) |
   | 32–48 GB+ | Qwen-Image bf16 | Wan 2.2 A14B bf16, HunyuanVideo 1.5, LTX-2 (flujos propios) |

   ¿Tienes un flujo propio (LTX-2, HunyuanVideo 1.5, sincronía labial…)? Expórtalo desde ComfyUI con
   *Save (API)*, sustituye los valores por marcadores (`{{prompt}}`, `{{seed}}`, `{{width}}`, `{{height}}`,
   `{{frames}}`, `{{fps}}`, `{{image}}`, `{{audio}}`…) y guárdalo en `~/durosTCM/workflows/t2v_mi_flujo.json`
   (el prefijo indica la capacidad: `t2i`, `i2i`, `t2v`, `i2v`, `lip`, `up`…). Aparecerá en el Estudio IA.

2. **Ollama** (guionista y director creativo): instala [Ollama](https://ollama.com) y ejecuta
   `ollama pull qwen3:8b`. Para describir rostros de inspiración: `ollama pull qwen2.5vl:7b`.
   También vale cualquier servidor compatible con OpenAI (LM Studio, llama.cpp, vLLM).

3. **Voces**: `pip install durostcm[audio]` instala **Kokoro** (voces naturales en español e inglés; funciona en CPU).

4. **Escalado e interpolación neuronales** (opcional): descarga `realesrgan-ncnn-vulkan` y `rife-ncnn-vulkan`
   e indica sus rutas en **Ajustes → Motores IA**. Funcionan en GPUs NVIDIA, AMD, Intel y Apple.

5. **Sin ComfyUI**: con `--gpu` se instala diffusers y durosTCM puede ejecutar FLUX, Qwen-Image, Wan 2.2,
   LTX-Video o Stable Audio directamente desde Hugging Face.

> ⚖️ Revisa la licencia de cada modelo antes de un uso comercial. El catálogo indica un resumen orientativo
> (por ejemplo, Wan 2.2, Qwen-Image y FLUX.1 schnell son Apache 2.0; FLUX.1 dev es no comercial).

---

## Personaje hiperrealista 4K en 2 horas (flujo recomendado)

1. **Inicio → «Personaje hiperrealista 4K»** → elige 16:9 o 9:16.
2. En **Director IA** describe al personaje con detalles físicos concretos (edad, rasgos, piel, pelo, vestuario,
   una marca distintiva) y, si quieres, una localización.
3. *(Opcional)* En **Rostros** busca caras con licencia libre y márcalas: sus rasgos generales inspiran a una
   persona **nueva** (no se copia la identidad de nadie).
4. Mira la **estimación de tiempo** y pulsa **¡Acción!**. Referencia: en una RTX 4090 con Wan 2.2 5B una pieza
   de 24 s (con hoja de referencia y escalado a 4K) ronda los **50 minutos**; con Wan 2.2 A14B (máxima calidad)
   cuenta con 2–3 h o usa LoRAs de aceleración en tu flujo de ComfyUI. durosTCM:
   - escribe la biblia del personaje y la guarda en **Reparto**;
   - genera su **hoja de referencia** (frontal, ¾, perfil, cuerpo entero) con la misma semilla;
   - escala el retrato héroe a 4K;
   - planifica 6 planos (establecimiento, presentación, mirada, detalle de ojos, acción, plano héroe);
   - genera cada fotograma clave manteniendo la identidad (FLUX Kontext si está instalado) y lo anima (Wan 2.2);
   - escala los planos a 4K, compone música, rotula el nombre y monta todo en la línea de tiempo;
   - exporta un máster HEVC 10-bit 3840×2160 con metadatos y manifiesto de procedencia.
5. Refina en el editor (etalonaje, ritmo, rótulos) y vuelve a exportar en el formato que necesites.

Con el **Storyboard** puedes regenerar sólo el plano que no te convenza («Plano» / «Fotograma») y volver a montar.

---

## Atajos de teclado

| Tecla | Acción | Tecla | Acción |
|---|---|---|---|
| Espacio / K | Reproducir / pausa | J / L | Atrás 1 s / reproducir |
| ← → | Fotograma anterior / siguiente (Shift: 1 s) | Inicio / Fin | Ir al principio / final |
| S | Dividir en el cabezal | C / V | Cuchilla / selección |
| Supr | Eliminar · Shift+Supr cierra el hueco | N | Imantado |
| I / O / X | Entrada / salida / borrar rango | M | Marcador |
| T | Añadir texto | + / − / Ctrl+rueda | Zoom de la línea de tiempo |
| Ctrl+Z / Ctrl+Shift+Z | Deshacer / rehacer | Ctrl+C / Ctrl+V / Ctrl+D | Copiar / pegar / duplicar |
| Ctrl+S | Guardar | Ctrl+E | Exportar |

---

## Uso legal y responsable

- Las licencias CC0/CC BY/Pexels/Unsplash cubren la **fotografía**, no el **derecho a la propia imagen** de la
  persona retratada (LO 1/1982 en España, RGPD art. 9). durosTCM usa esos rostros sólo como inspiración y avisa
  cuando un prompt apunta a una persona real concreta.
- Para recrear a un actor, modelo o empleado real, registra su **cesión de derechos firmada** en
  *Rostros → Consentimientos*.
- El **Reglamento europeo de IA (art. 50)** obliga a señalar los contenidos sintéticos realistas: cada exportación
  incluye metadatos «generado con IA» y un manifiesto `.provenance.json` con modelos, semillas, licencias y créditos.
  Puedes añadir además una marca visible.
- durosTCM bloquea la generación de contenido sexual con menores.

---

## Arquitectura

```
durostcm/
  core/        modelo de proyecto, medios (ffprobe, proxies, ondas), motor de render FFmpeg,
               presets, etalonaje/efectos, keyframes, rotulación, cola de trabajos, biblioteca,
               hardware, intercambio (FCPXML/EDL/OTIO)
  ai/          motores: ComfyUI · diffusers · Ollama/OpenAI-compatible · Kokoro/Piper/sistema ·
               Real-ESRGAN · RIFE · rembg · A1111 · procedural; registro con respaldo automático;
               flujos ComfyUI integrados; catálogo y descargas de modelos;
               imagination/ = motor de imaginación (prompts de cine, personajes, localizaciones, storyboards)
  pipelines/   personaje 4K, anuncio, cortometraje, storyboard, producir planos, montar
  faces/       búsqueda de rostros con licencia libre y guardián ético
  server/      API REST + WebSocket (FastAPI) · documentación en /api/docs
  web/         interfaz compilada (fuente en frontend/, React + TypeScript + Vite)
```

El render final se construye como **un único filtergraph de FFmpeg**: cada clip se normaliza (recorte, velocidad,
marcha atrás, movimiento de cámara, etalonaje, efectos, transformaciones y fundidos), los clips con transición se
encadenan con `xfade`, las cadenas se superponen por pistas y el audio se mezcla con fundidos, keyframes de volumen
y normalización EBU R128. El visor del navegador reproduce una aproximación en tiempo real y la «previa exacta»
usa el mismo motor que la exportación.

### API
Todo lo que hace la interfaz está disponible por API (ver `http://127.0.0.1:7777/api/docs`). Ejemplo:
```bash
curl -X POST localhost:7777/api/pipelines/ad -H 'content-type: application/json' \
  -d '{"project_id":"p_xxx","params":{"product":"Aurora","duration":15,"aspect":"9:16"}}'
```
Línea de comandos: `durostcm render <id_proyecto> --format mov_prores_422hq --width 3840 --height 2160`.

### Desarrollo
```bash
pip install -e ".[dev]" && pytest -q                    # backend (incluye ComfyUI y Ollama simulados)
npm --prefix frontend install && npm --prefix frontend run dev   # interfaz en :5173 contra el backend en :7777
npm --prefix frontend run build                          # recompila durostcm/web
```

---

## Solución de problemas

- **«FFmpeg no encontrado»**: instálalo (`winget install Gyan.FFmpeg`, `brew install ffmpeg`, `sudo apt install ffmpeg`) o indica su ruta en Ajustes → Sistema.
- **La IA genera «bocetos»**: no hay ComfyUI/diffusers disponibles. Revisa **Motores** y `durostcm doctor`.
- **ComfyUI conectado pero «sin modelos compatibles»**: descarga un modelo desde **Motores → Catálogo** (configura antes la carpeta de ComfyUI en Ajustes).
- **Vídeos negros en el visor**: tu navegador no reproduce H.264; durosTCM genera automáticamente un proxy WebM (la primera carga tarda unos segundos).
- **Usarlo desde otro equipo de la red**: `durostcm serve --host 0.0.0.0` y define un token en Ajustes → Sistema.

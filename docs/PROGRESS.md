# durosTCM — Memoria de desarrollo (PROGRESS)

> Este archivo es la "memoria" del proyecto. Si la sesión de desarrollo se corta
> (créditos, contexto, reinicio), la siguiente sesión debe leer este archivo
> primero y continuar por la primera casilla sin marcar.

Rama de trabajo: `claude/durostcm-studio`

## Hitos

- [x] 1. Backend núcleo: modelo de proyecto/timeline, medios (ffprobe, miniaturas), motor de render FFmpeg, presets de exportación
- [x] 2. Motores IA: procedural (fallback CPU), ComfyUI, diffusers, Ollama (LLM), upscale, interpolación, TTS, música, cola de trabajos
- [x] 3. Motor de imaginación: personas creativas (Director, Guionista, Diseñador de personajes, Explorador de localizaciones, Director de fotografía), biblias de personaje/localización
- [x] 4. Pipelines: Personaje 4K, Anuncio, Cortometraje (brief → guion → storyboard → generación → timeline → export)
- [x] 5. Rostros de inspiración con licencia libre (Openverse, Wikimedia Commons, Pexels/Unsplash opcional) + guardián ético + procedencia/etiquetado IA
- [x] 6. Frontend: editor NLE (timeline multipista, inspector, biblioteca), previsualización, paneles IA, diálogo de exportación
- [x] 7. Instaladores (Linux/macOS/Windows), Docker (ComfyUI + Ollama), README en español, tests, CI

## Notas para retomar

- Backend: `durostcm/` (Python 3.10+, FastAPI). Arranque: `python -m durostcm serve`.
- Frontend: `frontend/` (Vite + React + TS). Build: `npm --prefix frontend run build` → servido por el backend.
- Tests: `pytest -q`.
- Sin GPU el motor `procedural` genera imágenes/vídeos de muestra para que todo el flujo funcione.

## Estado (sesión 1)

- Backend completo y probado (`pytest -q`: render, 20+ formatos, IA procedural, ComfyUI/Ollama simulados, API, pipelines, rostros).
- Frontend completo (editor NLE, visor, inspector, paneles IA, storyboard, exportación) y probado con Playwright.
- Instaladores (install.sh / install.ps1 / setup_comfyui.sh), Docker (durosTCM + ComfyUI + Ollama), README, CI: hechos.

## Hitos extra (sesión 1, en curso)

- [x] 8. Subtítulos automáticos por reconocimiento de voz (faster-whisper)
- [x] 9. Efectos de audio en el render (limpiar voz, reducción de ruido, eco, radio…)
- [x] 10. Detección de escenas (dividir metraje en planos) y marcas al ritmo de la música
- [ ] 11. Revisión final, tests completos, resumen al usuario

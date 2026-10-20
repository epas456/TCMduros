"""Reconocimiento de voz local con faster-whisper (subtítulos automáticos)."""

from __future__ import annotations

import asyncio
import importlib.util
import json

from ..base import Engine, EngineStatus, EngineUnavailable, GenContext, GenRequest, GenResult


class WhisperEngine(Engine):
    id = "whisper"
    name = "Whisper (faster-whisper)"
    description = "Transcribe diálogos y locuciones a subtítulos con marcas de tiempo, en 99 idiomas. GPU o CPU."
    capabilities = {"stt"}
    quality = "pro"

    def __init__(self) -> None:
        self._model = None
        self._model_name = ""

    async def status(self) -> EngineStatus:
        if importlib.util.find_spec("faster_whisper") is None:
            return EngineStatus(available=False, detail="pip install faster-whisper", quality="pro")
        return EngineStatus(available=True, detail="Instalado", models=["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"], quality="pro")

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        if importlib.util.find_spec("faster_whisper") is None:
            raise EngineUnavailable("faster-whisper no instalado")
        loop = asyncio.get_running_loop()

        def prog(v: float, s: str) -> None:
            asyncio.run_coroutine_threadsafe(ctx.progress(v, s), loop)

        return await asyncio.to_thread(self._run, req, ctx, prog)

    def _run(self, req: GenRequest, ctx: GenContext, prog) -> GenResult:
        from faster_whisper import WhisperModel

        name = req.model or "large-v3-turbo"
        if self._model is None or self._model_name != name:
            prog(0.02, f"Cargando Whisper {name}")
            device = "auto"
            try:
                self._model = WhisperModel(name, device=device, compute_type="auto")
            except Exception:
                self._model = WhisperModel(name, device="cpu", compute_type="int8")
            self._model_name = name
        src = req.video or req.audio or ""
        segments, info = self._model.transcribe(src, language=req.language or None, vad_filter=True, word_timestamps=False)
        out = []
        total = max(1.0, float(getattr(info, "duration", 0) or 1))
        for seg in segments:
            ctx.check()
            out.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip()})
            prog(min(0.98, seg.end / total), f"Transcribiendo {seg.end:.0f}/{total:.0f} s")
        p = ctx.path("subtitulos", "json")
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
        return GenResult(files=[str(p)], engine=self.id, model=name, meta={"segments": out, "language": getattr(info, "language", req.language)})

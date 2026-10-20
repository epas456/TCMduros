"""Motores de voz locales: Kokoro (neuronal, Apache 2.0), Piper (neuronal) y voz del sistema."""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from ...config import get_config
from ..base import Engine, EngineStatus, EngineUnavailable, GenContext, GenRequest, GenResult

KOKORO_VOICES = {
    "es": [("ef_dora", "Dora (mujer, ES)"), ("em_alex", "Álex (hombre, ES)"), ("em_santa", "Santa (hombre grave, ES)")],
    "en": [("af_heart", "Heart (mujer, US)"), ("af_bella", "Bella (mujer, US)"), ("am_michael", "Michael (hombre, US)"),
           ("am_fenrir", "Fenrir (hombre, US)"), ("bf_emma", "Emma (mujer, UK)"), ("bm_george", "George (hombre, UK)")],
    "fr": [("ff_siwis", "Siwis (mujer, FR)")],
    "it": [("if_sara", "Sara (mujer, IT)"), ("im_nicola", "Nicola (hombre, IT)")],
    "pt": [("pf_dora", "Dora (mujer, BR)"), ("pm_alex", "Alex (hombre, BR)")],
    "ja": [("jf_alpha", "Alpha (mujer, JA)")],
    "zh": [("zf_xiaobei", "Xiaobei (mujer, ZH)")],
}
_LANG_CODE = {"es": "e", "en": "a", "fr": "f", "it": "i", "pt": "p", "ja": "j", "zh": "z", "hi": "h"}


def _wav_duration(p: Path) -> float:
    try:
        with wave.open(str(p)) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


class KokoroEngine(Engine):
    id = "kokoro"
    name = "Kokoro TTS (neuronal, Apache 2.0)"
    description = "Voces naturales en español, inglés y más. 82M parámetros: funciona incluso en CPU."
    capabilities = {"tts"}
    quality = "pro"

    def __init__(self) -> None:
        self._pipes: dict[str, object] = {}

    async def status(self) -> EngineStatus:
        if importlib.util.find_spec("kokoro") is None:
            return EngineStatus(available=False, detail="pip install durostcm[audio]", quality="pro")
        return EngineStatus(available=True, detail="Instalado", models=[v for vs in KOKORO_VOICES.values() for v, _ in vs], quality="pro")

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        return await asyncio.to_thread(self._run, req, ctx)

    def _run(self, req: GenRequest, ctx: GenContext) -> GenResult:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline

        voice = req.voice or KOKORO_VOICES.get(req.language, KOKORO_VOICES["es"])[0][0]
        lang = voice[0] if voice and voice[0] in "abefhijpz" else _LANG_CODE.get(req.language, "e")
        pipe = self._pipes.get(lang)
        if pipe is None:
            pipe = KPipeline(lang_code=lang)
            self._pipes[lang] = pipe
        chunks = [audio for _gs, _ps, audio in pipe(req.text, voice=voice, speed=req.speech_speed)]
        if not chunks:
            raise RuntimeError("Kokoro no generó audio")
        audio = np.concatenate([np.asarray(c) for c in chunks])
        p = ctx.path(f"voz_{voice}", "wav")
        sf.write(str(p), audio, 24000)
        return GenResult(files=[str(p)], engine=self.id, model=f"kokoro:{voice}", meta={"duration": len(audio) / 24000, "voice": voice})


class PiperEngine(Engine):
    id = "piper"
    name = "Piper TTS"
    description = "Voces neuronales ligeras (ONNX). Configura la ruta del binario y la voz .onnx."
    capabilities = {"tts"}
    quality = "standard"

    async def status(self) -> EngineStatus:
        ep = get_config().settings.endpoints
        binary = ep.piper_bin or shutil.which("piper")
        if not binary:
            return EngineStatus(available=False, detail="Binario 'piper' no encontrado")
        if not ep.piper_voice or not Path(ep.piper_voice).exists():
            return EngineStatus(available=False, detail="Configura la voz .onnx de Piper")
        return EngineStatus(available=True, detail=Path(ep.piper_voice).stem, models=[Path(ep.piper_voice).stem])

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        ep = get_config().settings.endpoints
        binary = ep.piper_bin or shutil.which("piper")
        if not binary:
            raise EngineUnavailable("piper no instalado")
        p = ctx.path("voz_piper", "wav")
        args = [binary, "--model", ep.piper_voice, "--output_file", str(p), "--length_scale", f"{1 / max(0.3, req.speech_speed):.3f}"]
        proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _out, err = await proc.communicate(req.text.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(err.decode("utf-8", "ignore")[-500:])
        return GenResult(files=[str(p)], engine=self.id, model=Path(ep.piper_voice).stem, meta={"duration": _wav_duration(p)})


class SystemTTSEngine(Engine):
    id = "system"
    name = "Voz del sistema"
    description = "espeak-ng (Linux), say (macOS) o SAPI (Windows). Calidad básica, siempre útil para maquetas."
    capabilities = {"tts"}
    quality = "preview"

    def _backend(self) -> str | None:
        if sys.platform == "darwin" and shutil.which("say"):
            return "say"
        if sys.platform.startswith("win"):
            return "sapi"
        for b in ("espeak-ng", "espeak"):
            if shutil.which(b):
                return b
        return None

    async def status(self) -> EngineStatus:
        b = self._backend()
        return EngineStatus(available=b is not None, detail=b or "Instala espeak-ng", quality="preview")

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        b = self._backend()
        if b is None:
            raise EngineUnavailable("Sin voz del sistema")
        p = ctx.path("voz_sistema", "wav")
        if b == "say":
            aiff = p.with_suffix(".aiff")
            voice = req.voice or ("Monica" if req.language == "es" else "Samantha")
            cmd = ["say", "-v", voice, "-r", str(int(180 * req.speech_speed)), "-o", str(aiff), req.text]
            await asyncio.to_thread(subprocess.run, cmd, check=True, capture_output=True)
            from ...core.ffmpeg import run_ffmpeg

            await run_ffmpeg(["-i", str(aiff), str(p)], label="voz")
            aiff.unlink(missing_ok=True)
        elif b == "sapi":
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write(req.text)
                txt = f.name
            rate = int(max(-10, min(10, (req.speech_speed - 1) * 10)))
            ps = (
                "Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Rate={rate}; $s.SetOutputToWaveFile('{p}'); $t=Get-Content -Raw -Encoding UTF8 '{txt}'; $s.Speak($t); $s.Dispose()"
            )
            await asyncio.to_thread(subprocess.run, ["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True)
            Path(txt).unlink(missing_ok=True)
        else:
            lang = {"es": "es", "en": "en-us", "fr": "fr", "it": "it", "pt": "pt-br"}.get(req.language, req.language)
            cmd = [b, "-v", req.voice or lang, "-s", str(int(165 * req.speech_speed)), "-w", str(p), req.text]
            await asyncio.to_thread(subprocess.run, cmd, check=True, capture_output=True)
        return GenResult(files=[str(p)], engine=self.id, model=b, meta={"duration": _wav_duration(p)})


def list_voices() -> dict:
    return {"kokoro": KOKORO_VOICES}

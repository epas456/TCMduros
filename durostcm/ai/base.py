"""Interfaces comunes de los motores de IA."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

Capability = Literal[
    "text2image",
    "image2image",
    "text2video",
    "image2video",
    "upscale_image",
    "upscale_video",
    "interpolate",
    "tts",
    "music",
    "remove_bg",
    "lipsync",
    "llm",
    "vision",
    "stt",
]

CAPABILITY_LABELS: dict[str, str] = {
    "text2image": "Texto → Imagen",
    "image2image": "Imagen → Imagen",
    "text2video": "Texto → Vídeo",
    "image2video": "Imagen → Vídeo",
    "upscale_image": "Escalado de imagen (4K/8K)",
    "upscale_video": "Escalado de vídeo (4K)",
    "interpolate": "Interpolación de fotogramas (cámara lenta / 60fps)",
    "tts": "Voz (texto → habla)",
    "music": "Música",
    "remove_bg": "Quitar fondo",
    "lipsync": "Sincronía labial",
    "llm": "Cerebro creativo (LLM)",
    "vision": "Visión (describir imágenes)",
    "stt": "Subtítulos automáticos (voz → texto)",
}


class GenRequest(BaseModel):
    prompt: str = ""
    negative: str = ""
    width: int = 1280
    height: int = 720
    seed: int | None = None
    steps: int | None = None
    guidance: float | None = None
    duration: float = 4.0  # segundos (vídeo / música)
    fps: int = 24
    image: str | None = None  # ruta absoluta de imagen de entrada / fotograma inicial
    end_image: str | None = None  # fotograma final (si el modelo lo soporta)
    video: str | None = None  # ruta de vídeo de entrada (upscale, interpolar, lipsync)
    audio: str | None = None  # ruta de audio (lipsync)
    references: list[str] = Field(default_factory=list)  # imágenes de referencia (personaje)
    reference_weight: float = 0.8
    strength: float = 0.6  # img2img: cuánto cambia
    text: str = ""  # tts
    voice: str | None = None
    language: str = "es"
    speech_speed: float = 1.0
    model: str | None = None  # forzar modelo
    workflow: str | None = None  # forzar flujo ComfyUI
    scale: int = 2  # factor de escalado
    target_width: int | None = None
    target_height: int | None = None
    target_fps: int | None = None
    count: int = 1
    motion: str | None = None  # descripción del movimiento de cámara
    style: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def resolved_seed(self) -> int:
        if self.seed is None or self.seed < 0:
            self.seed = random.randint(0, 2**31 - 1)
        return self.seed


ProgressFn = Callable[[float, str], Awaitable[None]]


class GenContext:
    def __init__(self, out_dir: Path, progress: ProgressFn | None = None, cancel_event=None, log: Callable[[str], None] | None = None):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._progress = progress
        self.cancel_event = cancel_event
        self._log = log

    async def progress(self, v: float, stage: str = "") -> None:
        if self._progress:
            await self._progress(v, stage)

    def log(self, msg: str) -> None:
        if self._log:
            self._log(msg)

    def check(self) -> None:
        import asyncio

        if self.cancel_event is not None and self.cancel_event.is_set():
            raise asyncio.CancelledError()

    def path(self, stem: str, ext: str) -> Path:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = self.out_dir / f"{stem}_{stamp}"
        p = base.with_suffix(f".{ext}")
        i = 1
        while p.exists():
            p = self.out_dir / f"{stem}_{stamp}_{i}.{ext}"
            i += 1
        return p


class EngineStatus(BaseModel):
    available: bool
    detail: str = ""
    models: list[str] = Field(default_factory=list)
    quality: Literal["preview", "standard", "pro"] = "standard"


class GenResult(BaseModel):
    files: list[str]
    engine: str
    model: str = ""
    seed: int | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class Engine:
    id: str = "base"
    name: str = "Base"
    description: str = ""
    capabilities: set[str] = set()
    quality: Literal["preview", "standard", "pro"] = "standard"

    async def status(self) -> EngineStatus:
        return EngineStatus(available=False, detail="no implementado")

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        raise NotImplementedError

    def info(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "capabilities": sorted(self.capabilities),
            "quality": self.quality,
        }


class EngineUnavailable(RuntimeError):
    pass

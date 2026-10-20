"""Registro de motores de IA, detección de disponibilidad y selección con respaldo automático."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from ..config import get_config
from .base import CAPABILITY_LABELS, Engine, EngineStatus, EngineUnavailable, GenContext, GenRequest, GenResult
from .engines.comfyui import ComfyUIEngine
from .engines.diffusers_engine import DiffusersEngine
from .engines.llm import LLMEngine, OllamaEngine, OpenAICompatEngine
from .engines.procedural import ProceduralEngine
from .engines.speech import KokoroEngine, PiperEngine, SystemTTSEngine
from .engines.tools import A1111Engine, RealESRGANEngine, RembgEngine, RIFEEngine


class Registry:
    def __init__(self) -> None:
        self.engines: dict[str, Engine] = {}
        for e in (
            ComfyUIEngine(), DiffusersEngine(), A1111Engine(), RealESRGANEngine(), RIFEEngine(), RembgEngine(),
            KokoroEngine(), PiperEngine(), SystemTTSEngine(), OllamaEngine(), OpenAICompatEngine(), ProceduralEngine(),
        ):
            self.engines[e.id] = e
        self._status: dict[str, tuple[float, EngineStatus]] = {}

    async def status(self, engine_id: str, refresh: bool = False) -> EngineStatus:
        cached = self._status.get(engine_id)
        if cached and not refresh and time.time() - cached[0] < 20:
            return cached[1]
        e = self.engines[engine_id]
        try:
            st = await asyncio.wait_for(e.status(), timeout=8)
        except Exception as ex:  # noqa: BLE001
            st = EngineStatus(available=False, detail=f"Error: {ex}")
        self._status[engine_id] = (time.time(), st)
        return st

    async def all_status(self, refresh: bool = False) -> list[dict]:
        ids = list(self.engines)
        sts = await asyncio.gather(*(self.status(i, refresh) for i in ids))
        return [{**self.engines[i].info(), "status": st.model_dump()} for i, st in zip(ids, sts)]

    async def candidates(self, capability: str) -> list[Engine]:
        order = get_config().settings.engine_priority.get(capability, [])
        ids = [i for i in order if i in self.engines] + [i for i in self.engines if i not in order]
        out = []
        for i in ids:
            e = self.engines[i]
            if capability not in e.capabilities:
                continue
            st = await self.status(i)
            if not st.available:
                continue
            if isinstance(e, ComfyUIEngine) and not await e.has_capability(capability):
                continue
            out.append(e)
        return out

    async def capabilities(self) -> dict[str, dict]:
        out = {}
        for cap, label in CAPABILITY_LABELS.items():
            cands = await self.candidates(cap)
            out[cap] = {
                "label": label,
                "engines": [c.id for c in cands],
                "best": cands[0].id if cands else None,
                "quality": cands[0].quality if cands else None,
            }
        return out

    async def run(self, capability: str, req: GenRequest, ctx: GenContext, engine: str | None = None) -> GenResult:
        """Ejecuta con el motor pedido o el mejor disponible; si falla, prueba el siguiente."""
        if engine:
            e = self.engines.get(engine)
            if e is None:
                raise EngineUnavailable(f"Motor desconocido: {engine}")
            return await e.run(capability, req, ctx)
        cands = await self.candidates(capability)
        if not cands:
            raise EngineUnavailable(f"No hay ningún motor disponible para «{CAPABILITY_LABELS.get(capability, capability)}»")
        errors = []
        for e in cands:
            try:
                ctx.log(f"Motor: {e.name}")
                return await e.run(capability, req, ctx)
            except asyncio.CancelledError:
                raise
            except Exception as ex:  # noqa: BLE001
                errors.append(f"{e.name}: {ex}")
                ctx.log(f"Falló {e.name}: {ex} → probando el siguiente")
                self._status.pop(e.id, None)
        raise RuntimeError("Todos los motores fallaron:\n" + "\n".join(errors))

    async def llm(self) -> LLMEngine | None:
        for e in await self.candidates("llm"):
            if isinstance(e, LLMEngine):
                return e
        return None

    async def vision(self) -> LLMEngine | None:
        for e in await self.candidates("vision"):
            if isinstance(e, LLMEngine):
                return e
        return None


_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry


def out_dir_for(project_dir: Path, capability: str) -> Path:
    sub = {
        "text2image": "images", "image2image": "images", "upscale_image": "images", "remove_bg": "images",
        "text2video": "video", "image2video": "video", "upscale_video": "video", "interpolate": "video", "lipsync": "video",
        "tts": "voice", "music": "music",
    }.get(capability, "misc")
    d = project_dir / "generated" / sub
    d.mkdir(parents=True, exist_ok=True)
    return d

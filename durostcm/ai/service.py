"""Servicio de generación: ejecuta motores de IA y registra los resultados en el proyecto."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..core.jobs import JobContext, get_jobs
from ..core.media import make_proxy, needs_proxy, register_media
from ..core.project import Generation, MediaItem
from ..core.storage import get_store
from ..faces.ethics import check_prompt
from .base import GenContext, GenRequest
from .registry import get_registry, out_dir_for

_project_locks: dict[str, asyncio.Lock] = {}


def project_lock(pid: str) -> asyncio.Lock:
    return _project_locks.setdefault(pid, asyncio.Lock())


async def generate_media(
    ctx: JobContext,
    project_id: str,
    capability: str,
    req: GenRequest,
    *,
    engine: str | None = None,
    name: str | None = None,
    tags: list[str] | None = None,
    progress_range: tuple[float, float] = (0.0, 1.0),
    consent_ids: list[str] | None = None,
) -> list[MediaItem]:
    store = get_store()
    report = check_prompt(req.prompt, consent_ids)
    if report.level == "blocked":
        raise PermissionError("; ".join(report.issues))
    for issue in report.issues:
        ctx.log(f"⚠ {issue}")
    out_dir = out_dir_for(store.project_dir(project_id), capability)
    a, b = progress_range
    gctx = GenContext(out_dir, progress=ctx.sub(a, b), cancel_event=ctx.cancel_event, log=ctx.log)
    result = await get_registry().run(capability, req, gctx, engine)
    items: list[MediaItem] = []
    async with project_lock(project_id):
        p = store.get(project_id)
        for i, f in enumerate(result.files):
            gen = Generation(engine=result.engine, model=result.model, capability=capability, prompt=req.prompt or req.text,
                             negative=req.negative, seed=result.seed, params={k: v for k, v in req.model_dump().items()
                                                                               if k not in ("prompt", "negative", "text") and v not in (None, [], {}, "")})
            label = name or _auto_name(capability, req)
            if len(result.files) > 1:
                label = f"{label} {i + 1}"
            item = await asyncio.to_thread(register_media, store, p, Path(f), name=label, source="generated", generation=gen,
                                           tags=(tags or []) + [capability, result.engine])
            if result.meta.get("placeholder"):
                item.tags.append("guía")
            items.append(item)
        store.save(p)
    await get_jobs().broadcast({"type": "media_added", "project_id": project_id, "media": [m.model_dump() for m in items]})
    for item in items:
        if needs_proxy(item):
            schedule_proxy(project_id, item.id)
    return items


def _auto_name(capability: str, req: GenRequest) -> str:
    base = (req.prompt or req.text or capability).strip().replace("\n", " ")
    base = base.split(",")[0][:48]
    prefix = {"text2image": "IA·img", "image2image": "IA·var", "text2video": "IA·vid", "image2video": "IA·anim", "upscale_image": "4K·img",
              "upscale_video": "4K·vid", "interpolate": "Fluido", "tts": "Voz", "music": "Música", "remove_bg": "Recorte", "lipsync": "Labios"}.get(capability, "IA")
    return f"{prefix} · {base}"


def schedule_proxy(project_id: str, media_id: str) -> None:
    async def job(ctx: JobContext) -> dict:
        store = get_store()
        p = store.get(project_id)
        m = p.media_by_id(media_id)
        if m is None:
            return {}
        src = store.resolve(project_id, m.path)
        dst = store.subdir(project_id, "cache") / f"{m.id}_proxy.mp4"
        await make_proxy(src, dst, m.duration, progress=ctx.progress, cancel_event=ctx.cancel_event)
        async with project_lock(project_id):
            p = store.get(project_id)
            m = p.media_by_id(media_id)
            if m:
                m.proxy = store.relative(project_id, dst)
                store.save(p)
        await get_jobs().broadcast({"type": "media_updated", "project_id": project_id, "media": [m.model_dump()] if m else []})
        return {"proxy": str(dst.name)}

    get_jobs().submit("proxy", "Proxy de previsualización", job, project_id=project_id, pool="cpu")


async def media_path(project_id: str, media_id: str) -> Path:
    store = get_store()
    p = store.get(project_id)
    m = p.media_by_id(media_id)
    if m is None:
        raise KeyError(media_id)
    return store.resolve(project_id, m.path)


def request_from(params: dict[str, Any]) -> GenRequest:
    allowed = set(GenRequest.model_fields)
    return GenRequest(**{k: v for k, v in params.items() if k in allowed})

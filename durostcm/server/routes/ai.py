"""Rutas de IA: motores, generación, imaginación, pipelines, modelos y flujos ComfyUI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ... import pipelines as P
from ...ai import catalog as model_catalog
from ...ai import workflows as W
from ...ai.base import CAPABILITY_LABELS
from ...ai.engines.speech import list_voices
from ...ai.imagination import engine as IM
from ...ai.registry import get_registry
from ...ai.service import generate_media, media_path, request_from
from ...core.jobs import JobContext, get_jobs
from ...core.project import Camera
from ...core.storage import get_store
from ...faces.ethics import check_prompt

router = APIRouter()


@router.get("/ai/engines")
async def engines(refresh: bool = False):
    reg = get_registry()
    return {"engines": await reg.all_status(refresh), "capabilities": await reg.capabilities(), "labels": CAPABILITY_LABELS}


@router.get("/ai/voices")
async def voices():
    return list_voices()


@router.get("/ai/workflows")
async def workflows(capability: str | None = None):
    reg = get_registry()
    comfy = reg.engines["comfyui"]
    out = []
    try:
        caps = [capability] if capability else sorted({w["meta"]["capability"] for w in W.all_workflows().values()})
        for cap in caps:
            out += await comfy.workflows_for(cap)  # type: ignore[attr-defined]
    except Exception:
        out = [{**w["meta"], "available": None, "missing": []} for w in W.all_workflows().values() if not capability or w["meta"]["capability"] == capability]
    return {"workflows": out}


class WorkflowUpload(BaseModel):
    name: str
    capability: str
    label: str = ""
    workflow: dict


@router.post("/ai/workflows")
async def add_workflow(body: WorkflowUpload):
    p = W.save_user_workflow(body.name, {"capability": body.capability, "label": body.label or body.name}, body.workflow)
    return {"saved": p.name}


class GenerateBody(BaseModel):
    project_id: str
    capability: str
    params: dict[str, Any] = Field(default_factory=dict)
    engine: str | None = None
    name: str | None = None
    source_media_id: str | None = None  # imagen/vídeo de entrada desde el proyecto
    reference_media_ids: list[str] = Field(default_factory=list)
    audio_media_id: str | None = None
    consent_ids: list[str] = Field(default_factory=list)


@router.post("/ai/generate")
async def generate(body: GenerateBody):
    if body.capability not in CAPABILITY_LABELS:
        raise HTTPException(400, "Capacidad desconocida")
    get_store().get(body.project_id)
    req = request_from(body.params)
    report = check_prompt(req.prompt or req.text, body.consent_ids)
    if report.level == "blocked":
        raise HTTPException(403, "; ".join(report.issues))

    async def job(ctx: JobContext):
        if body.source_media_id:
            path = str(await media_path(body.project_id, body.source_media_id))
            if body.capability in ("upscale_video", "interpolate", "lipsync"):
                req.video = path
            else:
                req.image = path
        for mid in body.reference_media_ids:
            req.references.append(str(await media_path(body.project_id, mid)))
        if body.audio_media_id:
            req.audio = str(await media_path(body.project_id, body.audio_media_id))
        items = await generate_media(ctx, body.project_id, body.capability, req, engine=body.engine, name=body.name, consent_ids=body.consent_ids)
        return {"media": [m.model_dump() for m in items], "warnings": report.issues}

    pool = "gpu" if body.capability not in ("tts", "music") else "cpu"
    j = get_jobs().submit(f"ai:{body.capability}", f"{CAPABILITY_LABELS[body.capability]}", job, project_id=body.project_id, pool=pool)
    return {**j.public(), "ethics": report.model_dump()}


# ------------------------------------------------------------------ imaginación
class EnhanceBody(BaseModel):
    idea: str
    kind: str = "image"
    style: str = "cinematic"
    realism: float = 1.0
    imagination: float = 0.5
    seed: int | None = None
    use_llm: bool = True
    camera: Camera | None = None
    look: str | None = None


@router.post("/ai/imagine/prompt")
async def imagine_prompt(body: EnhanceBody):
    if body.use_llm:
        llm = await get_registry().llm()
        if llm is not None:
            try:
                data = await IM.llm_enhance(llm, body.idea, body.kind, body.imagination)
                if data:
                    return {"prompt": data.get("prompt"), "negative": data.get("negative") or IM.V.NEGATIVE_IMAGE, "title": data.get("title", ""), "source": "llm"}
            except Exception:
                pass
    r = IM.enhance_prompt(body.idea, kind=body.kind, style=body.style, realism=body.realism, imagination=body.imagination,
                          seed=body.seed, camera=body.camera, look=body.look)
    return {**r, "source": "imagination"}


@router.post("/ai/imagine/variations")
async def imagine_variations(body: EnhanceBody, n: int = 4):
    base = body.seed if body.seed is not None else 0
    return {"variations": [IM.enhance_prompt(body.idea, kind=body.kind, style=body.style, realism=body.realism,
                                             imagination=body.imagination, seed=base + i * 7919, camera=body.camera, look=body.look) for i in range(max(1, min(8, n)))]}


@router.post("/ai/check")
async def ethics_check(body: dict):
    return check_prompt(str(body.get("text", "")), body.get("consent_ids") or []).model_dump()


# ------------------------------------------------------------------ pipelines
class PipelineBody(BaseModel):
    project_id: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.get("/pipelines")
async def pipelines():
    return {"pipelines": [{"id": k, "label": v["label"]} for k, v in P.PIPELINES.items()]}


@router.post("/pipelines/{name}/plan")
async def plan(name: str, body: PipelineBody):
    if name not in P.PIPELINES:
        raise HTTPException(404, "Pipeline desconocido")
    return P.plan(name, body.params)


@router.post("/pipelines/{name}")
async def run_pipeline(name: str, body: PipelineBody):
    if name not in P.PIPELINES:
        raise HTTPException(404, "Pipeline desconocido")
    get_store().get(body.project_id)
    text = " ".join(str(v) for v in body.params.values() if isinstance(v, str))
    report = check_prompt(text)
    if report.level == "blocked":
        raise HTTPException(403, "; ".join(report.issues))
    j = P.start(name, body.project_id, body.params)
    return {**j.public(), "ethics": report.model_dump()}


# ------------------------------------------------------------------ modelos
@router.get("/models")
async def models():
    return {"models": model_catalog.catalog(), "comfyui_models_dir": str(model_catalog.comfy_models_dir() or "")}


@router.post("/models/{model_id}/download")
async def download_model(model_id: str):
    entry = next((e for e in model_catalog.CATALOG if e["id"] == model_id), None)
    if entry is None:
        raise HTTPException(404, "Modelo desconocido")

    async def job(ctx: JobContext):
        return await model_catalog.download_entry(ctx, model_id)

    j = get_jobs().submit("download", f"Descargar {entry['name']}", job, pool="io")
    return j.public()

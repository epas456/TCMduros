"""Rutas de sistema: salud, ajustes, hardware, presets, fuentes, LUTs y trabajos."""

from __future__ import annotations

import asyncio
import shutil

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ... import APP_NAME, __version__
from ...config import get_config
from ...core import hardware
from ...core.ffmpeg import ffmpeg_version, has_ffmpeg
from ...core.jobs import get_jobs
from ...core.looks import AUDIO_EFFECTS, EFFECTS, TRANSITIONS, list_looks
from ...core.presets import catalog as presets_catalog
from ...core.text import font_path, list_fonts

router = APIRouter()


@router.get("/health")
async def health():
    return {"ok": True, "app": APP_NAME, "version": __version__}


@router.get("/system")
async def system():
    hw = await asyncio.to_thread(hardware.detect)
    return {
        "app": APP_NAME,
        "version": __version__,
        "home": str(get_config().home),
        "ffmpeg": {"ok": has_ffmpeg(), "version": ffmpeg_version()},
        "hardware": hw,
        "recommendations": hardware.recommendations(hw["tier"]),
        "tier_label": hardware.TIERS.get(hw["tier"], {}).get("label", hw["tier"]),
    }


@router.get("/settings")
async def get_settings():
    return get_config().settings.model_dump()


@router.patch("/settings")
async def patch_settings(patch: dict):
    s = get_config().update(patch)
    from ...ai.registry import get_registry

    get_registry()._status.clear()
    return s.model_dump()


@router.get("/presets")
async def presets():
    return {**presets_catalog(), "looks": list_looks(), "effects": EFFECTS, "audio_effects": AUDIO_EFFECTS, "transitions": TRANSITIONS}


@router.get("/fonts")
async def fonts():
    return {"fonts": await asyncio.to_thread(list_fonts)}


@router.get("/fonts/file/{name}")
async def font_file(name: str, weight: str = "normal"):
    p = font_path(name, weight)
    if p is None:
        raise HTTPException(404, "Fuente no encontrada")
    return FileResponse(p)


@router.get("/luts")
async def luts():
    d = get_config().luts_dir
    return {"luts": sorted(f.name for f in d.iterdir() if f.suffix.lower() in (".cube", ".3dl", ".dat", ".m3d", ".csp"))}


@router.post("/luts")
async def upload_lut(file: UploadFile = File(...)):
    name = "".join(ch for ch in (file.filename or "lut.cube") if ch.isalnum() or ch in "._- ")
    if not name.lower().endswith((".cube", ".3dl", ".dat", ".m3d", ".csp")):
        raise HTTPException(400, "Formato de LUT no soportado (.cube, .3dl)")
    dst = get_config().luts_dir / name
    with open(dst, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"name": name}


# ------------------------------------------------------------------ trabajos
@router.get("/jobs")
async def jobs(project_id: str | None = None):
    return {"jobs": get_jobs().list(project_id)}


@router.get("/jobs/{job_id}")
async def job(job_id: str):
    j = get_jobs().get(job_id)
    if j is None:
        raise HTTPException(404, "Trabajo no encontrado")
    return j.public()


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str):
    return {"ok": get_jobs().cancel(job_id)}


@router.delete("/jobs")
async def clear():
    return {"removed": get_jobs().clear_finished()}

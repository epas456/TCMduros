"""Herramientas de postproducción: subtítulos automáticos/SRT, detección de escenas y de ritmo."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ...ai.base import GenContext, GenRequest
from ...ai.registry import get_registry
from ...ai.service import project_lock
from ...core.analysis import detect_beats, detect_scenes, parse_srt
from ...core.jobs import JobContext, get_jobs
from ...core.project import Clip, Project, TextStyle, Track, Transform
from ...core.storage import get_store

router = APIRouter()


def subtitle_track(p: Project) -> Track:
    for t in p.tracks:
        if t.kind == "text" and any(k in t.name.lower() for k in ("subt", "subs", "caption")):
            return t
    t = Track(name="Subtítulos", kind="text")
    idx = max((i for i, x in enumerate(p.tracks) if x.kind in ("video", "text")), default=-1)
    p.tracks.insert(idx + 1, t)
    return t


def add_subtitles(p: Project, items: list[dict], replace_range: tuple[float, float] | None = None) -> int:
    track = subtitle_track(p)
    if replace_range:
        a, b = replace_range
        track.clips = [c for c in track.clips if c.end <= a or c.start >= b]
    n = 0
    for it in items:
        start, end, text = float(it["start"]), float(it["end"]), str(it["text"]).strip()
        if not text or end - start < 0.05:
            continue
        track.clips.append(Clip(kind="text", start=round(start, 3), duration=round(end - start, 3), name="Subtítulo",
                                text=TextStyle(content=text, size=0.042, weight="normal", background="#000000A0", shadow=False, animation="none", max_width=0.82),
                                transform=Transform(x=0.5, y=0.88)))
        n += 1
    track.clips.sort(key=lambda c: c.start)
    return n


class AutoSubs(BaseModel):
    clip_id: str
    language: str | None = "es"
    model: str | None = None


@router.post("/projects/{pid}/subtitles/auto")
async def auto_subtitles(pid: str, body: AutoSubs):
    store = get_store()
    p = store.get(pid)
    found = p.find_clip(body.clip_id)
    if not found:
        raise HTTPException(404, "Clip no encontrado")
    _track, clip = found
    m = p.media_by_id(clip.media_id)
    if m is None or not m.has_audio:
        raise HTTPException(400, "El clip no tiene audio")
    src = store.resolve(pid, m.path)

    async def job(ctx: JobContext):
        gctx = GenContext(store.subdir(pid, "cache") / "stt", progress=ctx.progress, cancel_event=ctx.cancel_event, log=ctx.log)
        res = await get_registry().run("stt", GenRequest(video=str(src), language=body.language, model=body.model), gctx)
        segs = res.meta.get("segments", [])
        # pasar del tiempo de origen al tiempo de la línea de tiempo
        items = []
        for s in segs:
            a = clip.start + (s["start"] - clip.in_point) / clip.speed
            b = clip.start + (s["end"] - clip.in_point) / clip.speed
            a, b = max(a, clip.start), min(b, clip.end)
            if b > a:
                items.append({"start": a, "end": b, "text": s["text"]})
        async with project_lock(pid):
            proj = store.get(pid)
            n = add_subtitles(proj, items, replace_range=(clip.start, clip.end))
            store.bump(proj)
        await get_jobs().broadcast({"type": "project_changed", "project_id": pid})
        return {"subtitles": n, "language": res.meta.get("language")}

    j = get_jobs().submit("stt", "Subtítulos automáticos", job, project_id=pid, pool="gpu")
    return j.public()


@router.post("/projects/{pid}/subtitles/import")
async def import_srt(pid: str, file: UploadFile = File(...), offset: float = Form(0.0)):
    raw = (await file.read()).decode("utf-8-sig", "ignore")
    items = parse_srt(raw)
    if not items:
        raise HTTPException(400, "No se encontraron subtítulos en el archivo")
    for it in items:
        it["start"] += offset
        it["end"] += offset
    store = get_store()
    async with project_lock(pid):
        p = store.get(pid)
        n = add_subtitles(p, items)
        store.bump(p)
    await get_jobs().broadcast({"type": "project_changed", "project_id": pid})
    return {"subtitles": n}


def _media_path(pid: str, mid: str) -> Path:
    store = get_store()
    m = store.get(pid).media_by_id(mid)
    if m is None:
        raise HTTPException(404, "Medio no encontrado")
    return store.resolve(pid, m.path)


@router.get("/projects/{pid}/media/{mid}/scenes")
async def scenes(pid: str, mid: str, threshold: float = 0.35):
    path = _media_path(pid, mid)
    cuts = await asyncio.to_thread(detect_scenes, path, max(0.05, min(0.95, threshold)))
    return {"cuts": cuts}


@router.get("/projects/{pid}/media/{mid}/beats")
async def beats(pid: str, mid: str):
    path = _media_path(pid, mid)
    return await asyncio.to_thread(detect_beats, path)

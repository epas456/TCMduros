"""Pipelines de producción automática.

* ``character_4k``  — Personaje hiperrealista 4K: biblia → hoja de referencia → retrato héroe 4K →
  planos animados con identidad consistente → escalado 4K → montaje → exportación.
* ``ad``            — Anuncio: brief → storyboard (gancho/deseo/revelación/beneficio/cierre) → planos →
  locución → música con ducking → rótulos y logo → montaje.
* ``short_film``    — Cortometraje: idea → guion en 8 tiempos → personajes/localización → planos →
  diálogos con voces por personaje → subtítulos → música → montaje.
* ``storyboard``    — Sólo escribe el storyboard (para revisarlo antes de generar).
* ``produce``       — Genera los planos de un storyboard existente (todos o algunos).
* ``assemble``      — Monta en la línea de tiempo lo ya generado.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

from ..ai.base import GenRequest
from ..ai.imagination import engine as IM
from ..ai.registry import get_registry
from ..ai.service import generate_media
from ..core.hardware import estimate
from ..core.jobs import JobContext, get_jobs
from ..core.library import Character, get_library
from ..core.render import RenderSettings, render_project
from ..core.storage import get_store
from . import common as C


async def _llm():
    try:
        return await get_registry().llm()
    except Exception:
        return None


# ------------------------------------------------------------------ personaje 4K


async def character_4k(ctx: JobContext, pid: str, params: dict[str, Any]) -> dict:
    brief = params.get("description", "")
    aspect = params.get("aspect", "16:9")
    duration = float(params.get("duration", 24))
    imagination = float(params.get("imagination", 0.6))
    seed = params.get("seed") or random.randint(0, 2**31 - 1)
    lib = get_library()
    await C.set_canvas(pid, aspect, 24, uhd=True)

    # 1. Personaje
    await ctx.progress(0.01, "Diseñando personaje")
    character: Character | None = None
    if params.get("character_id"):
        character = lib.get("characters", params["character_id"])  # type: ignore[assignment]
    else:
        inspiration = ""
        face_ids = params.get("face_ids") or []
        if face_ids:
            faces = {f.id: f for f in lib.faces()}
            descs = [faces[i].description for i in face_ids if i in faces and faces[i].description]
            if descs:
                inspiration = " | ".join(descs)
        llm = await _llm()
        if llm is not None:
            try:
                character = await IM.llm_character(llm, brief, inspiration)
            except Exception as e:  # noqa: BLE001
                ctx.log(f"LLM no disponible para el personaje: {e}")
        if character is None:
            character = IM.design_character(brief, seed=seed, imagination=imagination)
            if inspiration:
                character.identity_prompt += f", subtle features inspired by: {inspiration[:300]}"
        if face_ids:
            faces = {f.id: f for f in lib.faces()}
            character.inspiration = [faces[i].credit for i in face_ids if i in faces]
        character.seed = character.seed or seed
        lib.save("characters", character)
    location = IM.design_location(params.get("location", ""), seed=seed + 1, imagination=imagination)
    lib.save("locations", location)
    await C.link_library(pid, [character], [location])

    # 2. Hoja de referencia
    views = IM.character_turnaround_prompts(character)[: int(params.get("reference_views", 4))]
    preview = await C.is_preview_only("text2image")
    w, h = (896, 1152) if not preview else (640, 832)
    hero_item = None
    for i, v in enumerate(views):
        a = 0.03 + 0.17 * i / len(views)
        b = 0.03 + 0.17 * (i + 1) / len(views)
        await ctx.progress(a, f"Hoja de referencia: {v['view']}")
        items = await generate_media(ctx, pid, "text2image", GenRequest(prompt=v["prompt"], negative=v["negative"], width=w, height=h, seed=character.seed),
                                     name=f"{character.name} · {v['view']}", tags=["personaje", character.id], progress_range=(a, b))
        if items:
            src = get_store().resolve(pid, items[0].path)
            lib.add_image("characters", character.id, src, as_hero=(i == 0))
            if i == 0:
                hero_item = items[0]
    character = lib.get("characters", character.id)  # type: ignore[assignment]

    # 3. Retrato héroe en 4K
    if hero_item is not None:
        await ctx.progress(0.2, "Escalando retrato héroe a 4K")
        try:
            await generate_media(ctx, pid, "upscale_image", GenRequest(image=str(get_store().resolve(pid, hero_item.path)), scale=4, target_height=3840 if aspect == "9:16" else 2160),
                                 name=f"{character.name} · retrato 4K", tags=["personaje", "4k"], progress_range=(0.2, 0.25))
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Escalado del retrato: {e}")

    # 4. Storyboard de presentación y planos
    sb, _loc = IM.storyboard_character(character, location, duration=duration, seed=seed)  # type: ignore[arg-type]
    for i, s in enumerate(sb.shots):
        s.seed = (character.seed or seed) + i
    await C.save_storyboard(pid, sb)
    await C.produce_shots(ctx, pid, sb, aspect, (0.25, 0.75))

    # 5. Escalado 4K de los planos
    store = get_store()
    if params.get("upscale", True):
        p = store.get(pid)
        vids = [s for s in sb.shots if s.video_media_id]
        for i, s in enumerate(vids):
            m = p.media_by_id(s.video_media_id)
            if m is None or (m.height or 0) >= 2000:
                continue
            a = 0.75 + 0.13 * i / max(1, len(vids))
            b = 0.75 + 0.13 * (i + 1) / max(1, len(vids))
            await ctx.progress(a, f"Escalando plano {s.index + 1} a 4K")
            tw, th = C.CANVAS_4K.get(aspect, (3840, 2160))
            try:
                items = await generate_media(ctx, pid, "upscale_video", GenRequest(video=str(store.resolve(pid, m.path)), scale=4, target_width=tw, target_height=th),
                                             name=f"Plano {s.index + 1} · 4K", tags=["4k", s.id], progress_range=(a, b))
                if items:
                    s.video_media_id = items[0].id
                    await C.update_shot(pid, s.id, video_media_id=items[0].id)
            except Exception as e:  # noqa: BLE001
                ctx.log(f"Escalado plano {s.index + 1}: {e}")

    # 6. Música, rótulo y montaje
    await ctx.progress(0.88, "Componiendo banda sonora")
    music = None
    try:
        music = await C.music_track(ctx, pid, sb, sum(s.duration for s in sb.shots), (0.88, 0.92))
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Música: {e}")
    if sb.shots:
        sb.shots[-1].on_screen_text = character.name
    await ctx.progress(0.92, "Montando la línea de tiempo")
    span = await C.assemble(pid, sb, music=music, title_style="slide_up", subtitles=False)

    result: dict[str, Any] = {"character_id": character.id, "location_id": location.id, "timeline": span}
    if params.get("auto_export", True):
        await ctx.progress(0.93, "Exportando máster 4K")
        p = store.get(pid)
        tw, th = C.CANVAS_4K.get(aspect, (3840, 2160))
        fmt = params.get("export_format", "mp4_h265")
        render = await render_project(store, p, RenderSettings(format=fmt, width=tw, height=th, quality="high", start=span["start"], end=span["end"],
                                                              title=f"{character.name} — durosTCM"),
                                      progress=ctx.sub(0.93, 1.0, "Render 4K: "), cancel_event=ctx.cancel_event, job_id=ctx.job.id)
        result["render"] = render
    return result


# ------------------------------------------------------------------ anuncio


async def ad(ctx: JobContext, pid: str, params: dict[str, Any]) -> dict:
    aspect = params.get("aspect", "16:9")
    duration = float(params.get("duration", 20))
    seed = params.get("seed") or random.randint(0, 2**31 - 1)
    imagination = float(params.get("imagination", 0.6))
    await C.set_canvas(pid, aspect, 25 if params.get("broadcast") else 30)
    lib = get_library()
    character = None
    if params.get("character_id"):
        try:
            character = lib.get("characters", params["character_id"])
        except KeyError:
            character = None
    await ctx.progress(0.01, "Escribiendo el anuncio")
    sb = None
    llm = await _llm()
    if llm is not None:
        try:
            brief = (f"Producto: {params.get('product')}. Descripción: {params.get('description', '')}. Público: {params.get('audience', '')}. "
                     f"Tono: {params.get('tone', 'premium')}. Marca: {params.get('brand', '')}. Llamada a la acción: {params.get('cta', '')}. "
                     f"Formato {aspect}. Incluye locución en off (speaker 'narrador') y rótulos clave.")
            sb = await IM.llm_storyboard(llm, brief, "ad", duration, [character] if character else [])
        except Exception as e:  # noqa: BLE001
            ctx.log(f"LLM: {e}")
    location = IM.design_location(params.get("location", ""), seed=seed, imagination=imagination)
    lib.save("locations", location)
    if sb is None:
        sb, _ = IM.storyboard_ad(params.get("product", "Producto"), params.get("description", ""), params.get("audience", ""), params.get("tone", "premium"),
                                 duration, aspect, params.get("cta", ""), params.get("brand", ""), seed, imagination, character, location=location)  # type: ignore[arg-type]
    for i, s in enumerate(sb.shots):
        s.seed = seed + i
        if s.location is None and i not in (2,):
            s.location = location.id
    await C.link_library(pid, [character] if character else [], [location])  # type: ignore[list-item]
    await C.save_storyboard(pid, sb)
    await C.produce_shots(ctx, pid, sb, aspect, (0.05, 0.78))
    voices: dict = {}
    if params.get("voiceover", True):
        await ctx.progress(0.78, "Grabando locución")
        voice = params.get("voice")
        if voice:
            for s in sb.shots:
                for d in s.dialogue:
                    d.voice = voice
        try:
            voices = await C.voice_lines(ctx, pid, sb, (0.78, 0.86))
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Locución: {e}")
    music = None
    if params.get("music", True):
        await ctx.progress(0.86, "Música")
        try:
            music = await C.music_track(ctx, pid, sb, duration, (0.86, 0.92))
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Música: {e}")
    store = get_store()
    logo = store.get(pid).media_by_id(params.get("logo_media_id"))
    await ctx.progress(0.93, "Montando")
    span = await C.assemble(pid, sb, voices=voices, music=music, logo=logo, title_style="zoom", subtitles=bool(params.get("subtitles", True)))
    result: dict[str, Any] = {"timeline": span, "location_id": location.id}
    if params.get("auto_export"):
        p = store.get(pid)
        result["render"] = await render_project(store, p, RenderSettings(format="mp4_h264", start=span["start"], end=span["end"], loudness=-14),
                                                progress=ctx.sub(0.94, 1.0, "Render: "), cancel_event=ctx.cancel_event, job_id=ctx.job.id)
    return result


# ------------------------------------------------------------------ cortometraje


async def short_film(ctx: JobContext, pid: str, params: dict[str, Any]) -> dict:
    idea = params.get("idea", "")
    genre = params.get("genre", "drama")
    duration = float(params.get("duration", 60))
    aspect = params.get("aspect", "2.39:1")
    seed = params.get("seed") or random.randint(0, 2**31 - 1)
    imagination = float(params.get("imagination", 0.7))
    await C.set_canvas(pid, aspect, 24)
    lib = get_library()
    chars: list[Character] = [c for c in C.chars_by_id(params.get("character_ids") or [])]
    await ctx.progress(0.01, "Escribiendo guion y storyboard")
    llm = await _llm()
    sb = None
    if not chars:
        if llm is not None:
            try:
                c = await IM.llm_character(llm, f"protagonista de un cortometraje de {genre}: {idea}")
                if c:
                    chars = [c]
            except Exception as e:  # noqa: BLE001
                ctx.log(f"LLM personaje: {e}")
        if not chars:
            chars = [IM.design_character(idea, seed=seed, imagination=imagination)]
        for c in chars:
            lib.save("characters", c)
    location = IM.design_location(params.get("location", ""), seed=seed + 7, imagination=imagination)
    lib.save("locations", location)
    if llm is not None:
        try:
            sb = await IM.llm_storyboard(llm, f"Cortometraje de {genre}: {idea}", "short_film", duration, chars,
                                         extra="Incluye diálogos breves y naturales. Usa la localización: " + location.description)
        except Exception as e:  # noqa: BLE001
            ctx.log(f"LLM storyboard: {e}")
    if sb is None:
        sb, _l, _c = IM.storyboard_short(idea, genre, duration, chars, seed, imagination, location=location)
    for i, s in enumerate(sb.shots):
        s.seed = seed + i
        s.location = s.location or location.id
        if not s.characters and chars:
            s.characters = [chars[0].id]
    await C.link_library(pid, chars, [location])
    await C.save_storyboard(pid, sb)

    # Retratos de referencia para mantener identidades
    for i, c in enumerate(chars):
        if not c.hero_image:
            v = IM.character_turnaround_prompts(c)[0]
            items = await generate_media(ctx, pid, "text2image", GenRequest(prompt=v["prompt"], negative=v["negative"], width=896, height=1152, seed=c.seed),
                                         name=f"{c.name} · referencia", tags=["personaje", c.id], progress_range=(0.03, 0.08))
            if items:
                lib.add_image("characters", c.id, get_store().resolve(pid, items[0].path), as_hero=True)
    await C.produce_shots(ctx, pid, sb, aspect, (0.08, 0.8))
    voices = {}
    try:
        voices = await C.voice_lines(ctx, pid, sb, (0.8, 0.88))
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Diálogos: {e}")
    music = None
    try:
        music = await C.music_track(ctx, pid, sb, duration, (0.88, 0.93))
    except Exception as e:  # noqa: BLE001
        ctx.log(f"Música: {e}")
    if sb.shots:
        sb.shots[0].on_screen_text = sb.title
    span = await C.assemble(pid, sb, voices=voices, music=music, title_style="fade", subtitles=True)
    return {"timeline": span, "characters": [c.id for c in chars], "location_id": location.id}


# ------------------------------------------------------------------ piezas sueltas


async def storyboard_only(ctx: JobContext, pid: str, params: dict[str, Any]) -> dict:
    fmt = params.get("format", "short_film")
    duration = float(params.get("duration", 30))
    brief = params.get("brief", "")
    chars = C.chars_by_id(params.get("character_ids") or [])
    llm = await _llm()
    sb = None
    if llm is not None:
        try:
            sb = await IM.llm_storyboard(llm, brief, fmt, duration, chars)
        except Exception as e:  # noqa: BLE001
            ctx.log(f"LLM: {e}")
    if sb is None:
        if fmt == "ad":
            sb, _ = IM.storyboard_ad(brief or "Producto", "", "", "premium", duration)
        elif fmt == "character" and chars:
            sb, _ = IM.storyboard_character(chars[0], None, duration)
        else:
            sb, _l, chars2 = IM.storyboard_short(brief, "drama", duration, chars or None)
            for c in chars2:
                get_library().save("characters", c)
            get_library().save("locations", _l)
    await C.save_storyboard(pid, sb)
    return {"storyboard": sb.model_dump()}


async def produce(ctx: JobContext, pid: str, params: dict[str, Any]) -> dict:
    p = get_store().get(pid)
    if not p.storyboard:
        raise ValueError("El proyecto no tiene storyboard")
    aspect = params.get("aspect") or _aspect_of(p.settings.width, p.settings.height)
    await C.produce_shots(ctx, pid, p.storyboard, aspect, (0.0, 1.0), make_video=params.get("video", True), only=params.get("shot_ids"))
    return {"ok": True}


async def assemble_only(ctx: JobContext, pid: str, params: dict[str, Any]) -> dict:
    p = get_store().get(pid)
    if not p.storyboard:
        raise ValueError("El proyecto no tiene storyboard")
    return await C.assemble(pid, p.storyboard, subtitles=params.get("subtitles", True))


def _aspect_of(w: int, h: int) -> str:
    r = w / h
    best = min(C.ASPECT_SIZES, key=lambda k: abs(_ratio(k) - r))
    return best


def _ratio(k: str) -> float:
    a, b = k.split(":")
    return float(a) / float(b)


PIPELINES = {
    "character_4k": {"fn": character_4k, "label": "Personaje hiperrealista 4K", "pool": "gpu"},
    "ad": {"fn": ad, "label": "Anuncio publicitario", "pool": "gpu"},
    "short_film": {"fn": short_film, "label": "Cortometraje", "pool": "gpu"},
    "storyboard": {"fn": storyboard_only, "label": "Storyboard", "pool": "io"},
    "produce": {"fn": produce, "label": "Generar planos", "pool": "gpu"},
    "assemble": {"fn": assemble_only, "label": "Montar en la línea de tiempo", "pool": "io"},
}


def start(name: str, pid: str, params: dict[str, Any]):
    spec = PIPELINES[name]

    async def job(ctx: JobContext):
        return await spec["fn"](ctx, pid, params)

    return get_jobs().submit(f"pipeline:{name}", spec["label"], job, project_id=pid, pool=spec["pool"])


def plan(name: str, params: dict[str, Any]) -> dict:
    """Estimación de tiempo antes de lanzar."""
    if name == "character_4k":
        d = float(params.get("duration", 24))
        return estimate(shots=6 + int(params.get("reference_views", 4)), seconds_of_video=d, upscale_4k=params.get("upscale", True))
    if name == "ad":
        d = float(params.get("duration", 20))
        return estimate(shots=5, seconds_of_video=d)
    if name == "short_film":
        d = float(params.get("duration", 60))
        return estimate(shots=max(8, int(d / 5)), seconds_of_video=d)
    return estimate(shots=1, seconds_of_video=4)

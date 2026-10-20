"""Piezas comunes de los pipelines: generar planos, voces, música y montar la línea de tiempo."""

from __future__ import annotations

import asyncio
from typing import Any

from ..ai.base import GenRequest
from ..ai.imagination import engine as IM
from ..ai.registry import get_registry
from ..ai.service import generate_media, project_lock
from ..core.jobs import JobContext, get_jobs
from ..core.library import Character, Location, get_library
from ..core.project import Clip, Keyframe, MediaItem, Project, Shot, Storyboard, TextStyle, Track, Transition
from ..core.storage import get_store

ASPECT_SIZES = {
    "16:9": (1344, 768), "9:16": (768, 1344), "1:1": (1024, 1024), "4:5": (896, 1120), "4:3": (1152, 864),
    "21:9": (1536, 640), "2.39:1": (1536, 640), "1.85:1": (1408, 768),
}
CANVAS = {
    "16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350), "4:3": (1440, 1080),
    "21:9": (2520, 1080), "2.39:1": (2580, 1080), "1.85:1": (1998, 1080),
}
CANVAS_4K = {"16:9": (3840, 2160), "9:16": (2160, 3840), "1:1": (2160, 2160), "4:5": (2160, 2700), "2.39:1": (4096, 1716), "21:9": (5040, 2160)}


async def is_preview_only(capability: str) -> bool:
    cands = await get_registry().candidates(capability)
    return not cands or cands[0].quality == "preview"


def gen_size(aspect: str, preview: bool) -> tuple[int, int]:
    w, h = ASPECT_SIZES.get(aspect, ASPECT_SIZES["16:9"])
    if preview:
        k = 1280 / max(w, h)
        w, h = int(w * k) // 2 * 2, int(h * k) // 2 * 2
    return w, h


def chars_by_id(ids: list[str]) -> list[Character]:
    lib = get_library()
    out = []
    for i in ids:
        try:
            out.append(lib.get("characters", i))  # type: ignore[arg-type]
        except KeyError:
            pass
    return out


def loc_by_id(lid: str | None) -> Location | None:
    if not lid:
        return None
    try:
        return get_library().get("locations", lid)  # type: ignore[return-value]
    except KeyError:
        return None


async def save_storyboard(pid: str, sb: Storyboard) -> None:
    store = get_store()
    async with project_lock(pid):
        p = store.get(pid)
        p.storyboard = sb
        store.save(p)
    await get_jobs().broadcast({"type": "storyboard", "project_id": pid, "storyboard": sb.model_dump()})


async def link_library(pid: str, characters: list[Character], locations: list[Location]) -> None:
    store = get_store()
    async with project_lock(pid):
        p = store.get(pid)
        for c in characters:
            if c.id not in p.characters:
                p.characters.append(c.id)
        for lo in locations:
            if lo.id not in p.locations:
                p.locations.append(lo.id)
        store.save(p)


def hero_path(c: Character) -> str | None:
    if not c.hero_image:
        return None
    return str(get_library().file("characters", c.id, c.hero_image))


async def shot_keyframe(ctx: JobContext, pid: str, shot: Shot, sb: Storyboard, aspect: str, rng: tuple[float, float], realism: float = 1.0) -> MediaItem | None:
    chars = chars_by_id(shot.characters)
    loc = loc_by_id(shot.location)
    prompt, negative = IM.compose_shot_prompt(shot, chars, loc, sb, "image", realism)
    preview = await is_preview_only("text2image")
    w, h = gen_size(aspect, preview)
    seed = shot.seed if shot.seed is not None else (chars[0].seed if chars and chars[0].seed is not None else None)
    refs = [p for p in (hero_path(c) for c in chars) if p]
    # Con un motor de referencia (FLUX Kontext) mantenemos la identidad del personaje
    use_ref = bool(refs) and not await is_preview_only("image2image")
    if use_ref:
        ref_prompt = f"Keep the exact same person. {shot.prompt or shot.description}. {IM.V.SHOT_SIZES.get(shot.camera.shot_size, '')}, " \
                     f"{IM.V.LIGHTING.get(shot.lighting, shot.lighting)}, setting: {loc.identity_prompt if loc else ''}, photorealistic"
        try:
            items = await generate_media(ctx, pid, "image2image", GenRequest(prompt=ref_prompt, negative=negative, width=w, height=h, seed=seed,
                                                                               image=refs[0], references=refs, strength=0.9),
                                         name=f"Plano {shot.index + 1} · fotograma", tags=["storyboard", shot.id], progress_range=rng)
            return items[0] if items else None
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Referencia de personaje no disponible ({e}); se usa texto→imagen")
    items = await generate_media(ctx, pid, "text2image", GenRequest(prompt=prompt, negative=negative, width=w, height=h, seed=seed),
                                 name=f"Plano {shot.index + 1} · fotograma", tags=["storyboard", shot.id], progress_range=rng)
    return items[0] if items else None


async def shot_video(ctx: JobContext, pid: str, shot: Shot, sb: Storyboard, aspect: str, keyframe: MediaItem | None, rng: tuple[float, float], fps: int = 24) -> MediaItem | None:
    chars = chars_by_id(shot.characters)
    loc = loc_by_id(shot.location)
    prompt, negative = IM.compose_shot_prompt(shot, chars, loc, sb, "video")
    preview = await is_preview_only("image2video" if keyframe else "text2video")
    w, h = gen_size(aspect, preview)
    store = get_store()
    req = GenRequest(prompt=prompt, negative=negative, width=w, height=h, duration=shot.duration, fps=fps,
                     seed=shot.seed, motion=shot.camera.movement)
    if keyframe is not None:
        req.image = str(store.resolve(pid, keyframe.path))
        items = await generate_media(ctx, pid, "image2video", req, name=f"Plano {shot.index + 1} · vídeo", tags=["storyboard", shot.id], progress_range=rng)
    else:
        items = await generate_media(ctx, pid, "text2video", req, name=f"Plano {shot.index + 1} · vídeo", tags=["storyboard", shot.id], progress_range=rng)
    return items[0] if items else None


async def voice_lines(ctx: JobContext, pid: str, sb: Storyboard, rng: tuple[float, float]) -> dict[str, list[MediaItem]]:
    """TTS de todos los diálogos y voz en off. Devuelve {shot_id: [medios]}."""
    lines = [(s, d) for s in sb.shots for d in s.dialogue if d.text.strip()]
    out: dict[str, list[MediaItem]] = {}
    if not lines:
        return out
    a, b = rng
    for i, (shot, d) in enumerate(lines):
        voice = d.voice
        if not voice:
            ch = next(iter(chars_by_id([d.speaker])), None)
            voice = ch.voice.voice_id if ch and ch.voice.voice_id else None
        r0 = a + (b - a) * i / len(lines)
        r1 = a + (b - a) * (i + 1) / len(lines)
        items = await generate_media(ctx, pid, "tts", GenRequest(text=d.text, voice=voice, language=sb.language or "es"),
                                     name=f"Voz · {d.text[:30]}", tags=["voz", shot.id], progress_range=(r0, r1))
        out.setdefault(shot.id, []).extend(items)
    return out


async def lipsync_available() -> bool:
    cands = await get_registry().candidates("lipsync")
    return bool(cands)


async def lipsync_shots(ctx: JobContext, pid: str, sb: Storyboard, voices: dict[str, list[MediaItem]], aspect: str, rng: tuple[float, float]) -> int:
    """Sustituye el vídeo de los planos con diálogo de un personaje por uno con sincronía labial."""
    if not await lipsync_available():
        return 0
    store = get_store()
    p = store.get(pid)
    todo = []
    for s in sb.shots:
        speaking = [d for d in s.dialogue if d.text.strip() and d.speaker not in ("narrador", "narrator", "")]
        if speaking and voices.get(s.id) and s.image_media_id:
            todo.append(s)
    a, b = rng
    done = 0
    for i, s in enumerate(todo):
        kf = p.media_by_id(s.image_media_id)
        voice = voices[s.id][0]
        if kf is None:
            continue
        chars = chars_by_id(s.characters)
        prompt = f"{chars[0].identity_prompt if chars else 'a person'} talking naturally to camera, {s.description}, natural lip movement, subtle head motion"
        w, h = gen_size(aspect, False)
        try:
            items = await generate_media(ctx, pid, "lipsync", GenRequest(prompt=prompt, image=str(store.resolve(pid, kf.path)), audio=str(store.resolve(pid, voice.path)),
                                                                         width=w, height=h, duration=max(1.0, voice.duration or s.duration), seed=s.seed),
                                         name=f"Plano {s.index + 1} · habla", tags=["lipsync", s.id],
                                         progress_range=(a + (b - a) * i / len(todo), a + (b - a) * (i + 1) / len(todo)))
            if items:
                s.video_media_id = items[0].id
                await update_shot(pid, s.id, video_media_id=items[0].id)
                done += 1
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Sincronía labial plano {s.index + 1}: {e}")
    return done


async def music_track(ctx: JobContext, pid: str, sb: Storyboard, duration: float, rng: tuple[float, float]) -> MediaItem | None:
    prompt = sb.music_prompt or f"{sb.style} cinematic score"
    items = await generate_media(ctx, pid, "music", GenRequest(prompt=prompt, duration=duration + 1.0), name="Banda sonora", tags=["música"], progress_range=rng)
    return items[0] if items else None


def _track(p: Project, kind: str, name_hint: str) -> Track:
    hint = name_hint.lower()
    for t in p.tracks:
        name = t.name.lower()
        if t.kind == kind and (name == hint or (name.split() and name.split()[-1] == hint)):
            return t
    t = Track(name=name_hint, kind=kind)  # type: ignore[arg-type]
    if kind == "audio":
        p.tracks.append(t)
    else:
        idx = max((i for i, x in enumerate(p.tracks) if x.kind in ("video", "text")), default=-1)
        p.tracks.insert(idx + 1, t)
    return t


async def assemble(pid: str, sb: Storyboard, *, voices: dict[str, list[MediaItem]] | None = None, music: MediaItem | None = None,
                   logo: MediaItem | None = None, title_style: str = "fade", subtitles: bool = True, start_at: float | None = None) -> dict[str, Any]:
    """Monta el storyboard en la línea de tiempo (vídeo, rótulos, subtítulos, voces y música con ducking)."""
    store = get_store()
    async with project_lock(pid):
        p = store.get(pid)
        p.ensure_default_tracks()
        v1 = next((t for t in p.tracks if t.kind == "video"), None) or _track(p, "video", "V1")
        titles = _track(p, "text", "Títulos")
        subs = _track(p, "text", "Subtítulos") if subtitles else None
        vo = _track(p, "audio", "Diálogo")
        mus = _track(p, "audio", "Música")
        t0 = start_at if start_at is not None else p.duration
        t = t0
        vo_spans: list[tuple[float, float]] = []
        for i, shot in enumerate(sb.shots):
            media = p.media_by_id(shot.video_media_id) or p.media_by_id(shot.image_media_id)
            dur = max(1.0, shot.duration)
            trans = None
            if i > 0 and shot.transition and shot.transition != "cut":
                d = min(0.6, dur / 3)
                trans = Transition(type=shot.transition if shot.transition in IM_TRANSITIONS else "fade", duration=d)
                t -= d
                dur += d  # el solape de la transición no acorta la pieza
            if media is not None:
                c = Clip(media_id=media.id, name=f"{i + 1}. {shot.scene}", start=round(t, 4), duration=dur, transition_in=trans)
                if media.kind == "video" and media.duration:
                    ratio = media.duration / dur
                    if 0.5 <= ratio < 1.0:
                        c.speed = round(ratio, 4)  # cámara lenta suave para llenar el plano
                elif media.kind == "image":
                    from ..core.project import Motion

                    mv = {"dolly_in": "push_in", "push_in": "push_in", "dolly_out": "pull_out", "pan": "pan_right", "tracking": "pan_right",
                          "tilt": "tilt_up", "crane": "tilt_up", "handheld": "handheld"}.get(shot.camera.movement, "drift")
                    c.motion = Motion(preset=mv, intensity=0.5)  # type: ignore[arg-type]
                if sb.look:
                    c.color.look = sb.look
                v1.clips.append(c)
            if shot.on_screen_text.strip():
                titles.clips.append(Clip(kind="text", start=round(t + min(0.4, dur * 0.1), 4), duration=max(1.0, dur - 0.6),
                                         text=TextStyle(content=shot.on_screen_text, size=0.075, animation=title_style if title_style else "fade",  # type: ignore[arg-type]
                                                        uppercase=sb.format == "ad"),
                                         name="Rótulo"))
            vt = t + 0.25
            for vm in (voices or {}).get(shot.id, []):
                vd = vm.duration or 2.0
                vo.clips.append(Clip(media_id=vm.id, start=round(vt, 4), duration=vd, name="Voz"))
                vo_spans.append((vt, vt + vd))
                if subs is not None:
                    line = next((d.text for d in shot.dialogue if d.text and d.text[:30] in (vm.name or "")), None) or (vm.generation.prompt if vm.generation else "")
                    if line:
                        subs.clips.append(Clip(kind="text", start=round(vt, 4), duration=vd, name="Subtítulo",
                                               text=TextStyle(content=line, size=0.042, weight="normal", background="#000000A0", shadow=False, animation="none"),
                                               transform=_sub_transform()))
                vt += vd + 0.15
            t += dur
        end = t
        if subs is not None and not subs.clips:
            p.tracks.remove(subs)
        if logo is not None and sb.shots:
            last = sb.shots[-1]
            lc = Clip(media_id=logo.id, start=round(end - max(1.5, last.duration * 0.7), 4), duration=max(1.5, last.duration * 0.7), fade_in=0.4, name="Logo")
            lc.transform.fit = "contain"
            lc.transform.scale = 0.28
            lc.transform.y = 0.42
            _track(p, "video", "Logo").clips.append(lc)
        if music is not None:
            mdur = end - t0
            mc = Clip(media_id=music.id, start=round(t0, 4), duration=max(1.0, min(mdur, music.duration or mdur)), volume=0.55,
                      audio_fade_in=1.0, audio_fade_out=2.0, name="Música")
            if vo_spans:
                kfs = [Keyframe(t=0, value=1.0)]
                for a, b in vo_spans:
                    a2, b2 = a - t0, b - t0
                    kfs += [Keyframe(t=max(0, a2 - 0.3), value=1.0), Keyframe(t=max(0, a2), value=0.35), Keyframe(t=b2, value=0.35), Keyframe(t=b2 + 0.4, value=1.0)]
                kfs.sort(key=lambda k: k.t)
                mc.keyframes["volume"] = _dedupe(kfs)
            mus.clips.append(mc)
        store.bump(p)
    await get_jobs().broadcast({"type": "project_changed", "project_id": pid})
    return {"start": t0, "end": end}


IM_TRANSITIONS = {"fade", "dissolve", "fadeblack", "fadewhite", "wipeleft", "wiperight", "slideleft", "slideright", "slideup", "slidedown",
                  "circleopen", "circleclose", "radial", "smoothleft", "smoothright", "zoomin", "hblur", "distance"}


def _sub_transform():
    from ..core.project import Transform

    return Transform(x=0.5, y=0.88)


def _dedupe(kfs: list[Keyframe]) -> list[Keyframe]:
    out: list[Keyframe] = []
    for k in kfs:
        if out and abs(out[-1].t - k.t) < 1e-3:
            out[-1] = k
        else:
            out.append(k)
    return out


async def set_canvas(pid: str, aspect: str, fps: float, uhd: bool = False) -> None:
    store = get_store()
    async with project_lock(pid):
        p = store.get(pid)
        if p.duration == 0:
            w, h = (CANVAS_4K if uhd else CANVAS).get(aspect, (1920, 1080))
            p.settings.width, p.settings.height, p.settings.fps = w, h, fps
            store.bump(p)


async def update_shot(pid: str, shot_id: str, **fields) -> Storyboard | None:
    store = get_store()
    async with project_lock(pid):
        p = store.get(pid)
        if not p.storyboard:
            return None
        for s in p.storyboard.shots:
            if s.id == shot_id:
                for k, v in fields.items():
                    setattr(s, k, v)
        store.save(p)
        sb = p.storyboard
    await get_jobs().broadcast({"type": "storyboard", "project_id": pid, "storyboard": sb.model_dump()})
    return sb


async def produce_shots(ctx: JobContext, pid: str, sb: Storyboard, aspect: str, rng: tuple[float, float], *, make_video: bool = True,
                        only: list[str] | None = None, realism: float = 1.0) -> None:
    """Genera fotograma clave y vídeo de cada plano, actualizando el storyboard en vivo."""
    shots = [s for s in sb.shots if not only or s.id in only]
    if not shots:
        return
    a, b = rng
    span = (b - a) / len(shots)
    for i, shot in enumerate(shots):
        ctx.check()
        base = a + span * i
        kf_end = base + span * (0.35 if make_video else 1.0)
        await ctx.progress(base, f"Plano {shot.index + 1}/{len(sb.shots)}: fotograma clave")
        try:
            kf = await shot_keyframe(ctx, pid, shot, sb, aspect, (base, kf_end), realism)
            if kf:
                shot.image_media_id = kf.id
                shot.status = "image"
                await update_shot(pid, shot.id, image_media_id=kf.id, status="image")
            if make_video:
                await ctx.progress(kf_end, f"Plano {shot.index + 1}/{len(sb.shots)}: animando")
                vid = await shot_video(ctx, pid, shot, sb, aspect, kf, (kf_end, base + span))
                if vid:
                    shot.video_media_id = vid.id
                    shot.status = "done"
                    await update_shot(pid, shot.id, video_media_id=vid.id, status="done")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            ctx.log(f"Plano {shot.index + 1}: error {e}")
            shot.status = "error"
            await update_shot(pid, shot.id, status="error")

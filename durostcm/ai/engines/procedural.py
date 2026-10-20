"""Motor procedural: siempre disponible, sin GPU ni modelos.

* Imágenes/vídeos de concepto (bocetos de storyboard) a partir del prompt.
* Escalado de alta calidad (Lanczos + nitidez) hasta 8K.
* Interpolación de fotogramas por compensación de movimiento (FFmpeg minterpolate).
* Música procedural por estado de ánimo.
* Voz: pista de silencio con la duración estimada (marca de tiempo para montar).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from PIL import Image, ImageFilter

from ...core.ffmpeg import probe, run_ffmpeg
from ..base import Engine, EngineStatus, GenContext, GenRequest, GenResult
from . import procedural_art, procedural_music


def _camera_from_prompt(prompt: str, motion: str | None) -> str:
    low = f"{motion or ''} {prompt}".lower()
    table = [
        (("dolly in", "push in", "acercamiento", "zoom in", "travelling in", "se acerca"), "push_in"),
        (("dolly out", "pull out", "alejamiento", "zoom out", "se aleja"), "pull_out"),
        (("pan left", "paneo izquierda", "barrido izquierda"), "pan_left"),
        (("pan right", "paneo derecha", "barrido derecha", "tracking", "travelling lateral"), "pan_right"),
        (("tilt up", "panorámica vertical", "sube", "crane up", "grúa"), "tilt_up"),
        (("tilt down", "baja la cámara", "crane down"), "tilt_down"),
        (("handheld", "cámara en mano", "camara en mano", "documental", "shaky"), "handheld"),
    ]
    for keys, preset in table:
        if any(k in low for k in keys):
            return preset
    return "push_in"


def _zoompan_expr(preset: str, frames: int, fps: int = 24) -> tuple[str, str, str]:
    p = f"(on/{frames})"
    e = f"({p}*{p}*(3-2*{p}))"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if preset == "pull_out":
        return f"1.22-0.22*{e}", cx, cy
    if preset == "pan_left":
        return "1.18", f"(iw-iw/zoom)*(1-{e})", cy
    if preset == "pan_right":
        return "1.18", f"(iw-iw/zoom)*{e}", cy
    if preset == "tilt_up":
        return "1.18", cx, f"(ih-ih/zoom)*(1-{e})"
    if preset == "tilt_down":
        return "1.18", cx, f"(ih-ih/zoom)*{e}"
    if preset == "handheld":
        return "1.08", f"(iw-iw/zoom)/2*(1+0.45*sin(on/{fps}*2.1))", f"(ih-ih/zoom)/2*(1+0.45*sin(on/{fps}*1.7+2))"
    return f"1+0.22*{e}", cx, cy


async def animate_still(image: Path, out: Path, width: int, height: int, duration: float, fps: int, preset: str, ctx: GenContext) -> Path:
    frames = max(2, int(duration * fps))
    z, x, y = _zoompan_expr(preset, frames, fps)
    W, H = width - width % 2, height - height % 2
    vf = (
        f"scale={int(W * 1.6) // 2 * 2}:{int(H * 1.6) // 2 * 2}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={int(W * 1.6) // 2 * 2}:{int(H * 1.6) // 2 * 2},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={fps},"
        f"noise=c0s=4:c0f=t,format=yuv420p"
    )
    args = ["-loop", "1", "-i", str(image), "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-movflags", "+faststart", str(out)]
    await run_ffmpeg(args, duration=duration, progress=ctx.progress, cancel_event=ctx.cancel_event, label="animar")
    return out


class ProceduralEngine(Engine):
    id = "procedural"
    name = "Procedural durosTCM (sin GPU)"
    description = "Bocetos de concepto, escalado Lanczos, interpolación por movimiento y música generativa. Siempre disponible."
    capabilities = {"text2image", "image2image", "text2video", "image2video", "upscale_image", "upscale_video", "interpolate", "music", "tts"}
    quality = "preview"

    async def status(self) -> EngineStatus:
        return EngineStatus(available=True, detail="Integrado", models=["concept-art", "lanczos", "minterpolate", "synth"], quality="preview")

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        seed = req.resolved_seed()
        files: list[str] = []
        if capability == "text2image":
            for i in range(max(1, req.count)):
                img = await asyncio.to_thread(procedural_art.generate, req.prompt, req.width, req.height, seed + i)
                p = ctx.path("concepto", "png")
                img.save(p)
                files.append(str(p))
                await ctx.progress((i + 1) / max(1, req.count), "Componiendo escena")
        elif capability == "image2image":
            src = Image.open(req.image or "")
            img = await asyncio.to_thread(procedural_art.stylize, src, req.prompt, req.strength, seed)
            p = ctx.path("variacion", "png")
            img.save(p)
            files.append(str(p))
        elif capability in ("text2video", "image2video"):
            if capability == "image2video" and req.image:
                still = Path(req.image)
            else:
                img = await asyncio.to_thread(procedural_art.generate, req.prompt, req.width, req.height, seed)
                still = ctx.path("fotograma", "png")
                img.save(still)
            out = ctx.path("plano", "mp4")
            preset = _camera_from_prompt(req.prompt, req.motion)
            await animate_still(still, out, req.width, req.height, req.duration, req.fps, preset, ctx)
            files.append(str(out))
        elif capability == "upscale_image":
            src = Image.open(req.image or "").convert("RGB")
            tw, th = _target(src.width, src.height, req)
            img = src.resize((tw, th), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
            p = ctx.path("escalado", "png")
            img.save(p)
            files.append(str(p))
        elif capability == "upscale_video":
            info = probe(req.video or "")
            tw, th = _target(info["width"] or 1920, info["height"] or 1080, req)
            out = ctx.path("escalado", "mp4")
            vf = f"hqdn3d=1.5:1.5:3:3,scale={tw}:{th}:flags=lanczos+accurate_rnd+full_chroma_int,unsharp=5:5:0.7:5:5:0,format=yuv420p"
            args = ["-i", str(req.video), "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-c:a", "copy", "-movflags", "+faststart", str(out)]
            await run_ffmpeg(args, duration=info.get("duration"), progress=ctx.progress, cancel_event=ctx.cancel_event, label="escalar")
            files.append(str(out))
        elif capability == "interpolate":
            info = probe(req.video or "")
            target = req.target_fps or 60
            out = ctx.path(f"interpolado_{target}fps", "mp4")
            vf = f"minterpolate=fps={target}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,format=yuv420p"
            slow = req.extra.get("slowmo")  # factor de cámara lenta
            if slow:
                vf = f"setpts={float(slow)}*PTS," + vf
            args = ["-i", str(req.video), "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "17"]
            args += ["-an"] if slow else ["-c:a", "copy"]
            args += [str(out)]
            dur = (info.get("duration") or 1) * (float(slow) if slow else 1)
            await run_ffmpeg(args, duration=dur, progress=ctx.progress, cancel_event=ctx.cancel_event, label="interpolar")
            files.append(str(out))
        elif capability == "music":
            st, mood = await asyncio.to_thread(procedural_music.compose, req.prompt, max(2.0, req.duration), seed)
            p = ctx.path(f"musica_{mood}", "wav")
            procedural_music.write_wav(p, st)
            files.append(str(p))
            return GenResult(files=files, engine=self.id, model=f"synth:{mood}", seed=seed, meta={"mood": mood})
        elif capability == "tts":
            words = max(1, len(req.text.split()))
            dur = max(1.0, words / (2.6 * req.speech_speed)) + 0.4
            p = ctx.path("voz_guia", "wav")
            procedural_music.silence(p, dur)
            ctx.log("Sin motor de voz instalado: se crea una pista guía en silencio con la duración estimada.")
            files.append(str(p))
            return GenResult(files=files, engine=self.id, model="guia-silencio", seed=seed, meta={"placeholder": True})
        else:
            raise ValueError(f"Capacidad no soportada: {capability}")
        await ctx.progress(1.0, "Listo")
        return GenResult(files=files, engine=self.id, model="procedural", seed=seed)


def _target(w: int, h: int, req: GenRequest) -> tuple[int, int]:
    if req.target_width and req.target_height:
        tw, th = req.target_width, req.target_height
    elif req.target_width:
        tw, th = req.target_width, int(h * req.target_width / w)
    elif req.target_height:
        tw, th = int(w * req.target_height / h), req.target_height
    else:
        tw, th = w * req.scale, h * req.scale
    return tw - tw % 2, th - th % 2

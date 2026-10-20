"""Herramientas de post-producción IA: Real-ESRGAN, RIFE, rembg y Automatic1111/Forge."""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import shutil
from pathlib import Path

import httpx

from ...config import get_config
from ...core.ffmpeg import probe, run_ffmpeg
from ..base import Engine, EngineStatus, EngineUnavailable, GenContext, GenRequest, GenResult


async def _run_bin(args: list[str], ctx: GenContext) -> None:
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    async def watch():
        if ctx.cancel_event is None:
            return
        await ctx.cancel_event.wait()
        if proc.returncode is None:
            proc.kill()

    w = asyncio.create_task(watch())
    try:
        _o, err = await proc.communicate()
    finally:
        w.cancel()
    ctx.check()
    if proc.returncode != 0:
        raise RuntimeError(err.decode("utf-8", "ignore")[-800:])


async def _extract_frames(video: Path, folder: Path, ctx: GenContext) -> float:
    folder.mkdir(parents=True, exist_ok=True)
    info = probe(video)
    await run_ffmpeg(["-i", str(video), "-vsync", "0", str(folder / "f_%06d.png")], duration=info.get("duration"), progress=ctx.progress, label="extraer", cancel_event=ctx.cancel_event)
    return info.get("fps") or 24.0


async def _assemble(folder: Path, fps: float, audio_src: Path | None, out: Path, ctx: GenContext, pattern: str = "f_%06d.png") -> None:
    args = ["-framerate", f"{fps:.4f}", "-i", str(folder / pattern)]
    if audio_src is not None and probe(audio_src).get("has_audio"):
        args += ["-i", str(audio_src), "-map", "0:v", "-map", "1:a?", "-c:a", "aac", "-b:a", "256k", "-shortest"]
    args += ["-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    await run_ffmpeg(args, label="ensamblar", cancel_event=ctx.cancel_event)


class RealESRGANEngine(Engine):
    id = "realesrgan"
    name = "Real-ESRGAN (ncnn-vulkan)"
    description = "Superresolución neuronal x2/x4 para imagen y vídeo en cualquier GPU (NVIDIA, AMD, Intel, Apple)."
    capabilities = {"upscale_image", "upscale_video"}
    quality = "pro"

    def _bin(self) -> str | None:
        return get_config().settings.endpoints.realesrgan_bin or shutil.which("realesrgan-ncnn-vulkan")

    async def status(self) -> EngineStatus:
        b = self._bin()
        return EngineStatus(available=bool(b), detail=b or "Descarga realesrgan-ncnn-vulkan y configura su ruta", models=["realesrgan-x4plus", "realesr-animevideov3"] if b else [], quality="pro")

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        b = self._bin()
        if not b:
            raise EngineUnavailable("Real-ESRGAN no configurado")
        model = req.model or "realesrgan-x4plus"
        scale = 4 if req.scale >= 3 else 2
        if model == "realesrgan-x4plus":
            scale = 4
        if capability == "upscale_image":
            out = ctx.path("esrgan", "png")
            await _run_bin([b, "-i", str(req.image), "-o", str(out), "-n", model, "-s", str(scale)], ctx)
            out = await _fit_target(out, req, ctx)
            return GenResult(files=[str(out)], engine=self.id, model=model)
        video = Path(req.video or "")
        work = ctx.out_dir / f"_esr_{video.stem}"
        src, dst = work / "in", work / "out"
        fps = await _extract_frames(video, src, ctx)
        dst.mkdir(parents=True, exist_ok=True)
        await ctx.progress(0.3, "Superresolución de fotogramas")
        await _run_bin([b, "-i", str(src), "-o", str(dst), "-n", model, "-s", str(scale), "-f", "png"], ctx)
        out = ctx.path("esrgan_video", "mp4")
        await _assemble(dst, fps, video, out, ctx)
        if req.target_width or req.target_height:
            fitted = ctx.path("esrgan_4k", "mp4")
            tw = req.target_width or -2
            th = req.target_height or -2
            await run_ffmpeg(["-i", str(out), "-vf", f"scale={tw}:{th}:flags=lanczos", "-c:v", "libx264", "-crf", "14", "-preset", "slow", "-c:a", "copy", str(fitted)], label="ajustar")
            out.unlink(missing_ok=True)
            out = fitted
        shutil.rmtree(work, ignore_errors=True)
        return GenResult(files=[str(out)], engine=self.id, model=model)


async def _fit_target(img: Path, req: GenRequest, ctx: GenContext) -> Path:
    if not (req.target_width or req.target_height):
        return img
    from PIL import Image

    im = Image.open(img)
    tw = req.target_width or int(im.width * req.target_height / im.height)  # type: ignore[operator]
    th = req.target_height or int(im.height * tw / im.width)
    im.resize((tw, th), Image.LANCZOS).save(img)
    return img


class RIFEEngine(Engine):
    id = "rife"
    name = "RIFE (ncnn-vulkan)"
    description = "Interpolación neuronal de fotogramas: 24→48/60 fps o cámara lenta suave."
    capabilities = {"interpolate"}
    quality = "pro"

    def _bin(self) -> str | None:
        return get_config().settings.endpoints.rife_bin or shutil.which("rife-ncnn-vulkan")

    async def status(self) -> EngineStatus:
        b = self._bin()
        return EngineStatus(available=bool(b), detail=b or "Descarga rife-ncnn-vulkan y configura su ruta", quality="pro")

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        b = self._bin()
        if not b:
            raise EngineUnavailable("RIFE no configurado")
        video = Path(req.video or "")
        work = ctx.out_dir / f"_rife_{video.stem}"
        src, dst = work / "in", work / "out"
        fps = await _extract_frames(video, src, ctx)
        n_in = len(list(src.glob("*.png")))
        target = req.target_fps or int(round(fps * 2))
        factor = max(2, int(round(target / fps)))
        slow = float(req.extra.get("slowmo") or 0)
        n_out = n_in * (factor if not slow else max(2, int(round(slow))))
        dst.mkdir(parents=True, exist_ok=True)
        await ctx.progress(0.3, "Interpolando con RIFE")
        await _run_bin([b, "-i", str(src), "-o", str(dst), "-n", str(n_out), "-f", "%08d.png"], ctx)
        out = ctx.path(f"rife_{target}fps", "mp4")
        out_fps = fps * factor if not slow else fps
        await _assemble(dst, out_fps, None if slow else video, out, ctx, pattern="%08d.png")
        shutil.rmtree(work, ignore_errors=True)
        return GenResult(files=[str(out)], engine=self.id, model="rife")


class RembgEngine(Engine):
    id = "rembg"
    name = "rembg (U²-Net / BiRefNet)"
    description = "Recorta personajes y productos (PNG con transparencia)."
    capabilities = {"remove_bg"}
    quality = "pro"

    async def status(self) -> EngineStatus:
        ok = importlib.util.find_spec("rembg") is not None
        return EngineStatus(available=ok, detail="Instalado" if ok else "pip install durostcm[matting]", quality="pro")

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        def work() -> Path:
            from PIL import Image
            from rembg import new_session, remove

            model = req.model or ("birefnet-portrait" if "portrait" in (req.prompt or "") else "u2net")
            session = new_session(model)
            out = remove(Image.open(req.image or ""), session=session)
            p = ctx.path("recorte", "png")
            out.save(p)
            return p

        p = await asyncio.to_thread(work)
        return GenResult(files=[str(p)], engine=self.id, model=req.model or "u2net")


class A1111Engine(Engine):
    id = "a1111"
    name = "Automatic1111 / Forge"
    description = "Usa tu instalación de Stable Diffusion WebUI (arráncala con --api)."
    capabilities = {"text2image", "image2image"}
    quality = "standard"

    def _url(self) -> str:
        return get_config().settings.endpoints.a1111_url.rstrip("/")

    async def status(self) -> EngineStatus:
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False) as c:
                r = await c.get(self._url() + "/sdapi/v1/sd-models")
                r.raise_for_status()
                models = [m.get("model_name", "") for m in r.json()]
            return EngineStatus(available=True, detail=f"{len(models)} modelos", models=models)
        except Exception:
            return EngineStatus(available=False, detail=f"No responde en {self._url()} (usa --api)")

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        seed = req.resolved_seed()
        payload = {
            "prompt": req.prompt,
            "negative_prompt": req.negative,
            "width": req.width // 8 * 8,
            "height": req.height // 8 * 8,
            "steps": req.steps or 30,
            "cfg_scale": req.guidance or 5.5,
            "seed": seed,
            "batch_size": max(1, req.count),
            "sampler_name": "DPM++ 2M Karras",
        }
        if req.model:
            payload["override_settings"] = {"sd_model_checkpoint": req.model}
        endpoint = "/sdapi/v1/txt2img"
        if capability == "image2image":
            endpoint = "/sdapi/v1/img2img"
            payload["init_images"] = [base64.b64encode(Path(req.image or req.references[0]).read_bytes()).decode()]
            payload["denoising_strength"] = req.strength
        await ctx.progress(0.1, "Generando en A1111")
        async with httpx.AsyncClient(timeout=1800, trust_env=False) as c:
            r = await c.post(self._url() + endpoint, json=payload)
            r.raise_for_status()
            imgs = r.json().get("images", [])
        files = []
        for b64 in imgs:
            p = ctx.path("a1111", "png")
            p.write_bytes(base64.b64decode(b64.split(",", 1)[-1]))
            files.append(str(p))
        return GenResult(files=files, engine=self.id, model=req.model or "", seed=seed)

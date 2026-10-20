"""Motor diffusers (Hugging Face): ejecuta modelos directamente en Python sin ComfyUI.

Requiere ``pip install durostcm[gpu]`` y una GPU NVIDIA (CUDA) o Apple Silicon (MPS).
Carga perezosa: sólo se importa torch cuando se usa. Mantiene un único pipeline en
memoria y lo descarga al cambiar de modelo.
"""

from __future__ import annotations

import asyncio
import gc
import importlib.util
import inspect
import threading
import wave
from pathlib import Path
from typing import Any

from ...config import get_config
from ..base import Engine, EngineStatus, EngineUnavailable, GenContext, GenRequest, GenResult


def _device() -> str | None:
    if importlib.util.find_spec("torch") is None:
        return None
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class DiffusersEngine(Engine):
    id = "diffusers"
    name = "Diffusers (Python)"
    description = "FLUX, Qwen-Image, SDXL, Wan 2.2, LTX-Video, HunyuanVideo, CogVideoX y Stable Audio directamente desde Hugging Face."
    capabilities = {"text2image", "image2image", "text2video", "image2video", "music"}
    quality = "pro"

    def __init__(self) -> None:
        self._pipe = None
        self._pipe_key: tuple[str, str] | None = None
        self._lock = threading.Lock()

    async def status(self) -> EngineStatus:
        if importlib.util.find_spec("diffusers") is None:
            return EngineStatus(available=False, detail="Instala con: pip install durostcm[gpu]", quality="pro")
        dev = await asyncio.to_thread(_device)
        if dev in (None, "cpu"):
            return EngineStatus(available=False, detail="Sin GPU compatible (CUDA/MPS): diffusers sería demasiado lento", quality="pro")
        p = get_config().settings.diffusers
        return EngineStatus(available=True, detail=f"Dispositivo: {dev}", models=[p.image_model, p.video_model, p.i2v_model], quality="pro")

    def _load(self, model_id: str, kind: str):
        import torch
        from diffusers import DiffusionPipeline

        key = (model_id, kind)
        if self._pipe_key == key and self._pipe is not None:
            return self._pipe
        self._unload()
        prefs = get_config().settings.diffusers
        dtype = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}.get(prefs.dtype, torch.bfloat16)
        dev = _device()
        if dev == "mps" and dtype == torch.bfloat16:
            dtype = torch.float16
        kwargs: dict[str, Any] = {"torch_dtype": dtype}
        token = get_config().settings.api_keys.huggingface or None
        if token:
            kwargs["token"] = token
        cache = str(get_config().models_dir / "hf")
        kwargs["cache_dir"] = cache
        if "wan" in model_id.lower():
            try:
                from diffusers import AutoencoderKLWan

                kwargs["vae"] = AutoencoderKLWan.from_pretrained(model_id, subfolder="vae", torch_dtype=torch.float32, cache_dir=cache, token=token)
            except Exception:
                pass
        if kind == "image2image":
            try:
                from diffusers import AutoPipelineForImage2Image

                pipe = AutoPipelineForImage2Image.from_pretrained(model_id, **kwargs)
            except Exception:
                pipe = DiffusionPipeline.from_pretrained(model_id, **kwargs)
        else:
            pipe = DiffusionPipeline.from_pretrained(model_id, **kwargs)
        if dev == "cuda" and prefs.cpu_offload:
            pipe.enable_model_cpu_offload()
        else:
            pipe.to(dev)
        vae = getattr(pipe, "vae", None)
        for fn in ("enable_tiling", "enable_slicing"):
            if vae is not None and hasattr(vae, fn):
                try:
                    getattr(vae, fn)()
                except Exception:
                    pass
        self._pipe, self._pipe_key = pipe, key
        return pipe

    def _unload(self) -> None:
        if self._pipe is not None:
            self._pipe = None
            self._pipe_key = None
            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        st = await self.status()
        if not st.available:
            raise EngineUnavailable(st.detail)
        loop = asyncio.get_running_loop()

        def progress(v: float, stage: str) -> None:
            asyncio.run_coroutine_threadsafe(ctx.progress(v, stage), loop)

        return await asyncio.to_thread(self._run_sync, capability, req, ctx, progress)

    def _run_sync(self, capability: str, req: GenRequest, ctx: GenContext, progress) -> GenResult:
        import torch

        prefs = get_config().settings.diffusers
        model = req.model or {
            "text2image": prefs.image_model,
            "image2image": prefs.image_model,
            "text2video": prefs.video_model,
            "image2video": prefs.i2v_model,
            "music": "stabilityai/stable-audio-open-1.0",
        }[capability]
        with self._lock:
            progress(0.02, f"Cargando {model}")
            pipe = self._load(model, capability)
            seed = req.resolved_seed()
            gen = torch.Generator(device="cpu").manual_seed(seed)
            steps = req.steps or (4 if "schnell" in model.lower() else (30 if capability in ("text2video", "image2video") else 28))
            sig = inspect.signature(pipe.__call__).parameters

            def on_step(_pipe, step, _t, kw):
                progress(0.05 + 0.85 * (step + 1) / steps, f"Paso {step + 1}/{steps}")
                if ctx.cancel_event is not None and ctx.cancel_event.is_set():
                    _pipe._interrupt = True
                return kw

            args: dict[str, Any] = {"prompt": req.prompt, "generator": gen, "num_inference_steps": steps}
            if "negative_prompt" in sig and req.negative:
                args["negative_prompt"] = req.negative
            if "callback_on_step_end" in sig:
                args["callback_on_step_end"] = on_step
            if req.guidance is not None and "guidance_scale" in sig:
                args["guidance_scale"] = req.guidance
            files: list[str] = []
            if capability in ("text2image", "image2image"):
                if "width" in sig:
                    args["width"], args["height"] = req.width // 16 * 16, req.height // 16 * 16
                if capability == "image2image":
                    from PIL import Image

                    args["image"] = Image.open(req.image or req.references[0]).convert("RGB")
                    if "strength" in sig:
                        args["strength"] = req.strength
                for i in range(max(1, req.count)):
                    args["generator"] = torch.Generator(device="cpu").manual_seed(seed + i)
                    img = pipe(**args).images[0]
                    p = ctx.path("diffusers", "png")
                    img.save(p)
                    files.append(str(p))
            elif capability in ("text2video", "image2video"):
                from diffusers.utils import export_to_video

                fps = req.fps or 24
                n = max(9, int(req.duration * fps))
                n = 4 * ((n - 1) // 4) + 1
                if "num_frames" in sig:
                    args["num_frames"] = n
                if "height" in sig:
                    args["width"], args["height"] = req.width // 32 * 32, req.height // 32 * 32
                if capability == "image2video":
                    if "image" not in sig:
                        raise EngineUnavailable(f"{model} no admite imagen de entrada; elige un modelo imagen→vídeo")
                    from PIL import Image

                    args["image"] = Image.open(req.image or req.references[0]).convert("RGB")
                out = pipe(**args)
                frames = out.frames[0]
                p = ctx.path("diffusers_video", "mp4")
                export_to_video(frames, str(p), fps=fps)
                files.append(str(p))
            elif capability == "music":
                import numpy as np

                args.pop("callback_on_step_end", None)
                args["num_inference_steps"] = req.steps or 100
                if "audio_end_in_s" in sig:
                    args["audio_end_in_s"] = min(47.0, req.duration)
                audio = pipe(**args).audios[0]
                arr = audio.T.float().cpu().numpy() if hasattr(audio, "cpu") else np.asarray(audio).T
                sr = getattr(getattr(pipe, "vae", None), "sampling_rate", 44100)
                p = ctx.path("musica_ia", "wav")
                _write_wav(p, arr, int(sr))
                files.append(str(p))
            progress(1.0, "Listo")
            return GenResult(files=files, engine=self.id, model=model, seed=seed)


def _write_wav(path: Path, arr, sr: int) -> None:
    import numpy as np

    a = np.asarray(arr, dtype=np.float32)
    if a.ndim == 1:
        a = a[:, None]
    data = (np.clip(a, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())

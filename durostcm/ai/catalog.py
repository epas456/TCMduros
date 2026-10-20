"""Catálogo de modelos abiertos recomendados y gestor de descargas (Hugging Face).

Los nombres de archivo siguen los paquetes "repackaged" de Comfy-Org, que son los que
esperan los flujos integrados. Verifica siempre la licencia en la ficha del modelo antes
de un uso comercial: aquí se indica un resumen orientativo.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx

from ..config import get_config
from ..core.jobs import JobContext

# folder = subcarpeta de ComfyUI/models
CATALOG: list[dict] = [
    # ---------------- vídeo
    {"id": "wan22_5b", "name": "Wan 2.2 TI2V 5B", "kind": "video", "engine": "comfyui", "vram": 10, "license": "Apache 2.0", "commercial": True,
     "notes": "Texto/imagen→vídeo 720p a 24 fps. El mejor equilibrio para GPUs de 12-16 GB.",
     "files": [
         {"repo": "Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "path": "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors", "folder": "diffusion_models", "gb": 10.0},
         {"repo": "Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "path": "split_files/vae/wan2.2_vae.safetensors", "folder": "vae", "gb": 1.4},
         {"repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged", "path": "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "folder": "text_encoders", "gb": 6.7},
     ]},
    {"id": "wan22_14b_i2v", "name": "Wan 2.2 A14B imagen→vídeo (fp8)", "kind": "video", "engine": "comfyui", "vram": 24, "license": "Apache 2.0", "commercial": True,
     "notes": "Calidad cine. Dos expertos (ruido alto/bajo). 16 fps nativos (interpola a 24/48 con RIFE).",
     "files": [
         {"repo": "Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "path": "split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", "folder": "diffusion_models", "gb": 14.3},
         {"repo": "Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "path": "split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", "folder": "diffusion_models", "gb": 14.3},
         {"repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged", "path": "split_files/vae/wan_2.1_vae.safetensors", "folder": "vae", "gb": 0.25},
         {"repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged", "path": "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "folder": "text_encoders", "gb": 6.7},
     ]},
    {"id": "wan22_14b_t2v", "name": "Wan 2.2 A14B texto→vídeo (fp8)", "kind": "video", "engine": "comfyui", "vram": 24, "license": "Apache 2.0", "commercial": True,
     "notes": "Texto→vídeo de máxima calidad abierta.",
     "files": [
         {"repo": "Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "path": "split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors", "folder": "diffusion_models", "gb": 14.3},
         {"repo": "Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "path": "split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors", "folder": "diffusion_models", "gb": 14.3},
         {"repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged", "path": "split_files/vae/wan_2.1_vae.safetensors", "folder": "vae", "gb": 0.25},
         {"repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged", "path": "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "folder": "text_encoders", "gb": 6.7},
     ]},
    {"id": "ltxv_2b", "name": "LTX-Video 2B v0.9.5", "kind": "video", "engine": "comfyui", "vram": 8, "license": "LTX Open Weights (revisar)", "commercial": None,
     "notes": "Muy rápido, ideal para GPUs de 8 GB y previsualizaciones. Para LTX-2.x usa su flujo oficial en ComfyUI (se detecta como flujo de usuario).",
     "files": [
         {"repo": "Lightricks/LTX-Video", "path": "ltx-video-2b-v0.9.5.safetensors", "folder": "checkpoints", "gb": 6.3},
         {"repo": "comfyanonymous/flux_text_encoders", "path": "t5xxl_fp16.safetensors", "folder": "text_encoders", "gb": 9.8},
     ]},
    # ---------------- imagen
    {"id": "flux_schnell", "name": "FLUX.1 [schnell] fp8", "kind": "image", "engine": "comfyui", "vram": 12, "license": "Apache 2.0", "commercial": True,
     "notes": "4 pasos: bocetos de calidad en segundos.",
     "files": [{"repo": "Comfy-Org/flux1-schnell", "path": "flux1-schnell-fp8.safetensors", "folder": "checkpoints", "gb": 17.2}]},
    {"id": "flux_dev", "name": "FLUX.1 [dev] fp8", "kind": "image", "engine": "comfyui", "vram": 12, "license": "FLUX.1-dev Non-Commercial", "commercial": False,
     "notes": "Fotorrealismo excelente. Licencia no comercial del modelo: consulta a BFL para uso comercial.",
     "files": [{"repo": "Comfy-Org/flux1-dev", "path": "flux1-dev-fp8.safetensors", "folder": "checkpoints", "gb": 17.2}]},
    {"id": "flux_kontext", "name": "FLUX.1 Kontext [dev] fp8", "kind": "image", "engine": "comfyui", "vram": 16, "license": "FLUX.1-dev Non-Commercial", "commercial": False,
     "notes": "Edita imágenes manteniendo la identidad: mismo personaje en escenas nuevas.",
     "files": [
         {"repo": "Comfy-Org/flux1-kontext-dev_ComfyUI", "path": "split_files/diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors", "folder": "diffusion_models", "gb": 11.9},
         {"repo": "comfyanonymous/flux_text_encoders", "path": "clip_l.safetensors", "folder": "text_encoders", "gb": 0.25},
         {"repo": "comfyanonymous/flux_text_encoders", "path": "t5xxl_fp8_e4m3fn_scaled.safetensors", "folder": "text_encoders", "gb": 5.2},
         {"repo": "black-forest-labs/FLUX.1-schnell", "path": "ae.safetensors", "folder": "vae", "gb": 0.33},
     ]},
    {"id": "qwen_image", "name": "Qwen-Image fp8", "kind": "image", "engine": "comfyui", "vram": 20, "license": "Apache 2.0", "commercial": True,
     "notes": "Fotorrealismo y texto dentro de la imagen (rótulos, packaging). Licencia comercial.",
     "files": [
         {"repo": "Comfy-Org/Qwen-Image_ComfyUI", "path": "split_files/diffusion_models/qwen_image_fp8_e4m3fn.safetensors", "folder": "diffusion_models", "gb": 20.4},
         {"repo": "Comfy-Org/Qwen-Image_ComfyUI", "path": "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors", "folder": "text_encoders", "gb": 9.4},
         {"repo": "Comfy-Org/Qwen-Image_ComfyUI", "path": "split_files/vae/qwen_image_vae.safetensors", "folder": "vae", "gb": 0.25},
     ]},
    {"id": "sdxl_base", "name": "SDXL base 1.0", "kind": "image", "engine": "comfyui", "vram": 8, "license": "CreativeML Open RAIL++-M", "commercial": True,
     "notes": "Base clásica para GPUs de 8 GB. Usa finetunes fotorrealistas (RealVisXL, Juggernaut) desde Civitai/HF.",
     "files": [{"repo": "stabilityai/stable-diffusion-xl-base-1.0", "path": "sd_xl_base_1.0.safetensors", "folder": "checkpoints", "gb": 6.9}]},
    # ---------------- post
    {"id": "esrgan_x4", "name": "Real-ESRGAN x4plus", "kind": "upscale", "engine": "comfyui", "vram": 2, "license": "BSD-3-Clause", "commercial": True,
     "notes": "Superresolución x4 para llevar fotogramas a 4K/8K.",
     "files": [{"repo": "lllyasviel/Annotators", "path": "RealESRGAN_x4plus.pth", "folder": "upscale_models", "gb": 0.07}]},
    # ---------------- diffusers (descarga automática al usarlos)
    {"id": "hf_wan22_5b", "name": "Wan 2.2 TI2V 5B (diffusers)", "kind": "video", "engine": "diffusers", "repo": "Wan-AI/Wan2.2-TI2V-5B-Diffusers", "vram": 16, "license": "Apache 2.0", "commercial": True, "files": []},
    {"id": "hf_ltx", "name": "LTX-Video (diffusers)", "kind": "video", "engine": "diffusers", "repo": "Lightricks/LTX-Video", "vram": 12, "license": "LTX Open Weights", "commercial": None, "files": []},
    {"id": "hf_flux_schnell", "name": "FLUX.1 schnell (diffusers)", "kind": "image", "engine": "diffusers", "repo": "black-forest-labs/FLUX.1-schnell", "vram": 16, "license": "Apache 2.0", "commercial": True, "files": []},
    {"id": "hf_qwen_image", "name": "Qwen-Image (diffusers)", "kind": "image", "engine": "diffusers", "repo": "Qwen/Qwen-Image", "vram": 24, "license": "Apache 2.0", "commercial": True, "files": []},
    {"id": "hf_stable_audio", "name": "Stable Audio Open 1.0", "kind": "music", "engine": "diffusers", "repo": "stabilityai/stable-audio-open-1.0", "vram": 8, "license": "Stability AI Community", "commercial": None, "files": []},
    # ---------------- LLM / voz
    {"id": "ollama_qwen3", "name": "Qwen3 8B (Ollama)", "kind": "llm", "engine": "ollama", "pull": "qwen3:8b", "vram": 6, "license": "Apache 2.0", "commercial": True, "files": [],
     "notes": "Guionista y director creativo local."},
    {"id": "ollama_qwen25vl", "name": "Qwen2.5-VL 7B (Ollama)", "kind": "vision", "engine": "ollama", "pull": "qwen2.5vl:7b", "vram": 6, "license": "Apache 2.0", "commercial": True, "files": [],
     "notes": "Visión: describe rasgos de rostros de inspiración y analiza fotogramas."},
    {"id": "kokoro", "name": "Kokoro 82M", "kind": "tts", "engine": "kokoro", "vram": 0, "license": "Apache 2.0", "commercial": True, "files": [],
     "notes": "pip install durostcm[audio] — voces en español e inglés."},
]


def comfy_models_dir() -> Path | None:
    p = get_config().settings.endpoints.comfyui_path
    if not p:
        return None
    d = Path(p).expanduser()
    return d / "models" if (d / "models").exists() else d


def installed(entry: dict) -> bool | None:
    root = comfy_models_dir()
    if entry.get("engine") != "comfyui" or root is None:
        return None
    return all((root / f["folder"] / Path(f["path"]).name).exists() for f in entry["files"])


def catalog() -> list[dict]:
    return [{**e, "installed": installed(e), "size_gb": round(sum(f.get("gb", 0) for f in e.get("files", [])), 1)} for e in CATALOG]


async def download_entry(ctx: JobContext, model_id: str) -> dict:
    entry = next((e for e in CATALOG if e["id"] == model_id), None)
    if entry is None:
        raise KeyError(model_id)
    if entry["engine"] == "ollama":
        return await _ollama_pull(ctx, entry["pull"])
    if entry["engine"] != "comfyui":
        raise ValueError("Este modelo se descarga automáticamente la primera vez que se usa")
    root = comfy_models_dir()
    if root is None:
        raise ValueError("Configura la carpeta de ComfyUI en Ajustes → Motores para descargar modelos en su sitio")
    total = sum(f.get("gb", 1) for f in entry["files"]) or 1
    done = 0.0
    token = get_config().settings.api_keys.huggingface or os.environ.get("HF_TOKEN", "")
    for f in entry["files"]:
        dst = root / f["folder"] / Path(f["path"]).name
        if dst.exists():
            done += f.get("gb", 1)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{f['repo']}/resolve/main/{f['path']}"
        start = done / total
        span = f.get("gb", 1) / total
        await _http_download(ctx, url, dst, token, start, span, Path(f["path"]).name)
        done += f.get("gb", 1)
    return {"model": model_id, "path": str(root)}


async def _http_download(ctx: JobContext, url: str, dst: Path, token: str, start: float, span: float, label: str) -> None:
    tmp = dst.with_suffix(dst.suffix + ".part")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    pos = tmp.stat().st_size if tmp.exists() else 0
    if pos:
        headers["Range"] = f"bytes={pos}-"
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, read=300), follow_redirects=True) as c:
        async with c.stream("GET", url, headers=headers) as r:
            if r.status_code == 416:
                tmp.replace(dst)
                return
            r.raise_for_status()
            size = int(r.headers.get("content-length", 0)) + pos
            mode = "ab" if pos and r.status_code == 206 else "wb"
            if mode == "wb":
                pos = 0
            with open(tmp, mode) as fh:
                async for chunk in r.aiter_bytes(1 << 20):
                    ctx.check()
                    fh.write(chunk)
                    pos += len(chunk)
                    if size:
                        await ctx.progress(start + span * pos / size, f"{label}: {pos / 2**30:.2f}/{size / 2**30:.2f} GB")
    tmp.replace(dst)


async def _ollama_pull(ctx: JobContext, name: str) -> dict:
    import json

    url = get_config().settings.endpoints.ollama_url.rstrip("/") + "/api/pull"
    async with httpx.AsyncClient(timeout=None, trust_env=False) as c:
        async with c.stream("POST", url, json={"name": name, "stream": True}) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                ctx.check()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("total"):
                    await ctx.progress(d.get("completed", 0) / d["total"], d.get("status", ""))
                elif d.get("status"):
                    await ctx.progress(ctx.job.progress, d["status"])
    await asyncio.sleep(0)
    return {"model": name}

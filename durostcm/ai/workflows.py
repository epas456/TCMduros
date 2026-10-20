"""Flujos ComfyUI integrados (formato API) con marcadores ``{{nombre|defecto}}``.

Marcadores disponibles: prompt, negative, seed, width, height, steps, cfg, guidance,
frames, fps, image, end_image, video, audio, strength, filename_prefix, model.

Cada flujo declara en ``meta``:
* ``capability``: capacidad que cubre.
* ``models``: {"Nodo.entrada": "archivo"} — modelos necesarios (se comprueban en /object_info).
* ``main_model``: la clave de ``models`` que se sustituye si el usuario fuerza un modelo.
* ``frames_rule``: "4n+1" / "8n+1" para modelos de vídeo.
* ``tier``: calidad orientativa (1 básico … 5 máximo) para elegir el mejor disponible.
* ``vram``: GB recomendados.

Los usuarios pueden añadir sus propios flujos en ``~/durosTCM/workflows/*.json`` con el
mismo formato ({"meta": {...}, "workflow": {...}}) exportando desde ComfyUI con
"Save (API)" y sustituyendo los valores por marcadores.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from ..config import get_config

NEG_PHOTO = "cartoon, anime, illustration, 3d render, cgi, plastic skin, wax skin, airbrushed, deformed, bad anatomy, extra fingers, mutated hands, watermark, text, logo, lowres, blurry, oversaturated, jpeg artifacts"
NEG_WAN = "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"

_VIDEO_OUT = {
    "90": {"class_type": "CreateVideo", "inputs": {"images": ["__FRAMES__", 0], "fps": "{{fps}}"}},
    "91": {"class_type": "SaveVideo", "inputs": {"video": ["90", 0], "filename_prefix": "{{filename_prefix}}", "format": "mp4", "codec": "h264"}},
}


def _video(wf: dict, frames_node: str) -> dict:
    out = copy.deepcopy(wf)
    v = copy.deepcopy(_VIDEO_OUT)
    v["90"]["inputs"]["images"] = [frames_node, 0]
    out.update(v)
    return out


BUILTIN: dict[str, dict[str, Any]] = {}


def _add(wid: str, meta: dict, wf: dict) -> None:
    meta = {"id": wid, "builtin": True, **meta}
    BUILTIN[wid] = {"meta": meta, "workflow": wf}


# ------------------------------------------------------------------ imagen
_add(
    "flux_dev_t2i",
    {"label": "FLUX.1 [dev] · fotorrealismo", "capability": "text2image", "tier": 4, "vram": 12,
     "models": {"1.ckpt_name": "flux1-dev-fp8.safetensors"}, "main_model": "1.ckpt_name",
     "defaults": {"steps": 24, "guidance": 3.0}, "license": "FLUX.1-dev Non-Commercial (las salidas pueden usarse comercialmente; revisar)"},
    {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{model|flux1-dev-fp8.safetensors}}"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["1", 1]}},
        "3": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["2", 0], "guidance": "{{guidance|3.0}}"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "5": {"class_type": "EmptySD3LatentImage", "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0], "latent_image": ["5", 0],
                                                    "seed": "{{seed}}", "steps": "{{steps|24}}", "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "{{filename_prefix}}"}},
    },
)
_add(
    "flux_schnell_t2i",
    {"label": "FLUX.1 [schnell] · rápido (Apache 2.0)", "capability": "text2image", "tier": 3, "vram": 12,
     "models": {"1.ckpt_name": "flux1-schnell-fp8.safetensors"}, "main_model": "1.ckpt_name", "defaults": {"steps": 4}, "license": "Apache 2.0"},
    {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{model|flux1-schnell-fp8.safetensors}}"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["1", 1]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "5": {"class_type": "EmptySD3LatentImage", "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["4", 0], "latent_image": ["5", 0],
                                                    "seed": "{{seed}}", "steps": "{{steps|4}}", "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "{{filename_prefix}}"}},
    },
)
_add(
    "qwen_image_t2i",
    {"label": "Qwen-Image · fotorrealismo y texto (Apache 2.0)", "capability": "text2image", "tier": 5, "vram": 20,
     "models": {"1.unet_name": "qwen_image_fp8_e4m3fn.safetensors", "2.clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "3.vae_name": "qwen_image_vae.safetensors"},
     "main_model": "1.unet_name", "defaults": {"steps": 20, "cfg": 2.5}, "license": "Apache 2.0"},
    {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "{{model|qwen_image_fp8_e4m3fn.safetensors}}", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.1}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative}}", "clip": ["2", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0],
                                                    "seed": "{{seed}}", "steps": "{{steps|20}}", "cfg": "{{cfg|2.5}}", "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "{{filename_prefix}}"}},
    },
)
_add(
    "sdxl_t2i",
    {"label": "SDXL (RealVisXL, Juggernaut…) · 8 GB", "capability": "text2image", "tier": 2, "vram": 8,
     "models": {"1.ckpt_name": "sd_xl_base_1.0.safetensors"}, "main_model": "1.ckpt_name", "any_model": True, "defaults": {"steps": 30, "cfg": 5.5}},
    {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{model|sd_xl_base_1.0.safetensors}}"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative}}", "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
                                                    "seed": "{{seed}}", "steps": "{{steps|30}}", "cfg": "{{cfg|5.5}}", "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "{{filename_prefix}}"}},
    },
)
_add(
    "sdxl_i2i",
    {"label": "SDXL · imagen→imagen", "capability": "image2image", "tier": 2, "vram": 8,
     "models": {"1.ckpt_name": "sd_xl_base_1.0.safetensors"}, "main_model": "1.ckpt_name", "any_model": True},
    {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{model|sd_xl_base_1.0.safetensors}}"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative}}", "clip": ["1", 1]}},
        "4": {"class_type": "LoadImage", "inputs": {"image": "{{image}}"}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["5", 0],
                                                    "seed": "{{seed}}", "steps": "{{steps|30}}", "cfg": "{{cfg|5.5}}", "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": "{{strength|0.55}}"}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "{{filename_prefix}}"}},
    },
)
_add(
    "flux_kontext_ref",
    {"label": "FLUX.1 Kontext · mismo personaje en nueva escena", "capability": "image2image", "tier": 5, "vram": 16, "reference": True,
     "models": {"1.unet_name": "flux1-dev-kontext_fp8_scaled.safetensors", "2.clip_name2": "t5xxl_fp8_e4m3fn_scaled.safetensors", "3.vae_name": "ae.safetensors"},
     "main_model": "1.unet_name", "defaults": {"steps": 20, "guidance": 2.5}, "license": "FLUX.1 Kontext dev Non-Commercial (revisar)"},
    {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "{{model|flux1-dev-kontext_fp8_scaled.safetensors}}", "weight_dtype": "default"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl_fp8_e4m3fn_scaled.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": "{{image}}"}},
        "5": {"class_type": "FluxKontextImageScale", "inputs": {"image": ["4", 0]}},
        "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["2", 0]}},
        "8": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["7", 0], "latent": ["6", 0]}},
        "9": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["8", 0], "guidance": "{{guidance|2.5}}"}},
        "10": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["7", 0]}},
        "11": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["9", 0], "negative": ["10", 0], "latent_image": ["6", 0],
                                                     "seed": "{{seed}}", "steps": "{{steps|20}}", "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": "{{filename_prefix}}"}},
    },
)
_add(
    "esrgan_upscale",
    {"label": "Real-ESRGAN x4 (ComfyUI)", "capability": "upscale_image", "tier": 3, "vram": 4,
     "models": {"2.model_name": "RealESRGAN_x4plus.pth"}, "main_model": "2.model_name", "any_model": True},
    {
        "1": {"class_type": "LoadImage", "inputs": {"image": "{{image}}"}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "{{model|RealESRGAN_x4plus.pth}}"}},
        "3": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        "4": {"class_type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": "{{filename_prefix}}"}},
    },
)

# ------------------------------------------------------------------ vídeo
_WAN5B = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "{{model|wan2.2_ti2v_5B_fp16.safetensors}}", "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
    "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
    "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["2", 0]}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative}}", "clip": ["2", 0]}},
    "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "width": "{{width}}", "height": "{{height}}", "length": "{{frames}}", "batch_size": 1}},
    "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0],
                                                "seed": "{{seed}}", "steps": "{{steps|20}}", "cfg": "{{cfg|5}}", "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
    "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
}
_WAN5B_MODELS = {"1.unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "2.clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "3.vae_name": "wan2.2_vae.safetensors"}
_add("wan22_5b_t2v",
     {"label": "Wan 2.2 TI2V 5B · texto→vídeo 720p (Apache 2.0)", "capability": "text2video", "tier": 3, "vram": 10, "frames_rule": "4n+1",
      "native_fps": 24, "native": [1280, 704], "models": _WAN5B_MODELS, "main_model": "1.unet_name", "license": "Apache 2.0"},
     _video(_WAN5B, "9"))
_wan5b_i2v = copy.deepcopy(_WAN5B)
_wan5b_i2v["10"] = {"class_type": "LoadImage", "inputs": {"image": "{{image}}"}}
_wan5b_i2v["7"]["inputs"]["start_image"] = ["10", 0]
_add("wan22_5b_i2v",
     {"label": "Wan 2.2 TI2V 5B · imagen→vídeo 720p (Apache 2.0)", "capability": "image2video", "tier": 3, "vram": 10, "frames_rule": "4n+1",
      "native_fps": 24, "native": [1280, 704], "models": _WAN5B_MODELS, "main_model": "1.unet_name", "license": "Apache 2.0"},
     _video(_wan5b_i2v, "9"))


def _wan14b(kind: str) -> dict:
    hi = f"wan2.2_{kind}_high_noise_14B_fp8_scaled.safetensors"
    lo = f"wan2.2_{kind}_low_noise_14B_fp8_scaled.safetensors"
    wf: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "{{model|%s}}" % hi, "weight_dtype": "default"}},
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": lo, "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "5": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": 8.0}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["3", 0]}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative}}", "clip": ["3", 0]}},
    }
    if kind == "i2v":
        wf["9"] = {"class_type": "LoadImage", "inputs": {"image": "{{image}}"}}
        wf["10"] = {"class_type": "WanImageToVideo", "inputs": {"positive": ["7", 0], "negative": ["8", 0], "vae": ["4", 0], "start_image": ["9", 0],
                                                                "width": "{{width}}", "height": "{{height}}", "length": "{{frames}}", "batch_size": 1}}
        pos, neg, lat = ["10", 0], ["10", 1], ["10", 2]
    else:
        wf["10"] = {"class_type": "EmptyHunyuanLatentVideo", "inputs": {"width": "{{width}}", "height": "{{height}}", "length": "{{frames}}", "batch_size": 1}}
        pos, neg, lat = ["7", 0], ["8", 0], ["10", 0]
    wf["11"] = {"class_type": "KSamplerAdvanced", "inputs": {"model": ["5", 0], "add_noise": "enable", "noise_seed": "{{seed}}", "steps": "{{steps|20}}", "cfg": "{{cfg|3.5}}",
                                                             "sampler_name": "euler", "scheduler": "simple", "positive": pos, "negative": neg, "latent_image": lat,
                                                             "start_at_step": 0, "end_at_step": 10, "return_with_leftover_noise": "enable"}}
    wf["12"] = {"class_type": "KSamplerAdvanced", "inputs": {"model": ["6", 0], "add_noise": "disable", "noise_seed": "{{seed}}", "steps": "{{steps|20}}", "cfg": "{{cfg|3.5}}",
                                                             "sampler_name": "euler", "scheduler": "simple", "positive": pos, "negative": neg, "latent_image": ["11", 0],
                                                             "start_at_step": 10, "end_at_step": 10000, "return_with_leftover_noise": "disable"}}
    wf["13"] = {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}}
    return _video(wf, "13")


for _kind, _cap in (("t2v", "text2video"), ("i2v", "image2video")):
    _add(f"wan22_14b_{_kind}",
         {"label": f"Wan 2.2 A14B · {'texto' if _kind == 't2v' else 'imagen'}→vídeo cine (Apache 2.0)", "capability": _cap, "tier": 5, "vram": 24,
          "frames_rule": "4n+1", "native_fps": 16, "native": [1280, 720],
          "models": {"1.unet_name": f"wan2.2_{_kind}_high_noise_14B_fp8_scaled.safetensors", "2.unet_name": f"wan2.2_{_kind}_low_noise_14B_fp8_scaled.safetensors",
                     "3.clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "4.vae_name": "wan_2.1_vae.safetensors"},
          "main_model": "1.unet_name", "license": "Apache 2.0"},
         _wan14b(_kind))

_LTX = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{model|ltx-video-2b-v0.9.5.safetensors}}"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "ltxv"}},
    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["2", 0]}},
    "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative}}", "clip": ["2", 0]}},
    "5": {"class_type": "LTXVConditioning", "inputs": {"positive": ["3", 0], "negative": ["4", 0], "frame_rate": "{{fps}}"}},
    "6": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": "{{width}}", "height": "{{height}}", "length": "{{frames}}", "batch_size": 1}},
    "7": {"class_type": "LTXVScheduler", "inputs": {"steps": "{{steps|30}}", "max_shift": 2.05, "base_shift": 0.95, "stretch": True, "terminal": 0.1, "latent": ["6", 0]}},
    "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
    "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": "{{seed}}"}},
    "10": {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["5", 0], "negative": ["5", 1], "cfg": "{{cfg|3}}"}},
    "11": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["9", 0], "guider": ["10", 0], "sampler": ["8", 0], "sigmas": ["7", 0], "latent_image": ["6", 0]}},
    "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["1", 2]}},
}
_add("ltxv_t2v",
     {"label": "LTX-Video 2B · rápido (8 GB)", "capability": "text2video", "tier": 2, "vram": 8, "frames_rule": "8n+1", "native_fps": 24, "native": [768, 512],
      "models": {"1.ckpt_name": "ltx-video-2b-v0.9.5.safetensors", "2.clip_name": "t5xxl_fp16.safetensors"}, "main_model": "1.ckpt_name", "any_model": True,
      "license": "LTX-Video Open Weights (revisar)"},
     _video(_LTX, "12"))


# ------------------------------------------------------------------ utilidades
_PH = re.compile(r"\{\{(\w+)(?:\|([^}]*))?\}\}")


def fill(workflow: dict, values: dict[str, Any]) -> dict:
    """Sustituye marcadores conservando tipos (int/float) cuando el valor es sólo el marcador."""

    def conv(default: str | None) -> Any:
        if default is None:
            return None
        for cast in (int, float):
            try:
                return cast(default)
            except ValueError:
                pass
        if default.lower() in ("true", "false"):
            return default.lower() == "true"
        return default

    def sub(v: Any) -> Any:
        if isinstance(v, str):
            m = _PH.fullmatch(v.strip())
            if m:
                name, default = m.group(1), m.group(2)
                val = values.get(name)
                if val is None or val == "":
                    return conv(default) if default is not None else ("" if name in ("negative", "prompt") else val)
                return val
            return _PH.sub(lambda mm: str(values.get(mm.group(1)) if values.get(mm.group(1)) not in (None, "") else (mm.group(2) or "")), v)
        if isinstance(v, list):
            return [sub(x) for x in v]
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        return v

    return sub(copy.deepcopy(workflow))


def frames_for(duration: float, fps: int, rule: str | None) -> int:
    n = max(1, int(round(duration * fps)))
    if rule == "4n+1":
        return 4 * max(1, round((n - 1) / 4)) + 1
    if rule == "8n+1":
        return 8 * max(1, round((n - 1) / 8)) + 1
    return n


def user_workflows() -> dict[str, dict]:
    out: dict[str, dict] = {}
    d = get_config().workflows_dir
    for f in sorted(d.glob("*.json")):
        if f.name.endswith(".meta.json"):
            continue
        try:
            data = json.loads(f.read_text("utf-8"))
        except Exception:
            continue
        if "workflow" in data and "meta" in data:
            meta, wf = data["meta"], data["workflow"]
        else:
            sidecar = f.with_name(f.stem + ".meta.json")
            meta = json.loads(sidecar.read_text("utf-8")) if sidecar.exists() else {}
            wf = data
            if "capability" not in meta:
                prefix = f.stem.split("_")[0].lower()
                meta["capability"] = {
                    "t2i": "text2image", "i2i": "image2image", "t2v": "text2video", "i2v": "image2video", "up": "upscale_image",
                    "upv": "upscale_video", "lip": "lipsync", "tts": "tts", "music": "music",
                }.get(prefix, "text2image")
        meta.setdefault("label", f.stem)
        meta.setdefault("tier", 6)  # los del usuario tienen prioridad
        meta["id"] = f"user:{f.stem}"
        meta["builtin"] = False
        out[meta["id"]] = {"meta": meta, "workflow": wf}
    return out


def all_workflows() -> dict[str, dict]:
    return {**BUILTIN, **user_workflows()}


def save_user_workflow(name: str, meta: dict, workflow: dict) -> Path:
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "flujo"
    p = get_config().workflows_dir / f"{safe}.json"
    p.write_text(json.dumps({"meta": meta, "workflow": workflow}, ensure_ascii=False, indent=1), "utf-8")
    return p

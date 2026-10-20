"""Detección de hardware y estimaciones de tiempo para planificar producciones."""

from __future__ import annotations

import functools
import os
import platform
import shutil
import subprocess
import sys


@functools.lru_cache(maxsize=1)
def detect() -> dict:
    info: dict = {
        "os": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "cpu": platform.processor() or platform.machine(),
        "cores": os.cpu_count() or 1,
        "ram_gb": _ram_gb(),
        "gpus": [],
        "accelerator": "cpu",
    }
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            for line in out.strip().splitlines():
                name, mem, drv = [x.strip() for x in line.split(",")]
                info["gpus"].append({"name": name, "vram_gb": round(float(mem) / 1024, 1), "driver": drv, "vendor": "nvidia"})
            if info["gpus"]:
                info["accelerator"] = "cuda"
        except Exception:
            pass
    if sys.platform == "darwin" and platform.machine() == "arm64":
        info["accelerator"] = "mps"
        info["gpus"].append({"name": "Apple Silicon (memoria unificada)", "vram_gb": round(info["ram_gb"] * 0.7, 1), "vendor": "apple"})
    if not info["gpus"] and shutil.which("rocm-smi"):
        info["accelerator"] = "rocm"
        info["gpus"].append({"name": "AMD ROCm", "vram_gb": None, "vendor": "amd"})
    vram = max((g.get("vram_gb") or 0 for g in info["gpus"]), default=0)
    info["vram_gb"] = vram
    info["tier"] = tier_for(vram, info["accelerator"])
    return info


def _ram_gb() -> float:
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        return round(int(line.split()[1]) / 1024 / 1024, 1)
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout
            return round(int(out) / 2**30, 1)
        if sys.platform.startswith("win"):
            import ctypes

            class MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = MEMSTAT()
            st.dwLength = ctypes.sizeof(MEMSTAT)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))  # type: ignore[attr-defined]
            return round(st.ullTotalPhys / 2**30, 1)
    except Exception:
        pass
    return 0.0


# Segundos de cómputo orientativos (Wan 2.2 TI2V 5B a 720p/24 fps, FLUX/Qwen a ~1 MP).
# Referencia: Wan 2.2 5B genera 5 s de vídeo 720p en ~9 min en una RTX 4090.
TIERS = {
    "cpu": {"label": "Sin GPU (modo boceto)", "image_s": None, "video_s_per_s": None},
    "entry": {"label": "GPU 8 GB (RTX 3060/4060)", "image_s": 40, "video_s_per_s": 240},
    "mid": {"label": "GPU 12-16 GB (RTX 4070/4080)", "image_s": 20, "video_s_per_s": 170},
    "high": {"label": "GPU 24 GB (RTX 3090/4090)", "image_s": 10, "video_s_per_s": 110},
    "pro": {"label": "GPU 32-80 GB (RTX 5090 / A6000 / H100)", "image_s": 5, "video_s_per_s": 50},
    "apple": {"label": "Apple Silicon", "image_s": 60, "video_s_per_s": 600},
}


def tier_for(vram: float, accel: str) -> str:
    if accel == "mps":
        return "apple"
    if accel not in ("cuda", "rocm") or not vram:
        return "cpu"
    if vram >= 30:
        return "pro"
    if vram >= 20:
        return "high"
    if vram >= 11:
        return "mid"
    return "entry"


def recommendations(tier: str) -> dict:
    rec = {
        "cpu": {"image": "Procedural (bocetos) · instala una GPU o conecta un servidor ComfyUI remoto", "video": "Procedural (animación de bocetos)",
                "llm": "qwen3:4b en Ollama (CPU)", "tts": "Kokoro (funciona en CPU)"},
        "entry": {"image": "FLUX.1 schnell fp8 / SDXL (RealVisXL)", "video": "LTX-Video 2B o Wan 2.2 5B (GGUF/offload)", "llm": "qwen3:8b", "tts": "Kokoro"},
        "mid": {"image": "FLUX.1 dev fp8 / FLUX Kontext", "video": "Wan 2.2 TI2V 5B (720p 24fps)", "llm": "qwen3:8b / gemma3:12b", "tts": "Kokoro"},
        "high": {"image": "Qwen-Image fp8 / FLUX.1 dev", "video": "Wan 2.2 A14B fp8 (cine 720p)", "llm": "qwen3:14b", "tts": "Kokoro"},
        "pro": {"image": "Qwen-Image / FLUX.1 dev (bf16)", "video": "Wan 2.2 A14B bf16 + LTX-2 / HunyuanVideo 1.5", "llm": "qwen3:32b", "tts": "Kokoro"},
        "apple": {"image": "FLUX.1 schnell / SDXL (MPS)", "video": "LTX-Video 2B / Wan 2.2 5B (lento)", "llm": "qwen3:8b", "tts": "Kokoro"},
    }
    return rec.get(tier, rec["cpu"])


def estimate(shots: int, seconds_of_video: float, images_per_shot: int = 1, upscale_4k: bool = False, tier: str | None = None) -> dict:
    """Estimación aproximada del tiempo de una producción en este equipo."""
    t = tier or detect()["tier"]
    spec = TIERS.get(t, TIERS["cpu"])
    if spec["image_s"] is None:
        img = shots * images_per_shot * 2
        vid = seconds_of_video * 4
    else:
        img = shots * images_per_shot * spec["image_s"]
        vid = seconds_of_video * spec["video_s_per_s"]
    up = seconds_of_video * (12 if upscale_4k else 0) * (1 if t != "cpu" else 3)
    total = img + vid + up + 60
    return {"tier": t, "tier_label": spec["label"], "images_s": img, "video_s": vid, "upscale_s": up, "total_s": total,
            "fits_2h": total <= 7200}

"""Configuración global de durosTCM.

Todo vive bajo ``DUROSTCM_HOME`` (por defecto ``~/durosTCM``)::

    config.yaml        ajustes editables desde la interfaz
    projects/<id>/     proyecto, medios, renders y caché
    library/           personajes, localizaciones, rostros de inspiración, consentimientos
    workflows/         flujos ComfyUI propios del usuario (formato API)
    luts/ fonts/       LUTs .cube y fuentes adicionales
    models/            modelos descargados para el motor diffusers
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


def default_home() -> Path:
    env = os.environ.get("DUROSTCM_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / "durosTCM").resolve()


class EngineEndpoints(BaseModel):
    comfyui_url: str = "http://127.0.0.1:8188"
    comfyui_path: str = ""  # carpeta de instalación de ComfyUI (para descargar modelos en su sitio)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    ollama_vision_model: str = "qwen2.5vl:7b"
    openai_compat_url: str = ""  # LM Studio / llama.cpp / vLLM, p.ej. http://127.0.0.1:1234/v1
    openai_compat_model: str = ""
    a1111_url: str = "http://127.0.0.1:7861"
    realesrgan_bin: str = ""  # ruta a realesrgan-ncnn-vulkan
    rife_bin: str = ""  # ruta a rife-ncnn-vulkan
    piper_bin: str = ""
    piper_voice: str = ""  # ruta al .onnx de la voz


class DiffusersPrefs(BaseModel):
    image_model: str = "black-forest-labs/FLUX.1-schnell"
    video_model: str = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
    i2v_model: str = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
    dtype: str = "bfloat16"
    cpu_offload: bool = True


class ApiKeys(BaseModel):
    pexels: str = ""
    unsplash: str = ""
    huggingface: str = ""


class EthicsPrefs(BaseModel):
    ai_label_metadata: bool = True  # metadatos "generado con IA" en cada exportación (AI Act art. 50)
    ai_label_watermark: bool = False  # marca visible "IA" por defecto
    provenance_sidecar: bool = True  # manifiesto JSON de procedencia junto al render
    require_consent_for_real_people: bool = True
    allowed_face_licenses: list[str] = Field(default_factory=lambda: ["cc0", "pdm", "by", "by-sa"])


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 7777
    language: str = "es"
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    max_parallel_jobs: int = 1
    engine_priority: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "text2image": ["comfyui", "diffusers", "a1111", "procedural"],
            "image2image": ["comfyui", "diffusers", "a1111", "procedural"],
            "text2video": ["comfyui", "diffusers", "procedural"],
            "image2video": ["comfyui", "diffusers", "procedural"],
            "upscale_image": ["realesrgan", "comfyui", "procedural"],
            "upscale_video": ["realesrgan", "procedural"],
            "interpolate": ["rife", "procedural"],
            "tts": ["kokoro", "piper", "system", "procedural"],
            "music": ["diffusers", "procedural"],
            "llm": ["ollama", "openai_compat", "imagination"],
            "vision": ["ollama"],
            "remove_bg": ["rembg", "procedural"],
            "lipsync": ["comfyui"],
            "stt": ["whisper"],
        }
    )
    endpoints: EngineEndpoints = Field(default_factory=EngineEndpoints)
    diffusers: DiffusersPrefs = Field(default_factory=DiffusersPrefs)
    api_keys: ApiKeys = Field(default_factory=ApiKeys)
    ethics: EthicsPrefs = Field(default_factory=EthicsPrefs)
    auth_token: str = ""  # si se expone en red local, exigir este token


class AppConfig:
    """Rutas + ajustes persistidos en ``config.yaml`` (thread-safe)."""

    def __init__(self, home: Path | None = None):
        self.home = (home or default_home()).resolve()
        self._lock = threading.Lock()
        self.ensure_dirs()
        self.settings = self._load()

    # --- rutas -----------------------------------------------------------
    @property
    def projects_dir(self) -> Path:
        return self.home / "projects"

    @property
    def library_dir(self) -> Path:
        return self.home / "library"

    @property
    def workflows_dir(self) -> Path:
        return self.home / "workflows"

    @property
    def luts_dir(self) -> Path:
        return self.home / "luts"

    @property
    def fonts_dir(self) -> Path:
        return self.home / "fonts"

    @property
    def models_dir(self) -> Path:
        return self.home / "models"

    @property
    def config_file(self) -> Path:
        return self.home / "config.yaml"

    def ensure_dirs(self) -> None:
        for d in (
            self.home,
            self.home / "projects",
            self.home / "library" / "characters",
            self.home / "library" / "locations",
            self.home / "library" / "faces",
            self.home / "library" / "consents",
            self.home / "workflows",
            self.home / "luts",
            self.home / "fonts",
            self.home / "models",
        ):
            d.mkdir(parents=True, exist_ok=True)

    # --- persistencia ----------------------------------------------------
    def _load(self) -> Settings:
        s: Settings | None = None
        if self.config_file.exists():
            try:
                data = yaml.safe_load(self.config_file.read_text("utf-8")) or {}
                s = Settings.model_validate(data)
            except Exception:  # config corrupta: no bloquear el arranque
                backup = self.config_file.with_suffix(".yaml.bak")
                self.config_file.replace(backup)
        if s is None:
            s = Settings()
            self._write(s)
        return _env_overrides(s)

    def _write(self, s: Settings) -> None:
        tmp = self.config_file.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(s.model_dump(), allow_unicode=True, sort_keys=False), "utf-8")
        tmp.replace(self.config_file)

    def update(self, patch: dict[str, Any]) -> Settings:
        with self._lock:
            merged = _deep_merge(self.settings.model_dump(), patch)
            self.settings = Settings.model_validate(merged)
            self._write(self.settings)
            return self.settings


# Variables de entorno que sobrescriben la configuración (útil en Docker/servidores)
ENV_MAP = {
    "DUROSTCM_COMFYUI_URL": ("endpoints", "comfyui_url"),
    "DUROSTCM_COMFYUI_PATH": ("endpoints", "comfyui_path"),
    "DUROSTCM_OLLAMA_URL": ("endpoints", "ollama_url"),
    "DUROSTCM_OLLAMA_MODEL": ("endpoints", "ollama_model"),
    "DUROSTCM_OPENAI_URL": ("endpoints", "openai_compat_url"),
    "DUROSTCM_HOST": (None, "host"),
    "DUROSTCM_PORT": (None, "port"),
    "DUROSTCM_TOKEN": (None, "auth_token"),
    "HF_TOKEN": ("api_keys", "huggingface"),
    "PEXELS_API_KEY": ("api_keys", "pexels"),
    "UNSPLASH_ACCESS_KEY": ("api_keys", "unsplash"),
}


def _env_overrides(s: Settings) -> Settings:
    data = s.model_dump()
    changed = False
    for env, (section, key) in ENV_MAP.items():
        val = os.environ.get(env)
        if not val:
            continue
        target = data[section] if section else data
        if not target.get(key) or section is None or env.startswith("DUROSTCM_"):
            target[key] = int(val) if key == "port" else val
            changed = True
    return Settings.model_validate(data) if changed else s


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


_config: AppConfig | None = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def set_config(cfg: AppConfig) -> None:
    global _config
    _config = cfg

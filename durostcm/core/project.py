"""Modelo de datos del proyecto: medios, pistas, clips, efectos y storyboard.

Convenciones:
* Tiempos en segundos (float). ``clip.start`` es la posición en la línea de tiempo,
  ``clip.duration`` lo que ocupa en ella y ``clip.in_point`` el punto de entrada en
  el medio de origen. Con ``speed`` != 1 el clip consume ``duration * speed`` segundos
  de origen.
* ``Project.tracks`` se ordena de abajo arriba: la primera pista de vídeo es la del
  fondo (V1); las siguientes se componen encima.
* ``Transform.x/y`` son el centro del clip en fracción del lienzo (0.5, 0.5 = centro).
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------- créditos/licencias
class Credit(BaseModel):
    """Atribución de un recurso de terceros (rostro de inspiración, música, etc.)."""

    title: str = ""
    creator: str = ""
    license: str = ""  # cc0, pdm, by, by-sa, pexels, unsplash, own, consent...
    license_url: str = ""
    source_url: str = ""
    provider: str = ""
    attribution: str = ""


class Generation(BaseModel):
    """Cómo se generó un medio (para regenerarlo y para el manifiesto de procedencia)."""

    engine: str = ""
    model: str = ""
    capability: str = ""
    prompt: str = ""
    negative: str = ""
    seed: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    created: float = Field(default_factory=time.time)


# ---------------------------------------------------------------- medios
MediaKind = Literal["video", "image", "audio"]


class MediaItem(BaseModel):
    id: str = Field(default_factory=lambda: new_id("m_"))
    name: str
    kind: MediaKind
    path: str  # relativa a la carpeta del proyecto (o absoluta si es externa)
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    has_audio: bool = False
    has_video: bool = False
    vcodec: str | None = None
    acodec: str | None = None
    size_bytes: int | None = None
    proxy: str | None = None
    thumbnail: str | None = None
    waveform: str | None = None
    source: Literal["import", "upload", "generated", "stock", "render"] = "upload"
    ai_generated: bool = False
    generation: Generation | None = None
    credit: Credit | None = None
    tags: list[str] = Field(default_factory=list)
    created: float = Field(default_factory=time.time)


# ---------------------------------------------------------------- clip
class Crop(BaseModel):
    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0


class Transform(BaseModel):
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    rotation: float = 0.0  # grados
    opacity: float = 1.0
    fit: Literal["cover", "contain", "stretch", "none"] = "cover"
    flip_h: bool = False
    flip_v: bool = False
    crop: Crop = Field(default_factory=Crop)


class ColorGrade(BaseModel):
    exposure: float = 0.0  # -2..2 (paradas aprox.)
    contrast: float = 1.0  # 0..2
    saturation: float = 1.0  # 0..3
    gamma: float = 1.0
    temperature: float = 0.0  # -1 frío .. 1 cálido
    tint: float = 0.0  # -1 verde .. 1 magenta
    shadows: float = 0.0  # -1..1
    highlights: float = 0.0  # -1..1
    vignette: float = 0.0  # 0..1
    grain: float = 0.0  # 0..1
    sharpen: float = 0.0  # 0..1
    blur: float = 0.0  # 0..1
    look: str | None = None  # preset de looks.py
    lut: str | None = None  # nombre de archivo .cube en luts/
    lut_intensity: float = 1.0

    def is_identity(self) -> bool:
        return self == ColorGrade()


class Effect(BaseModel):
    type: str  # chroma_key, mirror, bw, sepia, glow, letterbox, stabilize, denoise, pixelate, invert
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class Transition(BaseModel):
    type: str = "fade"  # cualquier transición de xfade: fade, dissolve, wipeleft, slideup, circleopen, radial...
    duration: float = 0.5


class Motion(BaseModel):
    """Movimiento de cámara virtual sobre el clip (útil para fotos e IA)."""

    preset: Literal[
        "none", "push_in", "pull_out", "pan_left", "pan_right", "tilt_up", "tilt_down", "handheld", "drift"
    ] = "none"
    intensity: float = 0.5  # 0..1


class Keyframe(BaseModel):
    t: float  # segundos relativos al inicio del clip
    value: float
    easing: Literal["linear", "ease_in", "ease_out", "ease_in_out", "hold"] = "linear"


class TextStyle(BaseModel):
    content: str = "Texto"
    font: str = "Inter"
    size: float = 0.08  # fracción de la altura del lienzo
    weight: Literal["normal", "bold"] = "bold"
    color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: float = 0.0  # fracción del tamaño de fuente
    shadow: bool = True
    background: str | None = None  # p.ej. "#000000AA" para caja
    align: Literal["left", "center", "right"] = "center"
    line_spacing: float = 1.15
    letter_spacing: float = 0.0
    max_width: float = 0.9  # fracción del ancho del lienzo
    animation: Literal["none", "fade", "slide_up", "slide_down", "zoom", "typewriter"] = "fade"
    uppercase: bool = False


ClipKind = Literal["media", "text", "color", "adjustment"]


class Clip(BaseModel):
    id: str = Field(default_factory=lambda: new_id("c_"))
    kind: ClipKind = "media"
    media_id: str | None = None
    name: str = ""
    start: float = 0.0
    duration: float = 5.0
    in_point: float = 0.0
    speed: float = 1.0
    reverse: bool = False
    volume: float = 1.0
    muted: bool = False
    audio_fade_in: float = 0.0
    audio_fade_out: float = 0.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    transform: Transform = Field(default_factory=Transform)
    color: ColorGrade = Field(default_factory=ColorGrade)
    effects: list[Effect] = Field(default_factory=list)
    transition_in: Transition | None = None
    motion: Motion = Field(default_factory=Motion)
    keyframes: dict[str, list[Keyframe]] = Field(default_factory=dict)  # x, y, scale, opacity, volume
    text: TextStyle | None = None
    fill: str = "#000000"  # para clips de color
    label_color: str | None = None
    locked: bool = False

    @field_validator("duration")
    @classmethod
    def _positive(cls, v: float) -> float:
        return max(1.0 / 120.0, v)

    @field_validator("speed")
    @classmethod
    def _speed(cls, v: float) -> float:
        return min(16.0, max(0.05, v))

    @property
    def end(self) -> float:
        return self.start + self.duration

    @property
    def source_duration(self) -> float:
        return self.duration * self.speed


class Track(BaseModel):
    id: str = Field(default_factory=lambda: new_id("t_"))
    name: str = ""
    kind: Literal["video", "audio", "text"] = "video"
    clips: list[Clip] = Field(default_factory=list)
    muted: bool = False
    hidden: bool = False
    locked: bool = False
    solo: bool = False
    volume: float = 1.0


class Marker(BaseModel):
    id: str = Field(default_factory=lambda: new_id("k_"))
    t: float
    label: str = ""
    color: str = "#FFB020"


# ---------------------------------------------------------------- storyboard
class Camera(BaseModel):
    shot_size: str = "medium"  # extreme_wide, wide, medium, medium_close, close_up, extreme_close_up
    angle: str = "eye_level"  # low, high, dutch, overhead, pov
    movement: str = "static"  # dolly_in, dolly_out, pan, tilt, crane, orbit, handheld, drone, tracking
    lens: str = "35mm"


class DialogueLine(BaseModel):
    speaker: str = ""  # id o nombre de personaje, "narrador" para voz en off
    text: str = ""
    voice: str | None = None


class Shot(BaseModel):
    id: str = Field(default_factory=lambda: new_id("s_"))
    index: int = 0
    scene: str = ""
    description: str = ""
    prompt: str = ""
    negative: str = ""
    duration: float = 4.0
    camera: Camera = Field(default_factory=Camera)
    lighting: str = ""
    mood: str = ""
    characters: list[str] = Field(default_factory=list)
    location: str | None = None
    dialogue: list[DialogueLine] = Field(default_factory=list)
    on_screen_text: str = ""
    sfx: str = ""
    transition: str = "cut"
    seed: int | None = None
    image_media_id: str | None = None
    video_media_id: str | None = None
    audio_media_ids: list[str] = Field(default_factory=list)
    status: Literal["draft", "image", "video", "done", "error"] = "draft"


class Storyboard(BaseModel):
    title: str = ""
    logline: str = ""
    format: Literal["ad", "short_film", "character", "music_video", "trailer", "free"] = "free"
    style: str = ""
    look: str | None = None
    language: str = "es"
    music_prompt: str = ""
    voiceover: str = ""
    shots: list[Shot] = Field(default_factory=list)


# ---------------------------------------------------------------- proyecto
class ProjectSettings(BaseModel):
    width: int = 1920
    height: int = 1080
    fps: float = 24.0
    sample_rate: int = 48000
    background: str = "#000000"

    @field_validator("width", "height")
    @classmethod
    def _even(cls, v: int) -> int:
        v = max(16, min(8192, int(v)))
        return v - (v % 2)


class Project(BaseModel):
    id: str = Field(default_factory=lambda: new_id("p_"))
    name: str = "Proyecto sin título"
    version: int = 1
    rev: int = 0  # se incrementa cuando un proceso del servidor modifica la línea de tiempo
    created: float = Field(default_factory=time.time)
    updated: float = Field(default_factory=time.time)
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    media: list[MediaItem] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    markers: list[Marker] = Field(default_factory=list)
    storyboard: Storyboard | None = None
    characters: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    credits: list[Credit] = Field(default_factory=list)
    notes: str = ""

    # ------------------------------------------------------------ helpers
    def media_by_id(self, media_id: str | None) -> MediaItem | None:
        if not media_id:
            return None
        for m in self.media:
            if m.id == media_id:
                return m
        return None

    def find_clip(self, clip_id: str) -> tuple[Track, Clip] | None:
        for t in self.tracks:
            for c in t.clips:
                if c.id == clip_id:
                    return t, c
        return None

    def track_by_id(self, track_id: str) -> Track | None:
        return next((t for t in self.tracks if t.id == track_id), None)

    @property
    def duration(self) -> float:
        end = 0.0
        for t in self.tracks:
            for c in t.clips:
                end = max(end, c.end)
        return end

    def ensure_default_tracks(self) -> None:
        if not self.tracks:
            self.tracks = [
                Track(name="V1", kind="video"),
                Track(name="V2", kind="video"),
                Track(name="Títulos", kind="text"),
                Track(name="A1 Diálogo", kind="audio"),
                Track(name="A2 Música", kind="audio"),
            ]


def default_project(name: str = "Proyecto sin título", **settings: Any) -> Project:
    p = Project(name=name, settings=ProjectSettings(**settings))
    p.ensure_default_tracks()
    return p

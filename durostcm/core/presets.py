"""Presets de exportación: contenedores, códecs, resoluciones y plataformas."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FormatPreset:
    id: str
    label: str
    ext: str
    kind: str  # video, audio, image, sequence, gif
    vcodec: list[str] = field(default_factory=list)  # argumentos de vídeo
    acodec: list[str] = field(default_factory=list)  # argumentos de audio
    pix_fmt: str | None = "yuv420p"
    alpha: bool = False
    extra: list[str] = field(default_factory=list)
    crf_flag: str | None = "-crf"
    quality: dict[str, int] = field(default_factory=dict)  # draft/good/high/master → CRF/QP
    encoder: str | None = None  # para comprobar disponibilidad
    description: str = ""


_X264_Q = {"draft": 28, "good": 21, "high": 17, "master": 12}
_X265_Q = {"draft": 30, "good": 23, "high": 19, "master": 14}
_VP9_Q = {"draft": 40, "good": 32, "high": 24, "master": 15}
_AV1_Q = {"draft": 45, "good": 34, "high": 26, "master": 18}

FORMATS: dict[str, FormatPreset] = {
    p.id: p
    for p in [
        FormatPreset(
            "mp4_h264", "MP4 · H.264 (universal)", "mp4", "video",
            ["-c:v", "libx264", "-preset", "slow", "-profile:v", "high"], ["-c:a", "aac", "-b:a", "320k"],
            extra=["-movflags", "+faststart"], quality=_X264_Q, encoder="libx264",
            description="Compatible con todo: web, redes, televisión, móviles.",
        ),
        FormatPreset(
            "mp4_h265", "MP4 · H.265/HEVC 10-bit", "mp4", "video",
            ["-c:v", "libx265", "-preset", "medium", "-tag:v", "hvc1", "-x265-params", "log-level=error"],
            ["-c:a", "aac", "-b:a", "320k"], pix_fmt="yuv420p10le", extra=["-movflags", "+faststart"],
            quality=_X265_Q, encoder="libx265", description="Mitad de tamaño que H.264 a igual calidad. Ideal 4K/8K.",
        ),
        FormatPreset(
            "mov_prores_422hq", "MOV · Apple ProRes 422 HQ", "mov", "video",
            ["-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0", "-bits_per_mb", "8000"],
            ["-c:a", "pcm_s24le"], pix_fmt="yuv422p10le", crf_flag=None, encoder="prores_ks",
            description="Máster de postproducción / entrega a cadenas.",
        ),
        FormatPreset(
            "mov_prores_4444", "MOV · ProRes 4444 con transparencia", "mov", "video",
            ["-c:v", "prores_ks", "-profile:v", "4", "-vendor", "apl0", "-alpha_bits", "16"],
            ["-c:a", "pcm_s24le"], pix_fmt="yuva444p10le", alpha=True, crf_flag=None, encoder="prores_ks",
            description="Gráficos y personajes con canal alfa para componer.",
        ),
        FormatPreset(
            "mov_prores_proxy", "MOV · ProRes Proxy (offline)", "mov", "video",
            ["-c:v", "prores_ks", "-profile:v", "0"], ["-c:a", "pcm_s16le"], pix_fmt="yuv422p10le", crf_flag=None,
            encoder="prores_ks", description="Ligero para montaje offline.",
        ),
        FormatPreset(
            "mxf_dnxhr_hq", "MXF · Avid DNxHR HQ", "mxf", "video",
            ["-c:v", "dnxhd", "-profile:v", "dnxhr_hq"], ["-c:a", "pcm_s24le"], pix_fmt="yuv422p", crf_flag=None,
            encoder="dnxhd", description="Intermedio para Avid Media Composer / broadcast.",
        ),
        FormatPreset(
            "mov_dnxhr_444", "MOV · DNxHR 444 (12-bit)", "mov", "video",
            ["-c:v", "dnxhd", "-profile:v", "dnxhr_444"], ["-c:a", "pcm_s24le"], pix_fmt="yuv444p10le", crf_flag=None,
            encoder="dnxhd", description="Máxima calidad intermedia 4:4:4.",
        ),
        FormatPreset(
            "webm_vp9", "WebM · VP9", "webm", "video",
            ["-c:v", "libvpx-vp9", "-b:v", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "2"],
            ["-c:a", "libopus", "-b:a", "192k"], quality=_VP9_Q, encoder="libvpx-vp9", description="Web abierta, YouTube.",
        ),
        FormatPreset(
            "webm_vp9_alpha", "WebM · VP9 con transparencia", "webm", "video",
            ["-c:v", "libvpx-vp9", "-b:v", "0", "-row-mt", "1", "-auto-alt-ref", "0"], ["-c:a", "libopus", "-b:a", "160k"],
            pix_fmt="yuva420p", alpha=True, quality=_VP9_Q, encoder="libvpx-vp9", description="Overlays animados para web.",
        ),
        FormatPreset(
            "mp4_av1", "MP4 · AV1 (SVT-AV1)", "mp4", "video",
            ["-c:v", "libsvtav1", "-preset", "6", "-svtav1-params", "tune=0"], ["-c:a", "aac", "-b:a", "256k"],
            pix_fmt="yuv420p10le", extra=["-movflags", "+faststart"], quality=_AV1_Q, encoder="libsvtav1",
            description="Máxima eficiencia moderna (streaming 4K/8K).",
        ),
        FormatPreset(
            "mkv_h264_lossless", "MKV · H.264 sin pérdidas", "mkv", "video",
            ["-c:v", "libx264", "-preset", "veryslow", "-qp", "0"], ["-c:a", "flac"], pix_fmt="yuv444p", crf_flag=None,
            encoder="libx264", description="Archivo máster sin pérdida.",
        ),
        # --- aceleración por hardware (se muestran sólo si FFmpeg los incluye) ---
        FormatPreset(
            "mp4_h264_nvenc", "MP4 · H.264 NVIDIA NVENC (rápido)", "mp4", "video",
            ["-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr"], ["-c:a", "aac", "-b:a", "320k"],
            extra=["-movflags", "+faststart"], crf_flag="-cq", quality={"draft": 30, "good": 23, "high": 19, "master": 15},
            encoder="h264_nvenc", description="Codificación por GPU NVIDIA: 5-10x más rápido.",
        ),
        FormatPreset(
            "mp4_hevc_nvenc", "MP4 · HEVC 10-bit NVIDIA NVENC", "mp4", "video",
            ["-c:v", "hevc_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-tag:v", "hvc1"], ["-c:a", "aac", "-b:a", "320k"],
            pix_fmt="p010le", extra=["-movflags", "+faststart"], crf_flag="-cq", quality={"draft": 32, "good": 25, "high": 21, "master": 17},
            encoder="hevc_nvenc", description="4K/8K por GPU NVIDIA.",
        ),
        FormatPreset(
            "mp4_av1_nvenc", "MP4 · AV1 NVIDIA (RTX 40+)", "mp4", "video",
            ["-c:v", "av1_nvenc", "-preset", "p6", "-rc", "vbr"], ["-c:a", "aac", "-b:a", "256k"],
            pix_fmt="p010le", extra=["-movflags", "+faststart"], crf_flag="-cq", quality={"draft": 40, "good": 32, "high": 27, "master": 22},
            encoder="av1_nvenc", description="AV1 por GPU (RTX 40 o superior).",
        ),
        FormatPreset(
            "mp4_hevc_videotoolbox", "MP4 · HEVC Apple VideoToolbox", "mp4", "video",
            ["-c:v", "hevc_videotoolbox", "-tag:v", "hvc1", "-allow_sw", "1"], ["-c:a", "aac", "-b:a", "320k"],
            pix_fmt="p010le", extra=["-movflags", "+faststart"], crf_flag="-q:v", quality={"draft": 45, "good": 60, "high": 70, "master": 80},
            encoder="hevc_videotoolbox", description="Codificación por hardware en Mac (Apple Silicon).",
        ),
        FormatPreset(
            "mov_prores_videotoolbox", "MOV · ProRes 422 HQ Apple (hardware)", "mov", "video",
            ["-c:v", "prores_videotoolbox", "-profile:v", "hq"], ["-c:a", "pcm_s24le"], pix_fmt="p210le", crf_flag=None,
            encoder="prores_videotoolbox", description="ProRes acelerado en Mac M1 Pro/Max/Ultra y posteriores.",
        ),
        FormatPreset(
            "mp4_hevc_qsv", "MP4 · HEVC Intel Quick Sync", "mp4", "video",
            ["-c:v", "hevc_qsv", "-preset", "slower", "-tag:v", "hvc1"], ["-c:a", "aac", "-b:a", "320k"],
            pix_fmt="nv12", extra=["-movflags", "+faststart"], crf_flag="-global_quality", quality={"draft": 32, "good": 25, "high": 21, "master": 18},
            encoder="hevc_qsv", description="GPU integrada Intel / Arc.",
        ),
        FormatPreset(
            "gif", "GIF animado (paleta optimizada)", "gif", "gif", [], [], pix_fmt=None, crf_flag=None,
            description="Memes, previsualizaciones y correos.",
        ),
        FormatPreset(
            "png_sequence", "Secuencia PNG (16-bit, ZIP)", "zip", "sequence", ["-c:v", "png"], [], pix_fmt="rgba64be",
            alpha=True, crf_flag=None, description="Fotogramas sueltos para VFX y etalonaje.",
        ),
        FormatPreset(
            "jpg_sequence", "Secuencia JPG (ZIP)", "zip", "sequence", ["-c:v", "mjpeg", "-q:v", "2"], [], pix_fmt="yuvj444p",
            crf_flag=None, description="Fotogramas ligeros.",
        ),
        FormatPreset("png_still", "Fotograma PNG", "png", "image", ["-c:v", "png"], [], pix_fmt="rgb24", crf_flag=None),
        FormatPreset("jpg_still", "Fotograma JPG / póster", "jpg", "image", ["-c:v", "mjpeg", "-q:v", "1"], [], pix_fmt="yuvj444p", crf_flag=None),
        FormatPreset("wav", "Audio WAV 24-bit 48 kHz", "wav", "audio", [], ["-c:a", "pcm_s24le"], pix_fmt=None, crf_flag=None),
        FormatPreset("mp3", "Audio MP3 320 kbps", "mp3", "audio", [], ["-c:a", "libmp3lame", "-b:a", "320k"], pix_fmt=None, crf_flag=None),
        FormatPreset("flac", "Audio FLAC sin pérdidas", "flac", "audio", [], ["-c:a", "flac"], pix_fmt=None, crf_flag=None),
        FormatPreset("m4a", "Audio AAC (M4A)", "m4a", "audio", [], ["-c:a", "aac", "-b:a", "256k"], pix_fmt=None, crf_flag=None),
    ]
}

RESOLUTIONS = [
    {"id": "8k", "label": "8K UHD", "w": 7680, "h": 4320},
    {"id": "dci4k", "label": "4K DCI (cine)", "w": 4096, "h": 2160},
    {"id": "uhd4k", "label": "4K UHD", "w": 3840, "h": 2160},
    {"id": "1440p", "label": "QHD 1440p", "w": 2560, "h": 1440},
    {"id": "dci2k", "label": "2K DCI", "w": 2048, "h": 1080},
    {"id": "1080p", "label": "Full HD 1080p", "w": 1920, "h": 1080},
    {"id": "720p", "label": "HD 720p", "w": 1280, "h": 720},
    {"id": "480p", "label": "SD 480p", "w": 854, "h": 480},
]

ASPECTS = [
    {"id": "16:9", "label": "16:9 Horizontal", "ratio": 16 / 9},
    {"id": "9:16", "label": "9:16 Vertical (Reels/TikTok/Shorts)", "ratio": 9 / 16},
    {"id": "1:1", "label": "1:1 Cuadrado", "ratio": 1.0},
    {"id": "4:5", "label": "4:5 Feed Instagram", "ratio": 4 / 5},
    {"id": "4:3", "label": "4:3 Clásico", "ratio": 4 / 3},
    {"id": "21:9", "label": "21:9 Ultrapanorámico", "ratio": 21 / 9},
    {"id": "2.39:1", "label": "2.39:1 Cinemascope", "ratio": 2.39},
    {"id": "1.85:1", "label": "1.85:1 Cine plano", "ratio": 1.85},
]

PLATFORMS = [
    {"id": "youtube_4k", "label": "YouTube 4K", "format": "mp4_h264", "w": 3840, "h": 2160, "fps": None, "loudness": -14, "quality": "high"},
    {"id": "youtube_1080", "label": "YouTube 1080p", "format": "mp4_h264", "w": 1920, "h": 1080, "fps": None, "loudness": -14, "quality": "high"},
    {"id": "tiktok", "label": "TikTok / Reels / Shorts", "format": "mp4_h264", "w": 1080, "h": 1920, "fps": 30, "loudness": -14, "quality": "high"},
    {"id": "instagram_feed", "label": "Instagram Feed 4:5", "format": "mp4_h264", "w": 1080, "h": 1350, "fps": 30, "loudness": -14, "quality": "high"},
    {"id": "instagram_square", "label": "Instagram 1:1", "format": "mp4_h264", "w": 1080, "h": 1080, "fps": 30, "loudness": -14, "quality": "high"},
    {"id": "x_twitter", "label": "X / Twitter", "format": "mp4_h264", "w": 1920, "h": 1080, "fps": 30, "loudness": -14, "quality": "good"},
    {"id": "linkedin", "label": "LinkedIn", "format": "mp4_h264", "w": 1920, "h": 1080, "fps": 30, "loudness": -14, "quality": "good"},
    {"id": "tv_broadcast", "label": "TV broadcast (EBU R128)", "format": "mov_prores_422hq", "w": 1920, "h": 1080, "fps": 25, "loudness": -23, "quality": "master"},
    {"id": "cinema_dci", "label": "Cine DCI 4K (máster ProRes)", "format": "mov_prores_422hq", "w": 4096, "h": 2160, "fps": 24, "loudness": -27, "quality": "master"},
    {"id": "netflix_uhd", "label": "Streaming UHD (máster HEVC 10-bit)", "format": "mp4_h265", "w": 3840, "h": 2160, "fps": None, "loudness": -27, "quality": "master"},
    {"id": "web_hero", "label": "Vídeo de fondo web (ligero, sin audio)", "format": "webm_vp9", "w": 1920, "h": 1080, "fps": 30, "loudness": None, "quality": "good", "no_audio": True},
]

FPS_OPTIONS = [23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60, 120]


def get_format(fid: str) -> FormatPreset:
    if fid not in FORMATS:
        raise KeyError(f"Formato desconocido: {fid}")
    return FORMATS[fid]


def catalog() -> dict:
    from .ffmpeg import available_encoders

    enc = available_encoders()
    return {
        "formats": [
            {
                "id": f.id,
                "label": f.label,
                "ext": f.ext,
                "kind": f.kind,
                "alpha": f.alpha,
                "description": f.description,
                "available": f.encoder is None or f.encoder in enc,
            }
            for f in FORMATS.values()
        ],
        "resolutions": RESOLUTIONS,
        "aspects": ASPECTS,
        "platforms": PLATFORMS,
        "fps": FPS_OPTIONS,
        "qualities": ["draft", "good", "high", "master"],
    }

"""Importación de medios: análisis, miniaturas, proxies para previsualizar y formas de onda."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from .ffmpeg import FFmpegError, ffmpeg_bin, probe, run_ffmpeg, run_ffmpeg_sync
from .project import Credit, Generation, MediaItem, Project
from .storage import ProjectStore

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mxf", ".mts", ".m2ts", ".ts", ".wmv", ".flv", ".3gp", ".ogv", ".gif"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".exr", ".heic", ".avif"}
AUDIO_EXT = {".wav", ".mp3", ".aac", ".m4a", ".flac", ".ogg", ".opus", ".aiff", ".aif", ".wma"}

# Códecs que el navegador reproduce sin proxy
BROWSER_VCODECS = {"h264", "vp8", "vp9", "av1"}
BROWSER_ACODECS = {"aac", "mp3", "opus", "vorbis", "flac", "pcm_s16le"}


def kind_for(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    return None


def unique_name(folder: Path, name: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in name).strip() or "medio"
    target = folder / safe
    stem, suf = target.stem, target.suffix
    i = 1
    while target.exists():
        target = folder / f"{stem}_{i}{suf}"
        i += 1
    return target


def register_media(
    store: ProjectStore,
    project: Project,
    file: Path,
    *,
    name: str | None = None,
    source: str = "upload",
    generation: Generation | None = None,
    credit: Credit | None = None,
    tags: list[str] | None = None,
    make_proxy: bool = True,
) -> MediaItem:
    """Analiza ``file`` (ya dentro del proyecto o externo) y lo añade al proyecto."""
    info = probe(file)
    kind = kind_for(file)
    if info.get("is_image"):
        kind = "image"
    if kind is None:
        kind = "video" if info["has_video"] else ("audio" if info["has_audio"] else None)
    if kind is None:
        raise ValueError(f"Formato no soportado: {file.name}")
    if kind == "video" and not info["has_video"]:
        kind = "audio"
    item = MediaItem(
        name=name or file.name,
        kind=kind,  # type: ignore[arg-type]
        path=store.relative(project.id, file),
        duration=None if kind == "image" else info.get("duration"),
        width=info.get("width"),
        height=info.get("height"),
        fps=info.get("fps") if kind == "video" else None,
        has_audio=bool(info.get("has_audio")) and kind != "image",
        has_video=bool(info.get("has_video")),
        vcodec=info.get("vcodec"),
        acodec=info.get("acodec"),
        size_bytes=info.get("size_bytes"),
        source=source,  # type: ignore[arg-type]
        ai_generated=generation is not None,
        generation=generation,
        credit=credit,
        tags=tags or [],
    )
    cache = store.subdir(project.id, "cache")
    try:
        item.thumbnail = store.relative(project.id, make_thumbnail(file, kind, cache / f"{item.id}_thumb.jpg", item.duration))
    except Exception:
        item.thumbnail = None
    if kind in ("video", "audio") and item.has_audio:
        try:
            item.waveform = store.relative(project.id, make_waveform(file, cache / f"{item.id}_wave.json"))
        except Exception:
            item.waveform = None
    if make_proxy and kind == "video" and needs_proxy(item):
        item.proxy = None  # se genera en segundo plano (ver media_jobs)
    project.media.append(item)
    if credit and credit not in project.credits:
        project.credits.append(credit)
    return item


def needs_proxy(item: MediaItem) -> bool:
    if item.kind != "video":
        return False
    if (item.vcodec or "") not in BROWSER_VCODECS:
        return True
    if item.has_audio and (item.acodec or "") not in BROWSER_ACODECS:
        return True
    return (item.width or 0) * (item.height or 0) > 2560 * 1440


async def make_proxy(src: Path, dst: Path, duration: float | None, progress=None, cancel_event=None) -> Path:
    """Proxy H.264 720p ligero para la previsualización en el navegador."""
    args = [
        "-i", str(src),
        "-vf", "scale='min(1280,iw)':-2:flags=bicubic,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-g", "12",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(dst),
    ]
    await run_ffmpeg(args, duration=duration, progress=progress, cancel_event=cancel_event, label="proxy")
    return dst


def make_thumbnail(src: Path, kind: str, dst: Path, duration: float | None = None, width: int = 480) -> Path:
    if kind == "audio":
        run_ffmpeg_sync(
            [
                "-i", str(src), "-filter_complex",
                f"aformat=channel_layouts=mono,showwavespic=s={width}x{width * 9 // 16}:colors=#7CFFCB",
                "-frames:v", "1", str(dst),
            ]
        )
        return dst
    seek = []
    if kind == "video" and duration and duration > 1:
        seek = ["-ss", f"{min(duration * 0.1, 3.0):.3f}"]
    run_ffmpeg_sync([*seek, "-i", str(src), "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", str(dst)])
    return dst


def make_waveform(src: Path, dst: Path, points_per_second: int = 50) -> Path:
    """Picos de amplitud (0..1) para dibujar la onda en la línea de tiempo."""
    import subprocess

    sr = 8000
    cmd = [ffmpeg_bin(), "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, timeout=300).stdout
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    hop = max(1, sr // points_per_second)
    n = len(data) // hop
    if n == 0:
        peaks: list[float] = []
    else:
        peaks = np.abs(data[: n * hop].reshape(n, hop)).max(axis=1).round(3).tolist()
    dst.write_text(json.dumps({"pps": points_per_second, "peaks": peaks}), "utf-8")
    return dst


def import_file(
    store: ProjectStore,
    project: Project,
    src: Path,
    *,
    copy: bool = True,
    name: str | None = None,
    **kw,
) -> MediaItem:
    """Importa un archivo local copiándolo a ``media/`` (o enlazándolo si copy=False)."""
    src = Path(src).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(str(src))
    if copy:
        dst = unique_name(store.subdir(project.id, "media"), src.name)
        shutil.copy2(src, dst)
    else:
        dst = src
    try:
        return register_media(store, project, dst, name=name or src.name, source=kw.pop("source", "import"), **kw)
    except (FFmpegError, ValueError):
        if copy:
            dst.unlink(missing_ok=True)
        raise

"""Utilidades de bajo nivel para FFmpeg/FFprobe (con progreso y cancelación)."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Awaitable, Callable

from ..config import get_config

ProgressCB = Callable[[float, str], Awaitable[None] | None]


class FFmpegError(RuntimeError):
    def __init__(self, message: str, log: str = ""):
        super().__init__(message)
        self.log = log


def ffmpeg_bin() -> str:
    return get_config().settings.ffmpeg or "ffmpeg"


def ffprobe_bin() -> str:
    return get_config().settings.ffprobe or "ffprobe"


def has_ffmpeg() -> bool:
    return shutil.which(ffmpeg_bin()) is not None and shutil.which(ffprobe_bin()) is not None


def ffmpeg_version() -> str:
    try:
        out = subprocess.run([ffmpeg_bin(), "-version"], capture_output=True, text=True, timeout=10).stdout
        return out.splitlines()[0] if out else "?"
    except Exception:
        return "no encontrado"


_encoders_cache: set[str] | None = None


def available_encoders() -> set[str]:
    global _encoders_cache
    if _encoders_cache is None:
        try:
            out = subprocess.run(
                [ffmpeg_bin(), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20
            ).stdout
            _encoders_cache = {
                line.split()[1] for line in out.splitlines() if len(line.split()) > 1 and line.startswith(" ")
            }
        except Exception:
            _encoders_cache = set()
    return _encoders_cache


def probe(path: str | Path) -> dict:
    """Devuelve información normalizada de un archivo multimedia."""
    cmd = [
        ffprobe_bin(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise FFmpegError(f"ffprobe no pudo leer {Path(path).name}", res.stderr)
    data = json.loads(res.stdout or "{}")
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    info: dict = {
        "duration": _float(fmt.get("duration")),
        "size_bytes": int(fmt.get("size", 0) or 0),
        "format": fmt.get("format_name", ""),
        "has_video": v is not None,
        "has_audio": a is not None,
        "vcodec": v.get("codec_name") if v else None,
        "acodec": a.get("codec_name") if a else None,
        "width": None,
        "height": None,
        "fps": None,
        "rotation": 0,
        "pix_fmt": v.get("pix_fmt") if v else None,
    }
    if v:
        w, h = int(v.get("width", 0) or 0), int(v.get("height", 0) or 0)
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        tags_rot = (v.get("tags") or {}).get("rotate")
        if tags_rot:
            rot = int(tags_rot)
        if abs(rot) in (90, 270):
            w, h = h, w
        info.update(width=w, height=h, rotation=rot, fps=_rate(v.get("avg_frame_rate") or v.get("r_frame_rate")))
        if info["duration"] is None:
            info["duration"] = _float(v.get("duration"))
        # imágenes fijas: ffprobe las ve como vídeo de 1 frame
        if v.get("codec_name") in {"png", "mjpeg", "webp", "bmp", "tiff", "gif"} and (
            (info["duration"] or 0) <= 0.05 or fmt.get("format_name") in {"image2", "png_pipe", "jpeg_pipe", "webp_pipe"}
        ):
            if v.get("codec_name") != "gif" or int(v.get("nb_frames", 1) or 1) <= 1:
                info["is_image"] = True
    if a and info["duration"] is None:
        info["duration"] = _float(a.get("duration"))
    return info


def _float(x) -> float | None:
    try:
        f = float(x)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _rate(r: str | None) -> float | None:
    if not r or r in ("0/0",):
        return None
    try:
        if "/" in r:
            n, d = r.split("/")
            return round(float(n) / float(d), 3) if float(d) else None
        return float(r)
    except (ValueError, ZeroDivisionError):
        return None


_TIME_RE = re.compile(r"out_time_(?:us|ms)=(\d+)")


async def run_ffmpeg(
    args: list[str],
    *,
    duration: float | None = None,
    progress: ProgressCB | None = None,
    cancel_event: asyncio.Event | None = None,
    label: str = "ffmpeg",
    cwd: str | Path | None = None,
) -> str:
    """Ejecuta ffmpeg informando del progreso (0..1). Devuelve el log de stderr."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-y", "-nostdin", "-progress", "pipe:1", "-nostats", *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=str(cwd) if cwd else None
    )
    stderr_chunks: list[bytes] = []

    async def read_err():
        assert proc.stderr
        while True:
            chunk = await proc.stderr.read(65536)
            if not chunk:
                break
            stderr_chunks.append(chunk)
            if len(stderr_chunks) > 400:  # limitar memoria
                del stderr_chunks[:200]

    async def read_out():
        assert proc.stdout
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            m = _TIME_RE.search(line.decode("utf-8", "ignore"))
            if m and duration and progress:
                t = int(m.group(1)) / 1_000_000
                r = progress(min(0.999, max(0.0, t / duration)), label)
                if asyncio.iscoroutine(r):
                    await r

    async def watch_cancel():
        if cancel_event is None:
            return
        await cancel_event.wait()
        if proc.returncode is None:
            proc.kill()

    cancel_task = asyncio.create_task(watch_cancel())
    try:
        await asyncio.gather(read_err(), read_out())
        rc = await proc.wait()
    finally:
        cancel_task.cancel()
    log = b"".join(stderr_chunks).decode("utf-8", "ignore")
    if cancel_event is not None and cancel_event.is_set():
        raise asyncio.CancelledError()
    if rc != 0:
        tail = "\n".join(log.strip().splitlines()[-25:])
        raise FFmpegError(f"FFmpeg falló ({label}, código {rc}):\n{tail}", log)
    if progress:
        r = progress(1.0, label)
        if asyncio.iscoroutine(r):
            await r
    return log


def run_ffmpeg_sync(args: list[str], timeout: float = 600, cwd: str | Path | None = None) -> str:
    cmd = [ffmpeg_bin(), "-hide_banner", "-y", "-nostdin", *args]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(cwd) if cwd else None)
    if res.returncode != 0:
        tail = "\n".join(res.stderr.strip().splitlines()[-25:])
        raise FFmpegError(f"FFmpeg falló:\n{tail}", res.stderr)
    return res.stderr


_major: int | None = None


def ffmpeg_major() -> int:
    global _major
    if _major is None:
        m = re.search(r"version n?(\d+)", ffmpeg_version())
        _major = int(m.group(1)) if m else 6
    return _major


def filter_script_args(path: str | Path) -> list[str]:
    """Argumentos para leer el filtergraph desde archivo (evita límites de línea de comandos)."""
    if ffmpeg_major() >= 7:
        return ["-/filter_complex", str(path)]
    return ["-filter_complex_script", str(path)]


def escape_filter_path(p: str | Path) -> str:
    """Escapa una ruta para usarla dentro de un filtergraph (lut3d=file=..., etc.)."""
    s = str(Path(p).resolve()).replace("\\", "/")
    return s.replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")

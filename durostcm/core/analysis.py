"""Análisis de medios: cortes de escena, pulsos musicales y subtítulos (SRT)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np

from .ffmpeg import ffmpeg_bin

_PTS = re.compile(r"pts_time:([0-9.]+)")


def detect_scenes(path: Path, threshold: float = 0.35, min_gap: float = 0.6) -> list[float]:
    """Tiempos (s) de los cortes de plano detectados por cambio de imagen."""
    cmd = [
        ffmpeg_bin(), "-hide_banner", "-nostdin", "-i", str(path),
        "-vf", f"scale=320:-2,select='gt(scene,{threshold:.3f})',showinfo", "-an", "-f", "null", "-",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    cuts: list[float] = []
    for line in res.stderr.splitlines():
        if "showinfo" in line and "pts_time" in line:
            m = _PTS.search(line)
            if m:
                t = float(m.group(1))
                if not cuts or t - cuts[-1] >= min_gap:
                    cuts.append(round(t, 3))
    return cuts


def detect_beats(path: Path, max_seconds: float = 900) -> dict:
    """Pulsos y tempo aproximado (BPM) a partir del flujo de energía espectral."""
    sr = 22050
    cmd = [ffmpeg_bin(), "-v", "error", "-i", str(path), "-t", str(max_seconds), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, timeout=600).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    if x.size < sr:
        return {"bpm": None, "beats": [], "onsets": []}
    hop, win = 512, 2048
    n = 1 + (len(x) - win) // hop
    if n < 4:
        return {"bpm": None, "beats": [], "onsets": []}
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    frames = x[idx] * np.hanning(win)[None, :]
    mag = np.abs(np.fft.rfft(frames, axis=1))
    logmag = np.log1p(10 * mag)
    flux = np.maximum(0, np.diff(logmag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0], flux])
    flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    fps = sr / hop
    # tempo por autocorrelación del flujo (60–180 BPM)
    ac = np.correlate(flux, flux, mode="full")[len(flux) - 1:]
    lo, hi = int(fps * 60 / 180), int(fps * 60 / 60)
    hi = min(hi, len(ac) - 1)
    if hi <= lo:
        return {"bpm": None, "beats": [], "onsets": []}
    lag = lo + int(np.argmax(ac[lo:hi]))
    bpm = 60 * fps / lag
    # fase: el desplazamiento con más energía acumulada
    best_phase, best_score = 0, -1e9
    for ph in range(lag):
        score = flux[ph::lag].sum()
        if score > best_score:
            best_phase, best_score = ph, score
    beats = [round((best_phase + k * lag) / fps, 3) for k in range(int((len(flux) - best_phase) / lag) + 1)]
    # golpes fuertes (onsets) por picos locales
    thr = 1.5
    onsets = [round(i / fps, 3) for i in range(1, len(flux) - 1) if flux[i] > thr and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]]
    return {"bpm": round(float(bpm), 1), "beats": beats, "onsets": onsets}


_SRT_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def parse_srt(text: str) -> list[dict]:
    """Lee SRT (o WebVTT simple) → [{start, end, text}]."""
    items = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip())
    for b in blocks:
        lines = [ln for ln in b.split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            m = _SRT_TIME.search(ln)
            if m:
                g = [int(x) for x in m.groups()]
                start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / (10 ** len(m.group(4)))
                end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / (10 ** len(m.group(8)))
                txt = "\n".join(re.sub(r"<[^>]+>", "", x) for x in lines[i + 1:]).strip()
                if txt and end > start:
                    items.append({"start": start, "end": end, "text": txt})
                break
    return items

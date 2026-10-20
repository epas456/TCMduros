"""Compositor procedural de música (numpy): bandas sonoras ambientales por estado de ánimo.

Genera un WAV estéreo 48 kHz con pad, bajo, arpegio y percusión suave según el
estado de ánimo detectado en el prompt (épico, alegre, tenso, corporativo, triste,
misterioso, romántico, acción). Útil sin modelos y como guía temporal.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000

MOODS = {
    "epic": {"words": ["epic", "épic", "epica", "trailer", "heroic", "heroico", "batalla", "battle", "cine", "cinematic", "cinemat"], "key": 50, "minor": True, "prog": [0, 8, 3, 10], "bpm": 80, "drums": True, "arp": True},
    "happy": {"words": ["happy", "alegre", "feliz", "fun", "divertid", "summer", "verano", "kids", "niños"], "key": 60, "minor": False, "prog": [0, 7, 9, 5], "bpm": 112, "drums": True, "arp": True},
    "tense": {"words": ["tense", "tens", "suspense", "thriller", "horror", "terror", "miedo", "dark", "oscur"], "key": 45, "minor": True, "prog": [0, 1, 0, 6], "bpm": 70, "drums": False, "arp": False},
    "corporate": {"words": ["corporate", "corporativ", "business", "empresa", "tech", "tecnolog", "startup", "producto", "product", "anuncio", "ad "], "key": 57, "minor": False, "prog": [0, 5, 9, 7], "bpm": 104, "drums": True, "arp": True},
    "sad": {"words": ["sad", "triste", "melanc", "drama", "dramátic", "nostalg", "lluvia", "rain"], "key": 52, "minor": True, "prog": [0, 8, 5, 7], "bpm": 66, "drums": False, "arp": True},
    "mystery": {"words": ["mystery", "misteri", "space", "espacio", "sci-fi", "ciencia ficción", "noche", "night", "dream", "sueño", "ambient"], "key": 53, "minor": True, "prog": [0, 3, 10, 5], "bpm": 72, "drums": False, "arp": True},
    "romantic": {"words": ["romantic", "romántic", "romant", "love", "amor", "boda", "wedding", "tender", "tiern"], "key": 55, "minor": False, "prog": [0, 9, 5, 7], "bpm": 76, "drums": False, "arp": True},
    "action": {"words": ["action", "acción", "accion", "chase", "persecución", "sport", "deporte", "energ", "rápid", "fast"], "key": 52, "minor": True, "prog": [0, 10, 8, 10], "bpm": 128, "drums": True, "arp": True},
}


def detect_mood(prompt: str) -> str:
    low = prompt.lower()
    best, score = "mystery", 0
    for k, v in MOODS.items():
        s = sum(low.count(w) for w in v["words"])
        if s > score:
            best, score = k, s
    return best


def _midi(n: float) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def _env(n: int, a: float, r: float) -> np.ndarray:
    e = np.ones(n, dtype=np.float32)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na)
    if nr < n:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _saw(freq: float, n: int, rng, detune=0.004, voices=3) -> np.ndarray:
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    for v in range(voices):
        f = freq * (1 + (v - (voices - 1) / 2) * detune)
        ph = rng.random()
        out += (2 * ((t * f + ph) % 1) - 1).astype(np.float32)
    return out / voices


def _onepole(x: np.ndarray, cutoff: float) -> np.ndarray:
    """Paso bajo rápido por FFT (aproximación de un polo)."""
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    H = 1 / np.sqrt(1 + (f / cutoff) ** 2)
    return np.fft.irfft(X * H, n).astype(np.float32)


def _reverb(x: np.ndarray, mix: float = 0.3) -> np.ndarray:
    out = x.copy()
    for d, g in ((1557, 0.62), (1617, 0.6), (1491, 0.58), (1422, 0.56), (2131, 0.5), (2797, 0.45)):
        delayed = np.zeros_like(x)
        delayed[d:] = x[:-d] * g
        # feedback aproximado con dos repeticiones
        delayed[2 * d:] += x[:-2 * d] * g * g
        delayed[3 * d:] += x[:-3 * d] * g ** 3
        out += delayed * mix / 3
    return out


def compose(prompt: str, duration: float, seed: int = 0) -> tuple[np.ndarray, str]:
    rng = np.random.default_rng(seed)
    mood_id = detect_mood(prompt)
    m = MOODS[mood_id]
    n = int(duration * SR)
    L = np.zeros(n, dtype=np.float32)
    R = np.zeros(n, dtype=np.float32)
    beat = 60 / m["bpm"]
    bar = beat * 4
    key = m["key"]
    third = 3 if m["minor"] else 4
    nb = int(np.ceil(duration / bar))
    for b in range(nb):
        root = key + m["prog"][b % len(m["prog"])]
        s = int(b * bar * SR)
        e = min(n, int((b + 1) * bar * SR) + int(0.8 * SR))
        ln = e - s
        if ln <= 0:
            continue
        # quinta/tercera relativa: acordes diatónicos aproximados
        chord = [root, root + third if (m["prog"][b % len(m["prog"])] in (0, 7, 5) or not m["minor"]) else root + 3, root + 7, root + 12]
        pad = np.zeros(ln, dtype=np.float32)
        for k, note in enumerate(chord):
            pad += _saw(_midi(note), ln, rng) * (0.22 if k else 0.28)
        pad = _onepole(pad, 900 + 600 * rng.random()) * _env(ln, 1.2, 1.0)
        L[s:e] += pad * 0.55
        R[s:e] += pad * 0.5
        # bajo
        bass = np.sin(2 * np.pi * _midi(root - 12) * np.arange(ln) / SR).astype(np.float32) * _env(ln, 0.05, 0.6)
        L[s:e] += bass * 0.35
        R[s:e] += bass * 0.35
        # arpegio
        if m["arp"]:
            step = beat / 2
            notes = [chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[1] + 12]
            for i in range(8):
                ps = s + int(i * step * SR)
                pl = int(step * SR * 1.5)
                if ps >= n:
                    break
                pl = min(pl, n - ps)
                t = np.arange(pl) / SR
                pluck = np.sin(2 * np.pi * _midi(notes[i % 4]) * t) * np.exp(-t * 6)
                pan = 0.5 + 0.35 * np.sin(i)
                L[ps:ps + pl] += (pluck * 0.12 * (1 - pan)).astype(np.float32)
                R[ps:ps + pl] += (pluck * 0.12 * pan).astype(np.float32)
        if m["drums"]:
            for i in range(4):
                ks = s + int(i * beat * SR)
                kl = min(int(0.35 * SR), n - ks)
                if kl <= 0:
                    break
                t = np.arange(kl) / SR
                kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-t * 30)) * t) * np.exp(-t * 9)
                L[ks:ks + kl] += (kick * 0.45).astype(np.float32)
                R[ks:ks + kl] += (kick * 0.45).astype(np.float32)
                if i % 2 == 1:
                    hl = min(int(0.2 * SR), n - ks)
                    noise = rng.normal(0, 1, hl) * np.exp(-np.arange(hl) / SR * 25)
                    snare = _onepole(noise.astype(np.float32), 5000) * 0.18
                    L[ks:ks + hl] += snare
                    R[ks:ks + hl] += snare
    if m["minor"] and mood_id in ("tense", "mystery"):
        drone = np.sin(2 * np.pi * _midi(key - 24) * np.arange(n) / SR).astype(np.float32) * 0.15
        L += drone
        R += drone
    L, R = _reverb(L, 0.35), _reverb(R, 0.35)
    # fundidos y normalización
    fade = min(int(2.0 * SR), n // 4)
    env = np.ones(n, dtype=np.float32)
    env[:fade // 2] = np.linspace(0, 1, fade // 2)
    env[-fade:] = np.linspace(1, 0, fade)
    st = np.stack([L * env, R * env], axis=1)
    peak = np.abs(st).max() or 1
    st = st / peak * 0.8
    return st, mood_id


def write_wav(path: Path, stereo: np.ndarray) -> Path:
    data = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    return path


def silence(path: Path, duration: float) -> Path:
    return write_wav(path, np.zeros((int(duration * SR), 2), dtype=np.float32))

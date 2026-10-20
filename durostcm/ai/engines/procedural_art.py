"""Generador procedural de fotogramas de concepto (sin GPU).

No es un modelo de difusión: interpreta el prompt (ES/EN) y compone una escena
estilizada (cielo, montañas, mar, ciudad, bosque, desierto, espacio, retrato o
producto) con luz atmosférica, para que todo el flujo de durosTCM funcione y se
pueda maquetar un storyboard en cualquier equipo. Con ComfyUI/diffusers instalados
se usa automáticamente un modelo fotorrealista en su lugar.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

KEYWORDS = {
    "portrait": ["portrait", "retrato", "person", "persona", "woman", "mujer", "man", "hombre", "face", "rostro", "cara",
                 "character", "personaje", "girl", "chica", "boy", "chico", "actor", "actriz", "model", "modelo", "warrior",
                 "guerrera", "guerrero", "detective", "doctor", "doctora", "astronaut", "astronauta", "king", "rey", "queen", "reina"],
    "product": ["product", "producto", "bottle", "botella", "perfume", "watch", "reloj", "phone", "móvil", "movil", "sneaker",
                "zapatilla", "can", "lata", "packshot", "cosmetic", "cosmético", "crema", "car", "coche"],
    "space": ["space", "espacio", "galaxy", "galaxia", "planet", "planeta", "nebula", "nebulosa", "cosmos", "orbit", "órbita"],
    "ocean": ["sea", "mar", "ocean", "océano", "oceano", "beach", "playa", "lake", "lago", "coast", "costa", "wave", "ola", "harbor", "puerto"],
    "city": ["city", "ciudad", "street", "calle", "neon", "neón", "cyberpunk", "skyline", "rascacielos", "urban", "urbano", "metropolis", "tokyo", "madrid", "barcelona", "new york"],
    "forest": ["forest", "bosque", "jungle", "selva", "tree", "árbol", "arbol", "woods", "pine", "pino", "garden", "jardín"],
    "desert": ["desert", "desierto", "dune", "duna", "sahara", "canyon", "cañón", "mars", "marte"],
    "mountain": ["mountain", "montaña", "montana", "peak", "cumbre", "valley", "valle", "landscape", "paisaje", "alps", "alpes", "snow", "nieve"],
    "interior": ["room", "habitación", "habitacion", "office", "oficina", "kitchen", "cocina", "studio", "estudio", "bar", "café", "cafe", "library", "biblioteca"],
}
TIME = {
    "night": ["night", "noche", "midnight", "medianoche", "moon", "luna", "stars", "estrellas", "neon", "neón"],
    "sunset": ["sunset", "atardecer", "golden hour", "hora dorada", "dusk", "anochecer", "ocaso"],
    "dawn": ["dawn", "amanecer", "sunrise", "alba", "morning", "mañana"],
    "storm": ["storm", "tormenta", "rain", "lluvia", "fog", "niebla", "mist", "bruma", "overcast", "nublado"],
}
PALETTES = {
    "day": [(110, 170, 235), (190, 220, 245), (250, 245, 230)],
    "sunset": [(40, 30, 90), (220, 90, 70), (255, 190, 110)],
    "dawn": [(70, 90, 160), (240, 160, 150), (255, 225, 190)],
    "night": [(5, 8, 25), (20, 30, 70), (60, 50, 110)],
    "storm": [(50, 58, 70), (95, 105, 118), (150, 158, 165)],
}


@dataclass
class SceneSpec:
    kind: str
    time: str
    seed: int
    warm: float
    neon: bool


def analyze(prompt: str, seed: int) -> SceneSpec:
    low = prompt.lower()
    scores = {k: sum(low.count(w) for w in ws) for k, ws in KEYWORDS.items()}
    kind = max(scores, key=lambda k: scores[k]) if any(scores.values()) else random.Random(seed).choice(
        ["mountain", "ocean", "city", "forest", "desert", "space"]
    )
    t = "day"
    for k, ws in TIME.items():
        if any(w in low for w in ws):
            t = k
            break
    warm = 0.3 if any(w in low for w in ("warm", "cálid", "calid", "gold", "dorad", "fire", "fuego")) else 0.0
    warm -= 0.3 if any(w in low for w in ("cold", "frío", "frio", "ice", "hielo", "blue", "azul")) else 0.0
    neon = any(w in low for w in ("neon", "neón", "cyberpunk", "synthwave"))
    return SceneSpec(kind, t, seed, warm, neon)


def _noise1d(n: int, rng: np.random.Generator, octaves: int = 5, smooth: float = 1.0) -> np.ndarray:
    out = np.zeros(n)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        pts = max(3, int(4 * (2 ** o) / smooth))
        ctrl = rng.random(pts + 1)
        xs = np.linspace(0, pts, n)
        i = np.floor(xs).astype(int).clip(0, pts - 1)
        f = xs - i
        f = f * f * (3 - 2 * f)
        out += amp * (ctrl[i] * (1 - f) + ctrl[i + 1] * f)
        total += amp
        amp *= 0.5
    return out / total


def _lerp(a, b, t):
    return a + (b - a) * t


def _sky(W: int, H: int, spec: SceneSpec) -> np.ndarray:
    pal = np.array(PALETTES.get(spec.time, PALETTES["day"]), dtype=np.float32)
    if spec.warm:
        pal = pal + np.array([40, 10, -30]) * spec.warm
    if spec.neon and spec.time == "night":
        pal[1] = [60, 20, 90]
        pal[2] = [200, 60, 160]
    y = np.linspace(0, 1, H)[:, None]
    top = pal[0][None, None, :]
    mid = pal[1][None, None, :]
    bot = pal[2][None, None, :]
    t1 = np.clip(y / 0.6, 0, 1)[..., None]
    t2 = np.clip((y - 0.6) / 0.4, 0, 1)[..., None]
    sky = np.where(y[..., None] < 0.6, _lerp(top, mid, t1), _lerp(mid, bot, t2))
    return np.broadcast_to(sky, (H, W, 3)).astype(np.float32).copy()


def _sun(img: np.ndarray, cx: float, cy: float, r: float, color, glow: float = 0.6) -> None:
    H, W, _ = img.shape
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    core = np.clip(1 - (d - r) / (r * 0.15), 0, 1)
    halo = np.exp(-(d / (r * 6)) ** 2) * glow
    c = np.array(color, dtype=np.float32)
    img += (core[..., None] * 0.9 + halo[..., None]) * (c - img * 0.3) * 0.8


def _stars(img: np.ndarray, rng: np.random.Generator, n: int) -> None:
    H, W, _ = img.shape
    ys = rng.integers(0, int(H * 0.7), n)
    xs = rng.integers(0, W, n)
    b = rng.random(n) * 200 + 55
    img[ys, xs] = np.maximum(img[ys, xs], b[:, None])


def _ridge(img: np.ndarray, rng, base: float, amp: float, color, haze, smooth=1.0, sharp=False) -> np.ndarray:
    H, W, _ = img.shape
    prof = _noise1d(W, rng, 6, smooth)
    if sharp:
        prof = 1 - np.abs(prof * 2 - 1)
    top = (base - amp * prof) * H
    yy = np.arange(H)[:, None]
    mask = (yy >= top[None, :]).astype(np.float32)
    mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), dtype=np.float32) / 255
    col = np.array(color, dtype=np.float32)
    shade = np.clip((yy - top[None, :]) / (H * 0.5), 0, 1)[..., None]
    layer = col[None, None, :] * (1 - 0.35 * shade)
    img[:] = img * (1 - mask[..., None]) + layer * mask[..., None]
    return top


def _city(img, rng, spec: SceneSpec):
    H, W, _ = img.shape
    x = 0
    layers = [(0.55, (25, 28, 45), 0.25), (0.62, (12, 14, 26), 0.6)]
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    del d
    for base, col, lit in layers:
        x = int(-rng.integers(0, 40))
        while x < W:
            bw = int(rng.integers(W // 40, W // 12))
            bh = int(H * (rng.random() * 0.35 + 0.12))
            top = int(H * base) - bh + int(H * 0.25)
            img[max(0, top):, max(0, x):min(W, x + bw)] = col
            if spec.time in ("night", "sunset", "storm") or spec.neon:
                wy = np.arange(max(0, top) + 6, H - 4, max(6, H // 90))
                wx = np.arange(max(0, x) + 4, min(W, x + bw) - 3, max(5, W // 220))
                for yy in wy:
                    for xx in wx:
                        if rng.random() < lit * 0.45:
                            c = (255, 210, 140) if not spec.neon or rng.random() < 0.6 else ((255, 60, 200) if rng.random() < 0.5 else (60, 220, 255))
                            img[yy:yy + max(2, H // 300), xx:xx + max(2, W // 500)] = c
            x += bw + int(rng.integers(0, W // 60))


def _trees(img, rng, base: float, color, density=0.03):
    H, W, _ = img.shape
    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(pil)
    n = int(W * density)
    for _ in range(n):
        x = rng.random() * W
        h = H * (0.12 + rng.random() * 0.25)
        y = H * base + rng.random() * H * 0.08
        w = h * (0.28 + rng.random() * 0.12)
        d.polygon([(x, y - h), (x - w / 2, y), (x + w / 2, y)], fill=tuple(int(c) for c in color))
    d.rectangle([0, int(H * base) + int(H * 0.05), W, H], fill=tuple(int(c) for c in color))
    img[:] = np.asarray(pil, dtype=np.float32)


def _water(img, horizon: int):
    H, W, _ = img.shape
    above = img[:horizon][::-1]
    n = min(H - horizon, above.shape[0])
    refl = above[:n] * 0.55 + np.array([10, 25, 40], dtype=np.float32) * 0.45
    yy = np.arange(n)[:, None]
    ripple = (np.sin(yy * 0.9 + np.arange(W)[None, :] * 0.02) * 0.08 + 0.92)[..., None]
    img[horizon:horizon + n] = refl * ripple
    img[horizon:horizon + 2] = img[horizon:horizon + 2] * 0.7 + 255 * 0.3


def _portrait(img, rng, spec: SceneSpec):
    H, W, _ = img.shape
    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(W / 60))
    # bokeh
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for _ in range(40):
        r = rng.random() * W * 0.04 + W * 0.01
        x, y = rng.random() * W, rng.random() * H * 0.8
        c = (255, 200, 140, int(30 + rng.random() * 50)) if spec.time != "night" else (120, 160, 255, int(30 + rng.random() * 60))
        d.ellipse([x - r, y - r, x + r, y + r], fill=c)
    pil = Image.alpha_composite(pil.convert("RGBA"), over.filter(ImageFilter.GaussianBlur(3)))
    # silueta de busto con luz de recorte
    sil = Image.new("L", (W, H), 0)
    s = ImageDraw.Draw(sil)
    cx = W * (0.5 + (rng.random() - 0.5) * 0.2)
    head_r = H * 0.16
    cy = H * 0.42
    s.ellipse([cx - head_r * 0.82, cy - head_r * 1.05, cx + head_r * 0.82, cy + head_r * 1.05], fill=255)
    s.rectangle([cx - head_r * 0.35, cy + head_r * 0.7, cx + head_r * 0.35, cy + head_r * 1.5], fill=255)
    s.ellipse([cx - head_r * 2.6, cy + head_r * 1.3, cx + head_r * 2.6, cy + head_r * 4.5], fill=255)
    sil = sil.filter(ImageFilter.GaussianBlur(2))
    body = Image.new("RGBA", (W, H), (18, 16, 20, 255))
    rim_col = (255, 190, 120) if spec.time in ("sunset", "day", "dawn") else (110, 170, 255)
    edge = sil.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(W / 300))
    edge = Image.eval(edge, lambda v: min(255, v * 4))
    rim = Image.new("RGBA", (W, H), rim_col + (0,))
    rim.putalpha(edge)
    pil.paste(body, (0, 0), sil)
    pil = Image.alpha_composite(pil, rim)
    img[:] = np.asarray(pil.convert("RGB"), dtype=np.float32)


def _product(img, rng, spec: SceneSpec):
    H, W, _ = img.shape
    yy = np.linspace(0, 1, H)[:, None, None]
    base = np.array([28, 30, 36], dtype=np.float32) if spec.time in ("night",) else np.array([210, 205, 200], dtype=np.float32)
    img[:] = base * (1.15 - 0.5 * yy)
    xx = np.linspace(-1, 1, W)[None, :, None]
    img += 60 * np.exp(-((xx) ** 2) / 0.15) * np.exp(-((yy - 0.35) ** 2) / 0.2)
    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(pil)
    cx, floor = W / 2, H * 0.78
    d.ellipse([cx - W * 0.22, floor - H * 0.04, cx + W * 0.22, floor + H * 0.04], fill=(0, 0, 0, 60))
    hue = rng.random()
    col = tuple(int(c) for c in (np.array([math.sin(hue * 6.28) * 0.5 + 0.5, math.sin(hue * 6.28 + 2) * 0.5 + 0.5, math.sin(hue * 6.28 + 4) * 0.5 + 0.5]) * 180 + 40))
    bw, bh = W * 0.09, H * 0.42
    d.rounded_rectangle([cx - bw, floor - bh, cx + bw, floor], radius=int(bw * 0.4), fill=col + (255,))
    d.rectangle([cx - bw * 0.35, floor - bh - H * 0.07, cx + bw * 0.35, floor - bh + 4], fill=(30, 30, 30, 255))
    d.rounded_rectangle([cx - bw * 0.7, floor - bh * 0.62, cx - bw * 0.45, floor - bh * 0.12], radius=6, fill=(255, 255, 255, 110))
    pil = pil.filter(ImageFilter.GaussianBlur(0.6))
    img[:] = np.asarray(pil.convert("RGB"), dtype=np.float32)


def _space(img, rng, spec: SceneSpec):
    H, W, _ = img.shape
    img[:] = np.array([4, 5, 14], dtype=np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for _ in range(3):
        cx, cy = rng.random() * W, rng.random() * H
        s = W * (0.15 + rng.random() * 0.3)
        c = np.array(rng.choice([[120, 60, 200], [40, 120, 220], [220, 70, 120], [60, 200, 180]]), dtype=np.float32)
        img += np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * s * s)))[..., None] * c * 0.7
    _stars(img, rng, int(W * H / 900))
    pr = H * (0.18 + rng.random() * 0.2)
    pcx, pcy = W * (0.25 + rng.random() * 0.5), H * (0.55 + rng.random() * 0.3)
    d = np.sqrt((xx - pcx) ** 2 + (yy - pcy) ** 2)
    m = np.clip((pr - d) / 2, 0, 1)
    light = np.clip(((xx - pcx) * -0.6 + (yy - pcy) * -0.8) / pr * 0.7 + 0.4, 0.05, 1)
    pcol = np.array(rng.choice([[200, 140, 90], [90, 140, 210], [180, 90, 70]]), dtype=np.float32)
    band = (np.sin((yy - pcy) / pr * 12) * 0.12 + 0.88)
    img[:] = img * (1 - m[..., None]) + (pcol * (light * band)[..., None]) * m[..., None]
    atm = np.exp(-((d - pr) / (pr * 0.06)) ** 2) * (d > pr * 0.9)
    img += atm[..., None] * np.array([120, 170, 255], dtype=np.float32) * 0.6


def _finish(img: np.ndarray, rng: np.random.Generator, grain: float = 6.0, vignette: float = 0.35) -> Image.Image:
    H, W, _ = img.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    v = ((xx / W - 0.5) ** 2 + (yy / H - 0.5) ** 2) * 2
    img *= (1 - vignette * v)[..., None]
    img += rng.normal(0, grain, (H, W, 1)).astype(np.float32)
    # curva fílmica suave
    x = np.clip(img / 255, 0, 1)
    x = x * x * (3 - 2 * x) * 0.35 + x * 0.65
    return Image.fromarray((x * 255).astype(np.uint8))


def generate(prompt: str, width: int, height: int, seed: int) -> Image.Image:
    """Compone una imagen de concepto a partir del prompt."""
    s = int(hashlib.sha1(f"{prompt}|{seed}".encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(s)
    spec = analyze(prompt, seed)
    # Se trabaja a resolución reducida y luego se escala (rápido en CPU)
    scale = min(1.0, 1280 / max(width, height))
    W, H = max(64, int(width * scale)), max(64, int(height * scale))
    img = _sky(W, H, spec)
    if spec.time == "night":
        _stars(img, rng, int(W * H / 1500))
    sun_col = {"sunset": (255, 170, 90), "dawn": (255, 210, 170), "night": (230, 235, 255), "storm": (200, 205, 210)}.get(spec.time, (255, 250, 230))
    horizon = int(H * (0.62 + rng.random() * 0.06))
    if spec.kind in ("mountain", "ocean", "desert", "forest", "city"):
        sx = W * (0.2 + rng.random() * 0.6)
        sy = H * (0.25 if spec.time in ("day", "night") else 0.5)
        _sun(img, sx, sy, H * (0.035 if spec.time != "night" else 0.03), sun_col, 0.5 if spec.time != "storm" else 0.15)
    if spec.kind == "mountain":
        haze = img[horizon - 5].mean(axis=0)
        for i, (b, a) in enumerate([(0.55, 0.25), (0.65, 0.22), (0.78, 0.2)]):
            t = (i + 1) / 4
            col = _lerp(haze, np.array([25, 30, 40]), t)
            _ridge(img, rng, b, a, col, haze, smooth=1 + i * 0.3, sharp=i == 0)
    elif spec.kind == "ocean":
        _ridge(img, rng, 0.62, 0.08, img[horizon - 3].mean(axis=0) * 0.6, None, smooth=1.5)
        _water(img, horizon)
    elif spec.kind == "city":
        _city(img, rng, spec)
        if rng.random() < 0.5:
            _water(img, int(H * 0.86))
    elif spec.kind == "forest":
        haze = img[horizon].mean(axis=0)
        _ridge(img, rng, 0.6, 0.12, _lerp(haze, np.array([30, 50, 40]), 0.4), haze, smooth=1.3)
        _trees(img, rng, 0.72, _lerp(haze, np.array([12, 30, 20]), 0.7), 0.02)
        _trees(img, rng, 0.85, (8, 18, 12), 0.015)
    elif spec.kind == "desert":
        sand = np.array([200, 150, 95]) if spec.time != "night" else np.array([60, 55, 80])
        for i, b in enumerate([0.62, 0.72, 0.84]):
            _ridge(img, rng, b, 0.1, sand * (1 - i * 0.15), None, smooth=2.5)
    elif spec.kind == "space":
        _space(img, rng, spec)
    elif spec.kind == "portrait":
        _ridge(img, rng, 0.7, 0.2, img[horizon].mean(axis=0) * 0.7, None, smooth=1.2)
        _portrait(img, rng, spec)
    elif spec.kind == "product":
        _product(img, rng, spec)
    elif spec.kind == "interior":
        img[:] = img * 0.35 + np.array([60, 45, 35], dtype=np.float32) * 0.65
        pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(pil)
        d.rectangle([W * 0.55, H * 0.15, W * 0.85, H * 0.6], fill=tuple(int(c) for c in _sky(4, 4, spec)[1, 1]))
        d.rectangle([0, H * 0.75, W, H], fill=(40, 28, 22))
        img[:] = np.asarray(pil, dtype=np.float32)
        _sun(img, W * 0.7, H * 0.38, H * 0.02, (255, 220, 180), 0.35)
    if spec.time == "storm":
        img[:] = img * 0.85 + 30
    out = _finish(img, rng, grain=5.0, vignette=0.4 if spec.kind != "product" else 0.2)
    if out.size != (width, height):
        out = out.resize((width, height), Image.LANCZOS)
    return out


def stylize(image: Image.Image, prompt: str, strength: float, seed: int) -> Image.Image:
    """Img2img procedural: mezcla la imagen con la atmósfera derivada del prompt."""
    w, h = image.size
    atmos = generate(prompt, w, h, seed).filter(ImageFilter.GaussianBlur(max(w, h) / 80))
    base = image.convert("RGB")
    s = min(0.85, max(0.0, strength)) * 0.6
    return Image.blend(base, atmos, s)

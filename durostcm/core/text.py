"""Rotulación: renderiza títulos y subtítulos a PNG con transparencia (Pillow)."""

from __future__ import annotations

import functools
import hashlib
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import get_config
from .project import TextStyle

FONT_EXT = {".ttf", ".otf", ".ttc"}


def _font_dirs() -> list[Path]:
    dirs = [get_config().fonts_dir, Path(__file__).resolve().parent.parent / "assets" / "fonts"]
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", "C:/Windows")
        dirs += [Path(windir) / "Fonts", Path.home() / "AppData/Local/Microsoft/Windows/Fonts"]
    elif sys.platform == "darwin":
        dirs += [Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library/Fonts"]
    else:
        dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts", Path.home() / ".local/share/fonts"]
    return [d for d in dirs if d.exists()]


@functools.lru_cache(maxsize=1)
def _font_index() -> dict[str, dict[str, Path]]:
    """{familia_normalizada: {"regular": ruta, "bold": ruta}}"""
    idx: dict[str, dict[str, Path]] = {}
    for d in _font_dirs():
        for root, _dirs, files in os.walk(d):
            for f in files:
                p = Path(root) / f
                if p.suffix.lower() not in FONT_EXT:
                    continue
                stem = p.stem
                low = stem.lower().replace("_", "-")
                weight = "bold" if ("bold" in low or "black" in low or "heavy" in low) else "regular"
                if any(x in low for x in ("italic", "oblique", "thin", "light", "extralight", "condensed")) and weight == "regular":
                    weight = "other"
                fam = low.split("-")[0].replace(" ", "")
                for suffix in ("bold", "regular", "black", "heavy", "medium", "semibold"):
                    if fam.endswith(suffix) and fam != suffix:
                        fam = fam[: -len(suffix)]
                entry = idx.setdefault(fam, {})
                entry.setdefault(weight, p)
    return idx


def list_fonts() -> list[str]:
    names = sorted({k for k, v in _font_index().items() if "regular" in v or "bold" in v})
    return names


def font_path(name: str, weight: str = "normal") -> Path | None:
    idx = _font_index()
    key = name.lower().replace(" ", "").replace("_", "").replace("-", "")
    entry = idx.get(key)
    if entry is None:
        for k, v in idx.items():
            if k.startswith(key) or key.startswith(k):
                entry = v
                break
    if entry is None:
        for fallback in ("inter", "dejavusans", "arial", "helvetica", "liberationsans", "freesans", "roboto"):
            if fallback in idx:
                entry = idx[fallback]
                break
    if entry is None:
        return None
    want = "bold" if weight == "bold" else "regular"
    return entry.get(want) or entry.get("regular") or entry.get("bold") or next(iter(entry.values()))


def load_font(name: str, size: int, weight: str = "normal") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    p = font_path(name, weight)
    if p is not None:
        try:
            return ImageFont.truetype(str(p), size=size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow antiguo
        return ImageFont.load_default()


def parse_color(c: str | None, default=(255, 255, 255, 255)) -> tuple[int, int, int, int]:
    if not c:
        return default
    c = c.strip().lstrip("#")
    try:
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        if len(c) == 6:
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255
        if len(c) == 8:
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), int(c[6:8], 16)
    except ValueError:
        pass
    return default


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: float, spacing: float) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if _text_w(draw, test, font, spacing) <= max_w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def _text_w(draw, s: str, font, spacing: float) -> float:
    if not s:
        return 0
    if spacing:
        return sum(draw.textlength(ch, font=font) for ch in s) + spacing * (len(s) - 1)
    return draw.textlength(s, font=font)


def render_text(style: TextStyle, canvas_w: int, canvas_h: int, out: Path, reveal_chars: int | None = None) -> tuple[Path, int, int]:
    """Renderiza el bloque de texto (tamaño ajustado) en PNG RGBA. Devuelve (ruta, ancho, alto)."""
    size = max(8, int(style.size * canvas_h))
    font = load_font(style.font, size, style.weight)
    text = style.content.upper() if style.uppercase else style.content
    scratch = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    spacing = style.letter_spacing * size
    max_w = style.max_width * canvas_w
    lines = _wrap(scratch, text, font, max_w, spacing)
    if reveal_chars is not None:
        remaining = reveal_chars
        cut: list[str] = []
        for ln in lines:
            if remaining <= 0:
                cut.append("")
                continue
            cut.append(ln[:remaining])
            remaining -= len(ln) + 1
        visible = cut
    else:
        visible = lines
    ascent, descent = font.getmetrics() if hasattr(font, "getmetrics") else (size, size // 4)
    line_h = int((ascent + descent) * style.line_spacing)
    block_w = int(max((_text_w(scratch, ln, font, spacing) for ln in lines), default=0))
    block_h = line_h * len(lines)
    stroke = int(style.stroke_width * size)
    pad = int(size * 0.35) + stroke + (int(size * 0.12) if style.shadow else 0)
    W, H = max(2, block_w + pad * 2), max(2, block_h + pad * 2)
    W += W % 2
    H += H % 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if style.background:
        bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(bg).rounded_rectangle([0, 0, W - 1, H - 1], radius=int(size * 0.25), fill=parse_color(style.background))
        img = Image.alpha_composite(img, bg)
    color = parse_color(style.color)
    stroke_col = parse_color(style.stroke_color, (0, 0, 0, 255))

    def draw_lines(d: ImageDraw.ImageDraw, fill, dx=0, dy=0, with_stroke=True):
        for i, ln in enumerate(visible):
            lw = _text_w(d, lines[i] if i < len(lines) else ln, font, spacing)
            if style.align == "left":
                x = pad
            elif style.align == "right":
                x = W - pad - lw
            else:
                x = (W - lw) / 2
            y = pad + i * line_h
            if spacing:
                cx = x
                for ch in ln:
                    d.text((cx + dx, y + dy), ch, font=font, fill=fill, stroke_width=stroke if with_stroke else 0, stroke_fill=stroke_col)
                    cx += d.textlength(ch, font=font) + spacing
            else:
                d.text((x + dx, y + dy), ln, font=font, fill=fill, stroke_width=stroke if with_stroke else 0, stroke_fill=stroke_col)

    if style.shadow:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        off = max(1, int(size * 0.05))
        draw_lines(ImageDraw.Draw(sh), (0, 0, 0, 170), off, off)
        sh = sh.filter(ImageFilter.GaussianBlur(max(1, size * 0.06)))
        img = Image.alpha_composite(img, sh)
    draw_lines(ImageDraw.Draw(img), color)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=False, compress_level=1)
    return out, W, H


def style_hash(style: TextStyle, w: int, h: int) -> str:
    return hashlib.sha1(f"{style.model_dump_json()}|{w}x{h}".encode()).hexdigest()[:16]


def render_typewriter_frames(style: TextStyle, canvas_w: int, canvas_h: int, folder: Path, fps: float, reveal_seconds: float) -> tuple[Path, int, int, int]:
    """Secuencia PNG con el texto apareciendo letra a letra. Devuelve (patrón, w, h, nº frames)."""
    folder.mkdir(parents=True, exist_ok=True)
    total_chars = len(style.content)
    frames = max(1, int(reveal_seconds * fps))
    w = h = 0
    for i in range(frames + 1):
        n = int(round(total_chars * i / frames))
        _p, w, h = render_text(style, canvas_w, canvas_h, folder / f"f_{i:05d}.png", reveal_chars=n)
    return folder / "f_%05d.png", w, h, frames + 1

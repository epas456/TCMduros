"""Etalonaje: looks cinematográficos predefinidos y traducción de ColorGrade a filtros FFmpeg."""

from __future__ import annotations

from typing import Callable

from .project import ColorGrade

# Cada look es un parche de ColorGrade + filtros extra opcionales.
LOOKS: dict[str, dict] = {
    "teal_orange": {
        "label": "Teal & Orange (blockbuster)",
        "grade": {"contrast": 1.12, "saturation": 1.15},
        "extra": "colorbalance=rs=-0.08:gs=0.02:bs=0.12:rh=0.10:gh=0.02:bh=-0.10",
    },
    "bleach_bypass": {
        "label": "Bleach bypass (bélico, duro)",
        "grade": {"contrast": 1.35, "saturation": 0.55, "highlights": 0.1},
        "extra": "",
    },
    "noir": {"label": "Noir B/N contrastado", "grade": {"contrast": 1.4, "saturation": 0.0, "vignette": 0.45}, "extra": ""},
    "warm_film": {
        "label": "Película cálida (Kodak 5219 aprox.)",
        "grade": {"temperature": 0.35, "contrast": 1.08, "grain": 0.18, "shadows": 0.05},
        "extra": "curves=preset=medium_contrast",
    },
    "cold_thriller": {
        "label": "Thriller frío (Fincher)",
        "grade": {"temperature": -0.3, "tint": -0.15, "saturation": 0.8, "contrast": 1.15},
        "extra": "",
    },
    "vintage": {"label": "Vintage 70s", "grade": {"saturation": 0.85, "grain": 0.25, "vignette": 0.3}, "extra": "curves=preset=vintage"},
    "cross_process": {"label": "Proceso cruzado", "grade": {"saturation": 1.1}, "extra": "curves=preset=cross_process"},
    "pastel_dream": {
        "label": "Pastel onírico (Wes Anderson)",
        "grade": {"saturation": 0.9, "contrast": 0.9, "shadows": 0.15, "temperature": 0.15},
        "extra": "",
    },
    "neon_night": {
        "label": "Noche neón (cyberpunk)",
        "grade": {"contrast": 1.2, "saturation": 1.35, "tint": 0.2},
        "extra": "colorbalance=rs=0.05:bs=0.15:rh=0.08:bh=0.06",
    },
    "golden_hour": {"label": "Hora dorada", "grade": {"temperature": 0.5, "saturation": 1.1, "highlights": 0.08}, "extra": ""},
    "matrix": {"label": "Verde digital", "grade": {"tint": -0.45, "contrast": 1.2, "saturation": 0.8}, "extra": ""},
    "documentary": {"label": "Documental natural", "grade": {"contrast": 1.05, "saturation": 0.95, "sharpen": 0.15}, "extra": ""},
    "commercial_pop": {"label": "Anuncio pop (vibrante)", "grade": {"contrast": 1.1, "saturation": 1.3, "sharpen": 0.25}, "extra": ""},
    "horror": {"label": "Terror desaturado", "grade": {"saturation": 0.45, "tint": -0.1, "vignette": 0.6, "contrast": 1.25}, "extra": ""},
}


def effective_grade(cg: ColorGrade) -> tuple[ColorGrade, str]:
    """Combina el look elegido con los ajustes manuales (los manuales mandan si no son neutros)."""
    if not cg.look or cg.look not in LOOKS:
        return cg, ""
    look = LOOKS[cg.look]
    neutral = ColorGrade()
    data = cg.model_dump()
    for k, v in look["grade"].items():
        if data.get(k) == getattr(neutral, k):
            data[k] = v
    return ColorGrade.model_validate(data), look["extra"]


def grade_filters(
    cg: ColorGrade, lut_resolver: Callable[[str], str | None] | None = None, enable: str | None = None
) -> list[str]:
    """Lista de filtros FFmpeg (sin etiquetas) para aplicar un ColorGrade.

    ``lut_resolver`` recibe el nombre del LUT y devuelve la ruta (relativa al directorio de
    trabajo de FFmpeg, sin caracteres especiales) o None si no existe.
    ``enable`` permite aplicarlos sólo en un rango de tiempo (capas de ajuste).
    """
    g, extra = effective_grade(cg)
    en = f":enable='{enable}'" if enable else ""
    out: list[str] = []
    if abs(g.exposure) > 1e-3:
        f = 2 ** abs(g.exposure)
        if g.exposure > 0:
            m = max(0.05, 1 / f)
            out.append(f"colorlevels=rimax={m:.4f}:gimax={m:.4f}:bimax={m:.4f}{en}")
        else:
            m = max(0.05, 1 / f)
            out.append(f"colorlevels=romax={m:.4f}:gomax={m:.4f}:bomax={m:.4f}{en}")
    if abs(g.contrast - 1) > 1e-3 or abs(g.saturation - 1) > 1e-3 or abs(g.gamma - 1) > 1e-3:
        out.append(f"eq=contrast={g.contrast:.4f}:saturation={g.saturation:.4f}:gamma={g.gamma:.4f}{en}")
    if abs(g.temperature) > 1e-3 or abs(g.tint) > 1e-3:
        t, ti = g.temperature, g.tint
        out.append(
            "colorbalance="
            f"rs={0.06 * t:.4f}:bs={-0.06 * t:.4f}:rm={0.10 * t:.4f}:bm={-0.10 * t:.4f}:"
            f"rh={0.05 * t:.4f}:bh={-0.05 * t:.4f}:gm={-0.10 * ti:.4f}:gs={-0.05 * ti:.4f}{en}"
        )
    if abs(g.shadows) > 1e-3 or abs(g.highlights) > 1e-3:
        s = min(0.24, max(-0.24, 0.12 * g.shadows))
        h = min(0.24, max(-0.24, 0.12 * g.highlights))
        out.append(f"curves=all='0/0 0.25/{0.25 + s:.4f} 0.75/{0.75 + h:.4f} 1/1'{en}")
    if extra:
        out.extend(f"{x}{en}" for x in extra.split(";") if x)
    if g.lut and lut_resolver is not None:
        ref = lut_resolver(g.lut)
        if ref:
            if g.lut_intensity >= 0.999 or enable:
                out.append(f"lut3d=file={ref}{en}")
            elif g.lut_intensity > 0.001:
                out.append(
                    "@graph:[{in}]split[{u}a][{u}b];[{u}b]lut3d=file=%s[{u}c];"
                    "[{u}a][{u}c]blend=all_mode=normal:all_opacity=%.3f[{out}]" % (ref, g.lut_intensity)
                )
    if g.sharpen > 1e-3:
        out.append(f"unsharp=5:5:{min(2.5, g.sharpen * 2):.3f}:5:5:0{en}")
    if g.blur > 1e-3:
        out.append(f"gblur=sigma={g.blur * 20:.3f}{en}")
    if g.vignette > 1e-3:
        out.append(f"vignette=angle={0.15 + g.vignette * 0.85:.4f}{en}")
    if g.grain > 1e-3:
        out.append(f"noise=c0s={int(4 + g.grain * 30)}:c0f=t+u{en}")
    return out


def list_looks() -> list[dict]:
    return [{"id": k, "label": v["label"], "grade": v["grade"]} for k, v in LOOKS.items()]


# --------------------------------------------------------------------- efectos
def effect_filters(effect_type: str, params: dict) -> list[str]:
    p = params or {}
    if effect_type == "chroma_key":
        color = str(p.get("color", "#00FF00")).replace("#", "0x")
        sim = float(p.get("similarity", 0.12))
        blend = float(p.get("blend", 0.06))
        return ["format=yuva420p", f"chromakey=color={color}:similarity={sim:.3f}:blend={blend:.3f}", "despill=type=green" if p.get("despill", True) else "null"]
    if effect_type == "bw":
        return ["hue=s=0"]
    if effect_type == "sepia":
        return ["colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131"]
    if effect_type == "invert":
        return ["negate"]
    if effect_type == "mirror":
        return ["hflip"]
    if effect_type == "pixelate":
        n = max(2, int(p.get("size", 16)))
        return [f"pixelize=width={n}:height={n}"]
    if effect_type == "glow":
        s = float(p.get("strength", 0.4))
        sigma = float(p.get("radius", 18))
        # subgrafo: {in}/{out}/{u} los sustituye render.py
        return [
            "@graph:[{in}]format=gbrap,split[{u}a][{u}b];[{u}b]gblur=sigma=%.2f[{u}c];"
            "[{u}a][{u}c]blend=all_mode=screen:all_opacity=%.3f[{out}]" % (sigma, s)
        ]
    if effect_type == "chromatic_aberration":
        n = int(p.get("amount", 4))
        return [f"rgbashift=rh=-{n}:bh={n}"]
    if effect_type == "vhs":
        return ["rgbashift=rh=-3:bh=3", "noise=c0s=18:c0f=t", "eq=saturation=1.3:contrast=1.1", "gblur=sigma=0.6"]
    if effect_type == "old_film":
        return ["colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131", "noise=c0s=28:c0f=t+u", "vignette=angle=0.9", "eq=brightness='0.03*sin(40*t)':eval=frame"]
    if effect_type == "denoise":
        s = float(p.get("strength", 4))
        return [f"hqdn3d={s:.2f}:{s * 0.75:.2f}:{s * 1.5:.2f}:{s * 1.1:.2f}"]
    if effect_type == "stabilize":
        return ["deshake"]
    if effect_type == "letterbox":
        ratio = float(p.get("ratio", 2.39))
        return [
            f"drawbox=x=0:y=0:w=iw:h='max(0,(ih-iw/{ratio:.4f})/2)':color=black:t=fill",
            f"drawbox=x=0:y='ih-max(0,(ih-iw/{ratio:.4f})/2)':w=iw:h='max(0,(ih-iw/{ratio:.4f})/2)':color=black:t=fill",
        ]
    if effect_type == "lens_distortion":
        k = float(p.get("amount", -0.1))
        return [f"lenscorrection=k1={k:.3f}:k2={k / 2:.3f}"]
    if effect_type == "flicker":
        return ["eq=brightness='0.04*sin(55*t)':eval=frame"]
    return []


EFFECTS = [
    {"id": "chroma_key", "label": "Croma (pantalla verde)", "params": {"color": "#00FF00", "similarity": 0.12, "blend": 0.06}},
    {"id": "bw", "label": "Blanco y negro", "params": {}},
    {"id": "sepia", "label": "Sepia", "params": {}},
    {"id": "glow", "label": "Resplandor (glow)", "params": {"strength": 0.4, "radius": 18}},
    {"id": "chromatic_aberration", "label": "Aberración cromática", "params": {"amount": 4}},
    {"id": "vhs", "label": "VHS retro", "params": {}},
    {"id": "old_film", "label": "Película antigua", "params": {}},
    {"id": "denoise", "label": "Reducción de ruido", "params": {"strength": 4}},
    {"id": "stabilize", "label": "Estabilizar", "params": {}},
    {"id": "letterbox", "label": "Bandas cinemascope", "params": {"ratio": 2.39}},
    {"id": "lens_distortion", "label": "Distorsión de lente", "params": {"amount": -0.1}},
    {"id": "pixelate", "label": "Pixelar / censurar", "params": {"size": 16}},
    {"id": "mirror", "label": "Espejo", "params": {}},
    {"id": "invert", "label": "Invertir", "params": {}},
    {"id": "flicker", "label": "Parpadeo", "params": {}},
]

# --------------------------------------------------------------------- efectos de audio
def audio_effect_filters(effect_type: str, params: dict) -> list[str]:
    p = params or {}
    if effect_type == "voice_enhance":
        return ["highpass=f=80", "lowpass=f=14000", "afftdn=nf=-25", "equalizer=f=3000:t=q:w=1.2:g=3",
                "acompressor=threshold=-18dB:ratio=3:attack=10:release=150:makeup=2"]
    if effect_type == "denoise_audio":
        return [f"afftdn=nf={-abs(float(p.get('strength', 25))):.1f}"]
    if effect_type == "echo":
        d = int(p.get("delay_ms", 250))
        return [f"aecho=0.8:0.6:{d}:{float(p.get('decay', 0.4)):.2f}"]
    if effect_type == "reverb":
        return ["aecho=0.8:0.72:40|80|130|190:0.45|0.35|0.25|0.15"]
    if effect_type == "radio":
        return ["highpass=f=400", "lowpass=f=3400", "acompressor=threshold=-20dB:ratio=6:makeup=4"]
    if effect_type == "phone":
        return ["highpass=f=600", "lowpass=f=3000", "acrusher=bits=10:mix=0.3"]
    if effect_type == "bass_boost":
        return [f"bass=g={float(p.get('gain', 6)):.1f}"]
    if effect_type == "pitch":
        st = float(p.get("semitones", 3))
        r = 2 ** (st / 12)
        return [f"asetrate=48000*{r:.5f}", "aresample=48000", f"atempo={1 / r:.5f}"]
    if effect_type == "limiter":
        return ["alimiter=limit=0.9"]
    return []


AUDIO_EFFECTS = [
    {"id": "voice_enhance", "label": "Mejorar voz (limpieza + presencia + compresión)", "params": {}},
    {"id": "denoise_audio", "label": "Reducción de ruido", "params": {"strength": 25}},
    {"id": "reverb", "label": "Reverberación", "params": {}},
    {"id": "echo", "label": "Eco", "params": {"delay_ms": 250, "decay": 0.4}},
    {"id": "radio", "label": "Radio / walkie", "params": {}},
    {"id": "phone", "label": "Teléfono", "params": {}},
    {"id": "bass_boost", "label": "Realce de graves", "params": {"gain": 6}},
    {"id": "pitch", "label": "Cambiar tono (semitonos)", "params": {"semitones": 3}},
    {"id": "limiter", "label": "Limitador", "params": {}},
]
AUDIO_EFFECT_IDS = {e["id"] for e in AUDIO_EFFECTS}

# Transiciones disponibles en xfade (FFmpeg 6+)
TRANSITIONS = [
    "fade", "dissolve", "fadeblack", "fadewhite", "fadegrays", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown", "smoothleft", "smoothright", "smoothup", "smoothdown",
    "circlecrop", "circleopen", "circleclose", "rectcrop", "radial", "pixelize", "distance", "hblur",
    "diagtl", "diagtr", "diagbl", "diagbr", "hlslice", "hrslice", "vuslice", "vdslice", "squeezeh", "squeezev",
    "zoomin", "horzopen", "horzclose", "vertopen", "vertclose", "coverleft", "coverright", "revealleft", "revealright",
]

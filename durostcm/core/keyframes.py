"""Interpolación de keyframes y conversión a expresiones de FFmpeg."""

from __future__ import annotations

from .project import Keyframe


def _ease(p: float, easing: str) -> float:
    if easing == "ease_in":
        return p * p
    if easing == "ease_out":
        return 1 - (1 - p) * (1 - p)
    if easing == "ease_in_out":
        return p * p * (3 - 2 * p)
    if easing == "hold":
        return 0.0
    return p


def value_at(kfs: list[Keyframe], t: float, default: float) -> float:
    """Valor interpolado en ``t`` (segundos desde el inicio del clip)."""
    if not kfs:
        return default
    ks = sorted(kfs, key=lambda k: k.t)
    if t <= ks[0].t:
        return ks[0].value
    if t >= ks[-1].t:
        return ks[-1].value
    for a, b in zip(ks, ks[1:]):
        if a.t <= t <= b.t:
            span = max(1e-6, b.t - a.t)
            p = _ease((t - a.t) / span, a.easing)
            return a.value + (b.value - a.value) * p
    return default


def _ease_expr(p: str, easing: str) -> str:
    if easing == "ease_in":
        return f"({p})*({p})"
    if easing == "ease_out":
        return f"(1-(1-({p}))*(1-({p})))"
    if easing == "ease_in_out":
        return f"(({p})*({p})*(3-2*({p})))"
    if easing == "hold":
        return "0"
    return f"({p})"


def expr(kfs: list[Keyframe], default: float, var: str = "t", scale: float = 1.0, offset: float = 0.0) -> str:
    """Expresión FFmpeg por tramos: ``offset + scale * valor(t)``.

    El resultado va entre comillas simples en el filtergraph, así que puede llevar comas.
    """
    if not kfs:
        return f"{offset + scale * default:.6f}"
    ks = sorted(kfs, key=lambda k: k.t)

    def lin(v: float) -> str:
        return f"{offset + scale * v:.6f}"

    if len(ks) == 1:
        return lin(ks[0].value)
    # Construimos de atrás hacia delante: if(lt(t,t1), seg0, if(lt(t,t2), seg1, ... last))
    out = lin(ks[-1].value)
    for i in range(len(ks) - 2, -1, -1):
        a, b = ks[i], ks[i + 1]
        span = max(1e-6, b.t - a.t)
        p = f"(({var})-{a.t:.6f})/{span:.6f}"
        e = _ease_expr(p, a.easing)
        seg = f"({lin(a.value)}+({lin(b.value)}-{lin(a.value)})*{e})"
        out = f"if(lt({var},{b.t:.6f}),{seg},{out})"
    return f"if(lt({var},{ks[0].t:.6f}),{lin(ks[0].value)},{out})"


def sample(kfs: list[Keyframe], default: float, duration: float, fps: float, step: int = 1) -> list[tuple[float, float]]:
    """Muestras (t, valor) cada ``step`` frames, para comandos ``sendcmd``."""
    out = []
    n = int(duration * fps) + 1
    for i in range(0, n, step):
        t = i / fps
        out.append((t, value_at(kfs, t, default)))
    return out

"""Motor de render: convierte la línea de tiempo en un filtergraph de FFmpeg.

Arquitectura del grafo
----------------------
1. Cada clip visual se normaliza a un flujo del tamaño del lienzo de composición, con
   canal alfa, a los fps de salida y con su duración exacta (recorte, velocidad, marcha
   atrás, movimiento de cámara virtual, etalonaje, efectos, transformaciones, fundidos).
2. Los clips consecutivos de una pista unidos por transición forman una *cadena*
   que se monta con ``xfade``.
3. Las cadenas se superponen (``overlay``) sobre el fondo en el orden de las pistas,
   desplazadas a su posición temporal. Las capas de ajuste se aplican al acumulado.
4. Audio: cada clip con sonido se recorta, cambia de tempo, se ajusta de volumen/fundidos
   y se retrasa a su posición; luego se mezcla y opcionalmente se normaliza (EBU R128).
5. Post: reencuadre a la relación de aspecto de salida, marca "IA", códec y metadatos.
"""

from __future__ import annotations

import asyncio
import json
import math
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .. import APP_NAME, __version__
from ..config import get_config
from . import keyframes as kf
from .ffmpeg import filter_script_args, run_ffmpeg
from .looks import effect_filters, grade_filters
from .presets import FormatPreset, get_format
from .project import Clip, MediaItem, Project, Track
from .storage import ProjectStore
from .text import parse_color, render_text, render_typewriter_frames


class RenderSettings(BaseModel):
    format: str = "mp4_h264"
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    quality: Literal["draft", "good", "high", "master"] = "high"
    start: float = 0.0
    end: float | None = None
    reframe: Literal["fit", "fill", "blur_fill", "stretch"] = "blur_fill"
    loudness: float | None = None  # LUFS objetivo (-14 web, -23 EBU, -27 cine)
    include_audio: bool = True
    include_video: bool = True
    ai_watermark: bool | None = None
    ai_metadata: bool | None = None
    transparent: bool = False
    filename: str | None = None
    preview: bool = False
    title: str = ""
    author: str = ""
    copyright: str = ""
    subtitles_sidecar: bool = True


@dataclass
class _Member:
    clip: Clip
    track: Track
    start: float
    dur: float
    extend: float = 0.0  # congelar último fotograma (transición sin solape)
    xfade: tuple[str, float] | None = None  # (tipo, duración) respecto al miembro anterior


@dataclass
class _Chain:
    members: list[_Member] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.members[0].start

    @property
    def end(self) -> float:
        m = self.members[-1]
        return m.start + m.dur


def fps_str(fps: float) -> str:
    for nominal in (24, 30, 60, 120):
        if abs(fps - nominal * 1000 / 1001) < 0.005:
            return f"{nominal * 1000}/1001"
    if abs(fps - round(fps)) < 1e-6:
        return str(int(round(fps)))
    return f"{fps:.6f}"


def _even(v: float) -> int:
    n = max(2, int(round(v)))
    return n - (n % 2)


class _Graph:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.k = 0

    def tmp(self, p: str = "s") -> str:
        self.k += 1
        return f"{p}{self.k}"

    def add(self, inputs: list[str], filters: list[str], out: str | None = None, audio: bool = False) -> str:
        out = out or self.tmp()
        cur = list(inputs)
        buf: list[str] = []

        def flush(dst: str) -> None:
            nonlocal cur, buf
            chain = ",".join(buf) if buf else ("anull" if audio else "null")
            self.lines.append("".join(f"[{i}]" for i in cur) + chain + f"[{dst}]")
            cur, buf = [dst], []

        for f in filters:
            if not f:
                continue
            if f.startswith("@graph:"):
                if buf or len(cur) != 1:
                    flush(self.tmp())
                dst = self.tmp()
                tpl = f[len("@graph:"):]
                self.lines.append(tpl.replace("{in}", cur[0]).replace("{out}", dst).replace("{u}", self.tmp("g")))
                cur = [dst]
            else:
                buf.append(f)
        if buf or cur != [out]:
            if not buf and len(cur) == 1:
                # renombrar sin filtros
                self.lines.append(f"[{cur[0]}]{'anull' if audio else 'null'}[{out}]")
            else:
                flush(out)
        return out

    def raw(self, line: str) -> None:
        self.lines.append(line)

    def script(self) -> str:
        return ";\n".join(self.lines)


class Renderer:
    def __init__(self, store: ProjectStore, project: Project, settings: RenderSettings, workdir: Path):
        self.store = store
        self.p = project
        self.s = settings
        self.work = workdir
        self.work.mkdir(parents=True, exist_ok=True)
        self.cfg = get_config()
        self.fmt: FormatPreset = get_format(settings.format)
        self.inputs: list[list[str]] = []
        self.g = _Graph()
        self._lut_n = 0
        self._luts: dict[str, str] = {}
        self._cmd_n = 0
        self.warnings: list[str] = []

        ps = project.settings
        self.fps = float(settings.fps or ps.fps)
        if settings.preview:
            self.fps = min(self.fps, 30.0)
        self.fps_s = fps_str(self.fps)
        out_w = settings.width or ps.width
        out_h = settings.height or ps.height
        if settings.preview:
            scale = min(1.0, 540 / max(1, out_h))
            out_w, out_h = out_w * scale, out_h * scale
        self.OW, self.OH = _even(out_w), _even(out_h)
        pa = ps.width / ps.height
        oa = self.OW / self.OH
        if abs(pa - oa) / oa < 0.005 or settings.reframe == "stretch":
            self.CW, self.CH = self.OW, self.OH
            self.post = "none" if settings.reframe != "stretch" or abs(pa - oa) / oa < 0.005 else "none"
        else:
            if settings.reframe == "fill":
                k = max(self.OW / ps.width, self.OH / ps.height)
            else:
                k = min(self.OW / ps.width, self.OH / ps.height)
            self.CW, self.CH = _even(ps.width * k), _even(ps.height * k)
            self.post = settings.reframe
        self.k = self.CW / ps.width  # píxeles de composición por píxel de proyecto
        self.alpha_out = (self.fmt.alpha and settings.transparent)
        hi = (self.fmt.pix_fmt or "").startswith(("yuv422", "yuv444", "yuva444", "rgba64"))
        self.comp_fmt = "yuva444p" if hi else "yuva420p"
        self.start = max(0.0, settings.start)
        end = settings.end if settings.end is not None else project.duration
        self.end = max(self.start + 1 / self.fps, end if end > self.start else self.start + 1.0)
        self.D = self.end - self.start

    # ------------------------------------------------------------ utilidades
    def _input(self, args: list[str]) -> int:
        self.inputs.append(args)
        return len(self.inputs) - 1

    def _media_path(self, m: MediaItem) -> Path:
        return self.store.resolve(self.p.id, m.path)

    def _lut(self, name: str) -> str | None:
        if name in self._luts:
            return self._luts[name]
        src = (self.cfg.luts_dir / name).resolve()
        if not src.exists() or self.cfg.luts_dir.resolve() not in src.parents:
            self.warnings.append(f"LUT no encontrado: {name}")
            return None
        self._lut_n += 1
        ref = f"lut_{self._lut_n}{src.suffix.lower()}"
        shutil.copy2(src, self.work / ref)
        self._luts[name] = ref
        return ref

    def _sendcmd(self, target: str, param: str, samples: list[tuple[float, float]]) -> str:
        self._cmd_n += 1
        name = f"cmd_{self._cmd_n}.txt"
        lines = [f"{t:.4f} [enter] {target} {param} {v:.4f};" for t, v in samples]
        (self.work / name).write_text("\n".join(lines), "utf-8")
        return name

    # ------------------------------------------------------------ cadenas
    def _visual_tracks(self) -> list[Track]:
        return [t for t in self.p.tracks if t.kind in ("video", "text") and not t.hidden]

    def _is_visual(self, c: Clip) -> bool:
        if c.kind in ("text", "color"):
            return True
        if c.kind == "media":
            m = self.p.media_by_id(c.media_id)
            return m is not None and m.kind in ("video", "image")
        return False

    def build_chains(self, track: Track) -> list[_Chain]:
        chains: list[_Chain] = []
        clips = sorted((c for c in track.clips if self._is_visual(c)), key=lambda c: c.start)
        frame = 1 / self.fps
        for c in clips:
            cur = _Member(c, track, c.start, c.duration)
            prev_chain = chains[-1] if chains else None
            prev = prev_chain.members[-1] if prev_chain else None
            if prev is None:
                chains.append(_Chain([cur]))
                continue
            prev_end = prev.start + prev.dur
            overlap = prev_end - c.start
            tr = c.transition_in
            if tr and tr.duration > frame and overlap > -frame:
                if overlap > frame:
                    d = min(tr.duration, overlap, prev.dur, c.duration)
                    min_prev = (prev.xfade[1] if prev.xfade else 0) + frame
                    prev.dur = max(min_prev, (c.start + d) - prev.start)
                else:
                    d = min(tr.duration, prev.dur * 0.5, c.duration * 0.5)
                    prev.extend = d + max(0.0, -overlap)
                cur.xfade = (tr.type or "fade", max(frame, d))
                prev_chain.members.append(cur)  # type: ignore[union-attr]
                continue
            if overlap > 1e-6:
                new_dur = c.start - prev.start
                if new_dur <= frame:
                    prev_chain.members.pop()  # type: ignore[union-attr]
                    if not prev_chain.members:  # type: ignore[union-attr]
                        chains.pop()
                else:
                    prev.dur = new_dur
            if tr and tr.duration > frame:
                # transición tras un hueco: se convierte en fundido de entrada
                cur.clip = c.model_copy(update={"fade_in": max(c.fade_in, tr.duration)})
            chains.append(_Chain([cur]))
        return chains

    # ------------------------------------------------------------ clip → flujo normalizado
    def _clip_stream(self, mem: _Member) -> str:
        c = mem.clip
        dur = mem.dur + mem.extend
        CW, CH = self.CW, self.CH
        filters: list[str] = []
        src_w = src_h = None
        is_text = c.kind == "text"
        is_image = False

        if c.kind == "media":
            m = self.p.media_by_id(c.media_id)
            assert m is not None
            path = self._media_path(m)
            src_w, src_h = m.width or CW, m.height or CH
            if m.kind == "image":
                is_image = True
                idx = self._input(["-loop", "1", "-framerate", self.fps_s, "-t", f"{dur + 0.5:.4f}", "-i", str(path)])
                filters += ["setpts=PTS-STARTPTS"]
            else:
                src_dur = mem.dur * c.speed
                seek = max(0.0, c.in_point)
                if c.reverse:
                    idx = self._input(["-ss", f"{seek:.4f}", "-t", f"{src_dur:.4f}", "-i", str(path)])
                    filters += ["setpts=PTS-STARTPTS", "reverse"]
                else:
                    idx = self._input(["-ss", f"{seek:.4f}", "-t", f"{src_dur + 0.05:.4f}", "-i", str(path)])
                    filters += ["setpts=PTS-STARTPTS"]
                if abs(c.speed - 1) > 1e-4:
                    filters.append(f"setpts=PTS/{c.speed:.6f}")
            src_label = f"{idx}:v"
        elif c.kind == "color":
            idx = self._input(["-f", "lavfi", "-i", f"color=c={_ffcolor(c.fill)}:s={CW}x{CH}:r={self.fps_s}:d={dur + 0.5:.4f}"])
            src_label = f"{idx}:v"
            src_w, src_h = CW, CH
        elif is_text:
            assert c.text is not None
            if c.text.animation == "typewriter":
                reveal = min(max(0.3, dur * 0.6), max(0.3, len(c.text.content) * 0.045))
                folder = self.work / f"tw_{c.id}"
                pattern, src_w, src_h, _n = render_typewriter_frames(c.text, CW, CH, folder, self.fps, reveal)
                idx = self._input(["-framerate", self.fps_s, "-i", str(pattern)])
            else:
                png, src_w, src_h = render_text(c.text, CW, CH, self.work / f"text_{c.id}.png")
                idx = self._input(["-loop", "1", "-framerate", self.fps_s, "-t", f"{dur + 0.5:.4f}", "-i", str(png)])
            src_label = f"{idx}:v"
            filters.append("setpts=PTS-STARTPTS")
        else:
            raise ValueError(f"Clip no visual: {c.kind}")

        filters += [f"fps={self.fps_s}", f"tpad=stop_mode=clone:stop_duration={dur + 1:.4f}", f"trim=duration={dur:.4f}", "setpts=PTS-STARTPTS"]

        tr = c.transform
        # Recorte de origen y volteos
        cr = tr.crop
        if any(v > 1e-4 for v in (cr.left, cr.right, cr.top, cr.bottom)):
            fw = max(0.02, 1 - cr.left - cr.right)
            fh = max(0.02, 1 - cr.top - cr.bottom)
            filters.append(f"crop=trunc(iw*{fw:.5f}/2)*2:trunc(ih*{fh:.5f}/2)*2:iw*{cr.left:.5f}:ih*{cr.top:.5f}")
            src_w, src_h = (src_w or CW) * fw, (src_h or CH) * fh
        if tr.flip_h:
            filters.append("hflip")
        if tr.flip_v:
            filters.append("vflip")

        # Tamaño destino
        sw, sh = float(src_w or CW), float(src_h or CH)
        if is_text:
            tw, th = sw * tr.scale, sh * tr.scale
        elif tr.fit == "cover":
            s = max(CW / sw, CH / sh) * tr.scale
            tw, th = sw * s, sh * s
        elif tr.fit == "contain":
            s = min(CW / sw, CH / sh) * tr.scale
            tw, th = sw * s, sh * s
        elif tr.fit == "stretch":
            tw, th = CW * tr.scale, CH * tr.scale
        else:
            tw, th = sw * self.k * tr.scale, sh * self.k * tr.scale
        TW, TH = _even(tw), _even(th)

        motion = c.motion.preset if c.motion else "none"
        scale_kf = c.keyframes.get("scale") or []
        if is_text:
            if abs(tr.scale - 1) > 1e-3:
                filters.append(f"scale={TW}:{TH}:flags=lanczos")
        elif motion != "none":
            filters += self._motion_filters(motion, c.motion.intensity, TW, TH, dur, is_image)
        else:
            filters.append(f"scale={TW}:{TH}:flags=lanczos")
        filters.append("setsar=1")
        if scale_kf:
            e = kf.expr(scale_kf, 1.0, "t")
            filters.append(f"scale=w='max(2,trunc({TW}*({e})/{max(tr.scale, 1e-3):.6f}/2)*2)':h='max(2,trunc({TH}*({e})/{max(tr.scale, 1e-3):.6f}/2)*2)':eval=frame")

        # Etalonaje y efectos
        if not is_text:
            filters += grade_filters(c.color, self._lut)
        for eff in c.effects:
            if eff.enabled:
                filters += effect_filters(eff.type, eff.params)

        # Rotación
        rot_kf = c.keyframes.get("rotation") or []
        needs_alpha = (
            c.fade_in > 0 or c.fade_out > 0 or tr.opacity < 0.999 or abs(tr.rotation) > 1e-3 or rot_kf
            or c.keyframes.get("opacity") or is_text
        )
        if needs_alpha:
            filters.append("format=rgba")
        if rot_kf:
            e = kf.expr(rot_kf, tr.rotation, "t", scale=math.pi / 180)
            filters.append(f"rotate=a='{e}':c=none:ow='hypot(iw,ih)':oh=ow")
        elif abs(tr.rotation) > 1e-3:
            a = tr.rotation * math.pi / 180
            filters.append(f"rotate=a={a:.6f}:c=none:ow=rotw({a:.6f}):oh=roth({a:.6f})")

        # Opacidad
        op_kf = c.keyframes.get("opacity") or []
        if op_kf:
            name = f"colorchannelmixer@op{self.g.k + 1}_{len(self.inputs)}"
            cmd = self._sendcmd(name, "aa", kf.sample(op_kf, tr.opacity, dur, self.fps, step=1))
            filters += [f"sendcmd=f={cmd}", f"{name}=aa={kf.value_at(op_kf, 0, tr.opacity):.4f}"]
        elif tr.opacity < 0.999:
            filters.append(f"colorchannelmixer=aa={max(0.0, tr.opacity):.4f}")

        # Fundidos (y animaciones de texto)
        fi, fo = c.fade_in, c.fade_out
        anim = c.text.animation if (is_text and c.text) else "none"
        if is_text and anim != "none" and fi <= 0:
            fi = min(0.5, dur / 4)
        if is_text and anim != "none" and fo <= 0:
            fo = min(0.4, dur / 5)
        if is_text and anim == "zoom":
            filters.append(f"scale=w='max(2,trunc(iw*(0.85+0.15*min(t/0.6,1))/2)*2)':h=-2:eval=frame")
        if fi > 0:
            filters.append(f"fade=t=in:st=0:d={min(fi, dur):.4f}:alpha=1")
        if fo > 0:
            filters.append(f"fade=t=out:st={max(0.0, dur - fo):.4f}:d={min(fo, dur):.4f}:alpha=1")

        # Colocación en el lienzo
        xk, yk = c.keyframes.get("x") or [], c.keyframes.get("y") or []
        full = (
            TW == CW and TH == CH and abs(tr.x - 0.5) < 1e-4 and abs(tr.y - 0.5) < 1e-4
            and not xk and not yk and not scale_kf and not rot_kf and abs(tr.rotation) < 1e-3 and not is_text
        )
        lbl = self.g.add([src_label], filters)
        if full:
            return self.g.add([lbl], [f"format={self.comp_fmt}", "settb=AVTB"])
        ex = kf.expr(xk, tr.x, "t", scale=CW)
        ey = kf.expr(yk, tr.y, "t", scale=CH)
        if is_text and anim in ("slide_up", "slide_down"):
            sign = 1 if anim == "slide_up" else -1
            ey = f"({ey})+{sign}*{CH * 0.06:.2f}*(1-min(t/0.6,1))*(1-min(t/0.6,1))"
        bg = self.g.tmp("bg")
        self.g.raw(f"color=c=black@0.0:s={CW}x{CH}:r={self.fps_s}:d={dur:.4f},format={self.comp_fmt}[{bg}]")
        placed = self.g.tmp("pl")
        self.g.raw(
            f"[{bg}][{lbl}]overlay=x='({ex})-w/2':y='({ey})-h/2':eval=frame:eof_action=pass:format=auto,"
            f"format={self.comp_fmt},settb=AVTB[{placed}]"
        )
        return placed

    def _motion_filters(self, preset: str, intensity: float, TW: int, TH: int, dur: float, is_image: bool) -> list[str]:
        it = min(1.0, max(0.05, intensity))
        m = 1 + 0.25 * it  # sobredimensión (=rango de zoom)
        over = 1.5 if is_image else 1.0
        PW, PH = _even(TW * m * over), _even(TH * m * over)
        N = max(1, int(dur * self.fps))
        p = f"(on/{N})"
        e = f"({p}*{p}*(3-2*{p}))"  # suavizado
        cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        z = f"{m:.4f}"
        if preset == "push_in":
            z, x, y = f"1+({m - 1:.4f})*{e}", cx, cy
        elif preset == "pull_out":
            z, x, y = f"{m:.4f}-({m - 1:.4f})*{e}", cx, cy
        elif preset == "pan_left":
            x, y = f"(iw-iw/zoom)*(1-{e})", cy
        elif preset == "pan_right":
            x, y = f"(iw-iw/zoom)*{e}", cy
        elif preset == "tilt_up":
            x, y = cx, f"(ih-ih/zoom)*(1-{e})"
        elif preset == "tilt_down":
            x, y = cx, f"(ih-ih/zoom)*{e}"
        elif preset == "handheld":
            z = f"{1 + 0.08 * it:.4f}"
            amp = 0.45
            fr = self.fps
            x = f"(iw-iw/zoom)/2*(1+{amp}*(0.6*sin(on/{fr}*2.1)+0.3*sin(on/{fr}*5.3+1)+0.1*sin(on/{fr}*11)))"
            y = f"(ih-ih/zoom)/2*(1+{amp}*(0.6*sin(on/{fr}*1.7+2)+0.3*sin(on/{fr}*4.1)+0.1*sin(on/{fr}*9+3)))"
        else:  # drift
            z = f"1+({(m - 1) * 0.5:.4f})*{e}"
            x = f"(iw-iw/zoom)*(0.35+0.3*{e})"
            y = cy
        return [
            f"scale={PW}:{PH}:flags=lanczos",
            f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={TW}x{TH}:fps={self.fps_s}",
        ]

    def _chain_stream(self, chain: _Chain) -> str:
        acc = self._clip_stream(chain.members[0])
        acc_len = chain.members[0].dur + chain.members[0].extend
        for mem in chain.members[1:]:
            nxt = self._clip_stream(mem)
            assert mem.xfade is not None
            ttype, d = mem.xfade
            offset = mem.start - chain.start
            offset = max(0.0, min(offset, acc_len - d))
            out = self.g.tmp("xf")
            self.g.raw(f"[{acc}][{nxt}]xfade=transition={ttype}:duration={d:.4f}:offset={offset:.4f},format={self.comp_fmt}[{out}]")
            acc = out
            acc_len = offset + mem.dur + mem.extend
        return acc

    # ------------------------------------------------------------ vídeo completo
    def build_video(self) -> str:
        CW, CH = self.CW, self.CH
        base = self.g.tmp("base")
        if self.alpha_out:
            self.g.raw(f"color=c=black@0.0:s={CW}x{CH}:r={self.fps_s}:d={self.D:.4f},format={self.comp_fmt}[{base}]")
        else:
            bg = _ffcolor(self.p.settings.background)
            fmt = "yuv444p" if self.comp_fmt == "yuva444p" else "yuv420p"
            self.g.raw(f"color=c={bg}:s={CW}x{CH}:r={self.fps_s}:d={self.D:.4f},format={fmt},settb=AVTB[{base}]")
        stack = base
        for track in self._visual_tracks():
            for chain in self.build_chains(track):
                if chain.end <= self.start + 1e-6 or chain.start >= self.end - 1e-6:
                    continue
                lbl = self._chain_stream(chain)
                offset = chain.start - self.start
                shifted = self.g.tmp("sh")
                if offset < 0:
                    self.g.raw(f"[{lbl}]trim=start={-offset:.4f},setpts=PTS-STARTPTS[{shifted}]")
                else:
                    self.g.raw(f"[{lbl}]setpts=PTS-STARTPTS+{offset:.4f}/TB[{shifted}]")
                out = self.g.tmp("ov")
                self.g.raw(f"[{stack}][{shifted}]overlay=eof_action=pass:format=auto[{out}]")
                stack = out
            # capas de ajuste de esta pista
            for c in track.clips:
                if c.kind != "adjustment" or c.end <= self.start or c.start >= self.end:
                    continue
                a, b = c.start - self.start, c.end - self.start
                fl = grade_filters(c.color, self._lut, enable=f"between(t,{a:.4f},{b:.4f})")
                fl = [f for f in fl if not f.startswith("@graph:")]
                for eff in c.effects:
                    if eff.enabled:
                        fl += [f"{x}:enable='between(t,{a:.4f},{b:.4f})'" for x in effect_filters(eff.type, eff.params)
                               if not x.startswith("@graph:") and "=" in x and "[" not in x]
                if fl:
                    stack = self.g.add([stack], fl)
        return self._post(stack)

    def _post(self, stack: str) -> str:
        OW, OH = self.OW, self.OH
        fl: list[str] = []
        if self.post == "fit" or (self.post == "blur_fill" and self.alpha_out):
            fl.append(f"pad={OW}:{OH}:(ow-iw)/2:(oh-ih)/2:color={_ffcolor(self.p.settings.background)}{'@0' if self.alpha_out else ''}")
        elif self.post == "fill":
            fl.append(f"crop={OW}:{OH}:(iw-ow)/2:(ih-oh)/2")
        elif self.post == "blur_fill":
            out = self.g.tmp("bf")
            u = self.g.tmp("b")
            self.g.raw(
                f"[{stack}]split[{u}a][{u}b];"
                f"[{u}a]scale={OW}:{OH}:force_original_aspect_ratio=increase,crop={OW}:{OH},gblur=sigma=40,eq=brightness=-0.08:saturation=1.1[{u}c];"
                f"[{u}c][{u}b]overlay=(W-w)/2:(H-h)/2[{out}]"
            )
            stack = out
        if (self.CW, self.CH) != (OW, OH) and self.post == "none":
            fl.append(f"scale={OW}:{OH}:flags=lanczos")
        if fl:
            stack = self.g.add([stack], fl)
        watermark = self.s.ai_watermark if self.s.ai_watermark is not None else self.cfg.settings.ethics.ai_label_watermark
        if watermark and self._has_ai_content():
            badge = _ai_badge(self.work / "ai_badge.png", OH)
            idx = self._input(["-loop", "1", "-i", str(badge)])
            out = self.g.tmp("wm")
            margin = int(OH * 0.03)
            self.g.raw(f"[{stack}][{idx}:v]overlay=W-w-{margin}:H-h-{margin}:shortest=1[{out}]")
            stack = out
        return stack

    def _has_ai_content(self) -> bool:
        return any(m.ai_generated for m in self.p.media)

    # ------------------------------------------------------------ audio
    def build_audio(self) -> str | None:
        tracks = [t for t in self.p.tracks if not t.muted]
        if any(t.solo for t in self.p.tracks):
            tracks = [t for t in tracks if t.solo]
        labels: list[str] = []
        sr = self.p.settings.sample_rate
        for trk in tracks:
            for c in trk.clips:
                if c.kind != "media" or c.muted:
                    continue
                m = self.p.media_by_id(c.media_id)
                if m is None or not m.has_audio or m.kind == "image":
                    continue
                if c.end <= self.start or c.start >= self.end:
                    continue
                cut = max(0.0, self.start - c.start)
                dur = min(c.duration - cut, self.end - max(c.start, self.start))
                if dur <= 0:
                    continue
                speed = c.speed
                src_in = c.in_point + (0 if c.reverse else cut * speed)
                src_dur = dur * speed
                if c.reverse:
                    src_in = c.in_point + (c.duration - cut - dur) * speed
                idx = self._input(["-ss", f"{max(0.0, src_in):.4f}", "-t", f"{src_dur:.4f}", "-i", str(self._media_path(m))])
                fl = ["asetpts=PTS-STARTPTS"]
                if c.reverse:
                    fl.append("areverse")
                if abs(speed - 1) > 1e-4:
                    fl += [f"atempo={f:.6f}" for f in _atempo_chain(speed)]
                fl += [f"aresample={sr}", "aformat=sample_fmts=fltp:channel_layouts=stereo"]
                vol = c.volume * trk.volume
                vkf = c.keyframes.get("volume") or []
                if vkf:
                    var = f"(t+{cut:.4f})" if cut > 0 else "t"
                    e = kf.expr(vkf, 1.0, var, scale=trk.volume)
                    fl.append(f"volume='{e}':eval=frame")
                elif abs(vol - 1) > 1e-4:
                    fl.append(f"volume={vol:.4f}")
                if c.audio_fade_in > 0 and cut < c.audio_fade_in:
                    fl.append(f"afade=t=in:st=0:d={c.audio_fade_in - cut:.4f}")
                if c.audio_fade_out > 0:
                    st = max(0.0, (c.duration - cut) - c.audio_fade_out)
                    fl.append(f"afade=t=out:st={st:.4f}:d={c.audio_fade_out:.4f}")
                fl.append(f"atrim=duration={dur:.4f}")
                delay = int(round(max(0.0, c.start - self.start) * 1000))
                if delay > 0:
                    fl.append(f"adelay={delay}:all=1")
                labels.append(self.g.add([f"{idx}:a"], fl, audio=True))
        if not labels:
            return None
        out = self.g.tmp("mix")
        if len(labels) == 1:
            mix = f"[{labels[0]}]anull"
        else:
            mix = "".join(f"[{lbl}]" for lbl in labels) + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0"
        post = f",apad=whole_dur={self.D:.4f},atrim=duration={self.D:.4f}"
        if self.s.loudness is not None and not self.s.preview:
            post += f",loudnorm=I={self.s.loudness:.1f}:TP=-1.0:LRA=11"
            post += f",aresample={sr}"
        post += ",alimiter=limit=0.98:level=disabled"
        self.g.raw(f"{mix}{post}[{out}]")
        return out

    # ------------------------------------------------------------ comando
    def build_command(self, out_path: Path) -> tuple[list[str], Path]:
        fmt = self.fmt
        want_video = fmt.kind != "audio" and self.s.include_video
        want_audio = fmt.kind in ("video", "audio") and self.s.include_audio
        vout = self.build_video() if want_video else None
        aout = self.build_audio() if want_audio else None
        if want_audio and aout is None and fmt.kind == "audio":
            lbl = self.g.tmp("sil")
            self.g.raw(f"anullsrc=r={self.p.settings.sample_rate}:cl=stereo,atrim=duration={self.D:.4f}[{lbl}]")
            aout = lbl
        if fmt.kind == "gif" and vout:
            g = self.g.tmp("gif")
            gw = min(self.OW, 720)
            self.g.raw(
                f"[{vout}]fps={min(self.fps, 15):.3f},scale={gw}:-2:flags=lanczos,split[{g}a][{g}b];"
                f"[{g}a]palettegen=stats_mode=diff[{g}p];[{g}b][{g}p]paletteuse=dither=bayer:bayer_scale=5[{g}]"
            )
            vout = g
        script = self.work / "graph.txt"
        script.write_text(self.g.script(), "utf-8")
        args: list[str] = []
        for inp in self.inputs:
            args += inp
        args += filter_script_args(script.name)
        if vout:
            args += ["-map", f"[{vout}]"]
        if aout:
            args += ["-map", f"[{aout}]"]
        q = "draft" if self.s.preview else self.s.quality
        if vout and fmt.kind in ("video", "image", "sequence", "gif"):
            if self.s.preview:
                args += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p"]
            else:
                args += fmt.vcodec
                if fmt.crf_flag and fmt.quality:
                    args += [fmt.crf_flag, str(fmt.quality.get(q, 20))]
                pix = fmt.pix_fmt
                if pix and not (fmt.alpha and not self.s.transparent and pix.startswith(("yuva", "rgba"))):
                    args += ["-pix_fmt", pix]
                elif pix and fmt.alpha and not self.s.transparent:
                    args += ["-pix_fmt", pix.replace("yuva", "yuv").replace("rgba64be", "rgb48be")]
            if fmt.kind in ("video",):
                args += ["-r", self.fps_s]
                if not self.s.preview and fmt.ext in ("mp4", "mov", "mkv", "mxf"):
                    args += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
        if aout:
            if self.s.preview:
                args += ["-c:a", "aac", "-b:a", "128k"]
            else:
                args += fmt.acodec or ["-c:a", "aac", "-b:a", "256k"]
            args += ["-ar", str(self.p.settings.sample_rate)]
        if fmt.kind == "image":
            args += ["-frames:v", "1"]
        else:
            args += ["-t", f"{self.D:.4f}"]
        if not self.s.preview:
            args += fmt.extra
        args += self._metadata_args(fmt)
        if fmt.kind == "sequence":
            seq_dir = self.work / "frames"
            seq_dir.mkdir(exist_ok=True)
            ext = "png" if "png" in fmt.id else "jpg"
            target = seq_dir / f"frame_%06d.{ext}"
            args += [str(target)]
        else:
            args += [str(out_path)]
        return args, out_path

    def _metadata_args(self, fmt: FormatPreset) -> list[str]:
        if fmt.kind in ("sequence", "image", "gif"):
            return []
        md: dict[str, str] = {}
        if self.s.title or self.p.name:
            md["title"] = self.s.title or self.p.name
        if self.s.author:
            md["artist"] = self.s.author
        if self.s.copyright:
            md["copyright"] = self.s.copyright
        md["encoder"] = f"{APP_NAME} {__version__}"
        label_md = self.s.ai_metadata if self.s.ai_metadata is not None else self.cfg.settings.ethics.ai_label_metadata
        if label_md and self._has_ai_content():
            md["comment"] = "Contenido generado o modificado con IA (durosTCM). AI-generated content."
            md["description"] = "AI-generated: yes; tool: durosTCM; see provenance manifest"
        out: list[str] = []
        for k, v in md.items():
            out += ["-metadata", f"{k}={v}"]
        return out


def _atempo_chain(speed: float) -> list[float]:
    out = []
    s = speed
    while s > 2.0:
        out.append(2.0)
        s /= 2.0
    while s < 0.5:
        out.append(0.5)
        s /= 0.5
    out.append(s)
    return out


def _ffcolor(c: str | None) -> str:
    r, g, b, a = parse_color(c, (0, 0, 0, 255))
    base = f"0x{r:02X}{g:02X}{b:02X}"
    return base if a == 255 else f"{base}@{a / 255:.3f}"


def _ai_badge(path: Path, out_h: int) -> Path:
    from PIL import Image, ImageDraw

    from .text import load_font

    size = max(12, int(out_h * 0.022))
    font = load_font("Inter", size, "bold")
    label = "Generado con IA"
    tmp = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    w = int(tmp.textlength(label, font=font)) + size
    h = int(size * 1.7)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 3, fill=(0, 0, 0, 140))
    d.text((size // 2, (h - size) // 2 - size * 0.1), label, font=font, fill=(255, 255, 255, 230))
    img.save(path)
    return path


# ---------------------------------------------------------------- API de alto nivel
async def render_project(
    store: ProjectStore,
    project: Project,
    settings: RenderSettings,
    *,
    progress=None,
    cancel_event: asyncio.Event | None = None,
    job_id: str = "",
) -> dict:
    """Renderiza el proyecto y devuelve info del archivo resultante."""
    renders = store.subdir(project.id, "renders")
    work = store.subdir(project.id, "cache") / f"render_{job_id or int(time.time() * 1000)}"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    r = Renderer(store, project, settings, work)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = settings.filename or f"{_slug(project.name)}_{r.OW}x{r.OH}_{stamp}"
    base = _slug(base) or "render"
    if settings.preview:
        out_path = work / "preview.mp4"
    else:
        out_path = renders / f"{base}.{r.fmt.ext}"
    args, out_path = r.build_command(out_path)
    try:
        await run_ffmpeg(args, duration=r.D, progress=progress, cancel_event=cancel_event, label="render", cwd=work)
        if r.fmt.kind == "sequence":
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as z:
                for f in sorted((work / "frames").iterdir()):
                    z.write(f, f.name)
        extras: list[str] = []
        if not settings.preview:
            if settings.subtitles_sidecar:
                srt = export_srt(project, out_path.with_suffix(".srt"), settings.start, settings.end)
                if srt:
                    extras.append(srt.name)
            if get_config().settings.ethics.provenance_sidecar:
                prov = write_provenance(project, out_path, settings)
                extras.append(prov.name)
    finally:
        if not settings.preview:
            shutil.rmtree(work, ignore_errors=True)
    return {
        "path": store.relative(project.id, out_path),
        "name": out_path.name,
        "size_bytes": out_path.stat().st_size if out_path.exists() else 0,
        "width": r.OW,
        "height": r.OH,
        "fps": r.fps,
        "duration": r.D,
        "format": settings.format,
        "extras": extras,
        "warnings": r.warnings,
    }


async def render_frame(store: ProjectStore, project: Project, t: float, max_h: int = 720) -> Path:
    """Fotograma exacto del render final en ``t`` (JPG)."""
    work = store.subdir(project.id, "cache") / "frame"
    work.mkdir(parents=True, exist_ok=True)
    h = min(max_h, project.settings.height)
    w = _even(project.settings.width * h / project.settings.height)
    s = RenderSettings(format="jpg_still", start=max(0.0, t), end=t + 1 / project.settings.fps, width=w, height=_even(h), include_audio=False, subtitles_sidecar=False)
    r = Renderer(store, project, s, work)
    out = work / f"frame_{int(t * 1000)}.jpg"
    args, _ = r.build_command(out)
    await run_ffmpeg(args, label="frame", cwd=work)
    return out


def export_srt(project: Project, path: Path, start: float = 0.0, end: float | None = None) -> Path | None:
    """Subtítulos (pistas de texto llamadas 'Subtítulos'/'subs') en formato SRT."""
    items = []
    for t in project.tracks:
        if t.kind != "text" or not any(k in t.name.lower() for k in ("subt", "subs", "caption")):
            continue
        for c in t.clips:
            if c.kind == "text" and c.text and c.text.content.strip():
                items.append(c)
    if not items:
        return None
    items.sort(key=lambda c: c.start)
    end = end if end is not None else project.duration

    def ts(x: float) -> str:
        x = max(0.0, x)
        h, rem = divmod(x, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)) % 1000:03d}"

    lines = []
    n = 0
    for c in items:
        if c.end <= start or c.start >= end:
            continue
        n += 1
        lines += [str(n), f"{ts(c.start - start)} --> {ts(min(c.end, end) - start)}", c.text.content.strip(), ""]  # type: ignore[union-attr]
    if not n:
        return None
    path.write_text("\n".join(lines), "utf-8")
    return path


def write_provenance(project: Project, out_path: Path, settings: RenderSettings) -> Path:
    """Manifiesto de procedencia (inspirado en C2PA): qué es IA, con qué modelos, licencias y consentimientos."""
    used = set()
    for t in project.tracks:
        for c in t.clips:
            if c.media_id:
                used.add(c.media_id)
    assets = []
    for m in project.media:
        if m.id not in used:
            continue
        assets.append(
            {
                "id": m.id,
                "name": m.name,
                "kind": m.kind,
                "ai_generated": m.ai_generated,
                "generation": m.generation.model_dump() if m.generation else None,
                "credit": m.credit.model_dump() if m.credit else None,
            }
        )
    manifest = {
        "claim_generator": f"{APP_NAME}/{__version__}",
        "title": settings.title or project.name,
        "output": out_path.name,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ai_generated_content": any(a["ai_generated"] for a in assets),
        "disclosure": "Este contenido contiene material generado o modificado con inteligencia artificial."
        if any(a["ai_generated"] for a in assets)
        else "",
        "assets": assets,
        "credits": [c.model_dump() for c in project.credits],
        "render_settings": settings.model_dump(),
    }
    path = out_path.with_name(out_path.stem + ".provenance.json")
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    return path


def _slug(s: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in s.strip())
    while "__" in keep:
        keep = keep.replace("__", "_")
    return keep.strip("_")[:80]

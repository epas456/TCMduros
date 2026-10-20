/**
 * Compositor de previsualización en tiempo real (Canvas 2D).
 *
 * Reproduce la línea de tiempo en el navegador con una aproximación fiel del render final:
 * capas, transformaciones, keyframes, movimientos de cámara, fundidos, transiciones,
 * etalonaje (filtros CSS), textos animados y mezcla de audio. Para la imagen exacta
 * píxel a píxel se usa el render de previsualización del servidor (FFmpeg).
 */
import { urls } from "../api";
import { kfValue } from "../lib/timeline";
import type { Clip, ColorGrade, MediaItem, Project, TextStyle, Track } from "../types";

const LOOK_FILTERS: Record<string, string> = {
  teal_orange: "contrast(1.12) saturate(1.15) sepia(0.08) hue-rotate(-6deg)",
  bleach_bypass: "contrast(1.35) saturate(0.55)",
  noir: "grayscale(1) contrast(1.4)",
  warm_film: "sepia(0.18) contrast(1.08) saturate(1.05)",
  cold_thriller: "saturate(0.8) contrast(1.15) hue-rotate(12deg) brightness(0.97)",
  vintage: "sepia(0.3) saturate(0.85) contrast(0.95)",
  cross_process: "saturate(1.3) hue-rotate(-12deg) contrast(1.1)",
  pastel_dream: "saturate(0.9) contrast(0.9) brightness(1.05)",
  neon_night: "contrast(1.2) saturate(1.35) hue-rotate(8deg)",
  golden_hour: "sepia(0.25) saturate(1.1) brightness(1.03)",
  matrix: "hue-rotate(60deg) saturate(0.8) contrast(1.2)",
  documentary: "contrast(1.05) saturate(0.95)",
  commercial_pop: "contrast(1.1) saturate(1.3)",
  horror: "saturate(0.45) contrast(1.25) brightness(0.92)",
};

function gradeFilter(g: ColorGrade, effects: { type: string; enabled: boolean }[]): string {
  const parts: string[] = [];
  if (g.look && LOOK_FILTERS[g.look]) parts.push(LOOK_FILTERS[g.look]);
  const b = Math.pow(2, g.exposure) * (1 + (g.shadows + g.highlights) * 0.05);
  if (Math.abs(b - 1) > 1e-3) parts.push(`brightness(${b.toFixed(3)})`);
  if (Math.abs(g.contrast - 1) > 1e-3) parts.push(`contrast(${g.contrast})`);
  if (Math.abs(g.saturation - 1) > 1e-3) parts.push(`saturate(${g.saturation})`);
  if (g.temperature > 0.01) parts.push(`sepia(${(g.temperature * 0.35).toFixed(3)})`);
  if (g.temperature < -0.01) parts.push(`hue-rotate(${(g.temperature * -12).toFixed(1)}deg)`);
  if (Math.abs(g.tint) > 0.01) parts.push(`hue-rotate(${(g.tint * 10).toFixed(1)}deg)`);
  if (g.blur > 0.001) parts.push(`blur(${(g.blur * 8).toFixed(2)}px)`);
  for (const e of effects) {
    if (!e.enabled) continue;
    if (e.type === "bw") parts.push("grayscale(1)");
    if (e.type === "sepia" || e.type === "old_film") parts.push("sepia(0.9)");
    if (e.type === "invert") parts.push("invert(1)");
    if (e.type === "vhs") parts.push("saturate(1.3) contrast(1.1) blur(0.6px)");
  }
  return parts.join(" ") || "none";
}

function hexToRgba(c: string | null | undefined, fallback = "rgba(0,0,0,0)"): string {
  if (!c) return fallback;
  const h = c.replace("#", "");
  const n = (s: string) => parseInt(s, 16);
  if (h.length === 6) return `rgb(${n(h.slice(0, 2))},${n(h.slice(2, 4))},${n(h.slice(4, 6))})`;
  if (h.length === 8) return `rgba(${n(h.slice(0, 2))},${n(h.slice(2, 4))},${n(h.slice(4, 6))},${(n(h.slice(6, 8)) / 255).toFixed(3)})`;
  if (h.length === 3) return `rgb(${n(h[0] + h[0])},${n(h[1] + h[1])},${n(h[2] + h[2])})`;
  return fallback;
}

function motionView(preset: string, intensity: number, p: number, t: number): { z: number; ox: number; oy: number } {
  const it = Math.min(1, Math.max(0.05, intensity));
  const m = 1 + 0.25 * it;
  const e = p * p * (3 - 2 * p);
  switch (preset) {
    case "push_in": return { z: 1 + (m - 1) * e, ox: 0.5, oy: 0.5 };
    case "pull_out": return { z: m - (m - 1) * e, ox: 0.5, oy: 0.5 };
    case "pan_left": return { z: m, ox: 1 - e, oy: 0.5 };
    case "pan_right": return { z: m, ox: e, oy: 0.5 };
    case "tilt_up": return { z: m, ox: 0.5, oy: 1 - e };
    case "tilt_down": return { z: m, ox: 0.5, oy: e };
    case "handheld": {
      const a = 0.45;
      return {
        z: 1 + 0.08 * it,
        ox: 0.5 * (1 + a * (0.6 * Math.sin(t * 2.1) + 0.3 * Math.sin(t * 5.3 + 1) + 0.1 * Math.sin(t * 11))),
        oy: 0.5 * (1 + a * (0.6 * Math.sin(t * 1.7 + 2) + 0.3 * Math.sin(t * 4.1) + 0.1 * Math.sin(t * 9 + 3))),
      };
    }
    case "drift": return { z: 1 + (m - 1) * 0.5 * e, ox: 0.35 + 0.3 * e, oy: 0.5 };
    default: return { z: 1, ox: 0.5, oy: 0.5 };
  }
}

export class Compositor {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  project: Project | null = null;
  time = 0;
  playing = false;
  onTime: ((t: number) => void) | null = null;
  onEnd: (() => void) | null = null;
  videos = new Map<string, HTMLVideoElement>();
  private audios = new Map<string, HTMLAudioElement>();
  private images = new Map<string, HTMLImageElement>();
  private raf = 0;
  private wallStart = 0;
  private timeStart = 0;
  private scratch = document.createElement("canvas");
  private needsDraw = true;
  private settleUntil = 0; // repintar cada frame mientras los vídeos terminan de decodificar
  scale = 1; // resolución de previsualización relativa al proyecto
  muted = false;
  masterVolume = 1;
  loopRange: [number, number] | null = null;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d", { alpha: false })!;
    const tick = () => {
      this.raf = requestAnimationFrame(tick);
      this.frame();
    };
    this.raf = requestAnimationFrame(tick);
  }

  destroy() {
    cancelAnimationFrame(this.raf);
    for (const v of this.videos.values()) {
      v.pause();
      v.removeAttribute("src");
      v.load();
    }
    for (const a of this.audios.values()) a.pause();
    this.videos.clear();
    this.audios.clear();
  }

  setProject(p: Project | null) {
    this.project = p;
    if (p) {
      const w = Math.max(2, Math.round(p.settings.width * this.scale));
      const h = Math.max(2, Math.round(p.settings.height * this.scale));
      if (this.canvas.width !== w || this.canvas.height !== h) {
        this.canvas.width = w;
        this.canvas.height = h;
      }
      // liberar elementos de clips que ya no existen
      const ids = new Set(p.tracks.flatMap((t) => t.clips.map((c) => c.id)));
      for (const [id, v] of this.videos) if (!ids.has(id)) { v.pause(); this.videos.delete(id); }
      for (const [id, a] of this.audios) if (!ids.has(id)) { a.pause(); this.audios.delete(id); }
    }
    this.needsDraw = true;
  }

  setScale(s: number) {
    this.scale = s;
    this.setProject(this.project);
  }

  seek(t: number) {
    this.time = Math.max(0, t);
    if (this.playing) {
      this.wallStart = performance.now();
      this.timeStart = this.time;
      this.syncMedia(true);
    } else this.syncMedia(false);
    this.needsDraw = true;
    this.settleUntil = performance.now() + 600;
  }

  play() {
    if (!this.project) return;
    this.playing = true;
    this.wallStart = performance.now();
    this.timeStart = this.time;
    this.syncMedia(true);
  }

  pause() {
    this.playing = false;
    for (const v of this.videos.values()) v.pause();
    for (const a of this.audios.values()) a.pause();
    this.needsDraw = true;
  }

  invalidate() {
    this.needsDraw = true;
  }

  private duration(): number {
    let end = 0;
    for (const t of this.project?.tracks ?? []) for (const c of t.clips) end = Math.max(end, c.start + c.duration);
    return end;
  }

  private frame() {
    if (!this.project) return;
    if (this.playing) {
      const t = this.timeStart + (performance.now() - this.wallStart) / 1000;
      const end = this.loopRange ? this.loopRange[1] : this.duration();
      if (t >= end) {
        if (this.loopRange) {
          this.seek(this.loopRange[0]);
        } else {
          this.time = end;
          this.pause();
          this.onEnd?.();
        }
      } else this.time = t;
      this.syncMedia(true);
      this.onTime?.(this.time);
      this.draw();
    } else if (this.needsDraw || performance.now() < this.settleUntil) {
      this.draw();
      this.needsDraw = false;
    }
  }

  private media(c: Clip): MediaItem | undefined {
    return this.project?.media.find((m) => m.id === c.media_id);
  }

  private videoFor(c: Clip, m: MediaItem): HTMLVideoElement {
    let v = this.videos.get(c.id);
    const src = urls.media(this.project!.id, m.id, true, "video");
    if (!v) {
      v = document.createElement("video");
      v.crossOrigin = "anonymous";
      v.preload = "auto";
      v.playsInline = true;
      v.muted = true;
      const settle = () => {
        this.needsDraw = true;
        this.settleUntil = performance.now() + 1200;
      };
      for (const ev of ["seeked", "loadeddata", "canplay", "playing"]) v.addEventListener(ev, settle);
      this.videos.set(c.id, v);
    }
    if (v.dataset.src !== src) {
      v.dataset.src = src;
      v.src = src;
    }
    return v;
  }

  private imageFor(m: MediaItem): HTMLImageElement {
    let img = this.images.get(m.id);
    if (!img) {
      img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        this.needsDraw = true;
        this.settleUntil = performance.now() + 300;
      };
      img.src = urls.media(this.project!.id, m.id, false);
      this.images.set(m.id, img);
    }
    return img;
  }

  private audioFor(c: Clip, m: MediaItem): HTMLAudioElement {
    let a = this.audios.get(c.id);
    const src = urls.media(this.project!.id, m.id, true, m.kind === "video" ? "video" : "audio");
    if (!a) {
      a = new Audio();
      a.preload = "auto";
      this.audios.set(c.id, a);
    }
    if (a.dataset.src !== src) {
      a.dataset.src = src;
      a.src = src;
    }
    return a;
  }

  private sourceTime(c: Clip, m: MediaItem): number {
    const local = this.time - c.start;
    let st = c.in_point + local * c.speed;
    if (c.reverse) st = c.in_point + (c.duration - local) * c.speed;
    if (m.duration) st = Math.min(st, Math.max(0, m.duration - 0.05));
    return Math.max(0, st);
  }

  private clipVolume(track: Track, c: Clip): number {
    const local = this.time - c.start;
    let v = c.volume * track.volume * kfValue(c.keyframes.volume, local, 1);
    if (c.audio_fade_in > 0 && local < c.audio_fade_in) v *= local / c.audio_fade_in;
    if (c.audio_fade_out > 0 && local > c.duration - c.audio_fade_out) v *= Math.max(0, (c.duration - local) / c.audio_fade_out);
    return Math.max(0, Math.min(1, v * this.masterVolume));
  }

  /** Mantiene vídeos y audios sincronizados con el cabezal. */
  private syncMedia(playing: boolean) {
    const p = this.project;
    if (!p) return;
    const solo = p.tracks.some((t) => t.solo);
    const activeIds = new Set<string>();
    for (const track of p.tracks) {
      for (const c of track.clips) {
        if (c.kind !== "media") continue;
        const m = this.media(c);
        if (!m) continue;
        const inRange = this.time >= c.start - 0.5 && this.time < c.start + c.duration;
        const isActive = this.time >= c.start && this.time < c.start + c.duration;
        if (!inRange) continue;
        const audible = !this.muted && !track.muted && !c.muted && (!solo || track.solo) && m.has_audio && !c.reverse;
        if (m.kind === "video" && track.kind !== "audio") {
          const v = this.videoFor(c, m);
          activeIds.add(c.id);
          const want = this.sourceTime(c, m);
          v.muted = !audible || !isActive;
          v.volume = audible ? this.clipVolume(track, c) : 0;
          if (playing && isActive && !c.reverse) {
            if (Math.abs(v.playbackRate - c.speed) > 1e-3) v.playbackRate = Math.min(16, Math.max(0.0625, c.speed));
            if (Math.abs(v.currentTime - want) > 0.3) v.currentTime = want;
            if (v.paused) void v.play().catch(() => undefined);
          } else {
            if (!v.paused) v.pause();
            if (Math.abs(v.currentTime - want) > 0.02 && !v.seeking) v.currentTime = want;
          }
        } else if (m.kind === "audio" || (m.kind === "video" && track.kind === "audio")) {
          const a = this.audioFor(c, m);
          activeIds.add(c.id);
          const want = this.sourceTime(c, m);
          if (playing && isActive && audible) {
            a.volume = this.clipVolume(track, c);
            if (Math.abs(a.playbackRate - c.speed) > 1e-3) a.playbackRate = Math.min(4, Math.max(0.25, c.speed));
            if (Math.abs(a.currentTime - want) > 0.3) a.currentTime = want;
            if (a.paused) void a.play().catch(() => undefined);
          } else {
            if (!a.paused) a.pause();
            if (!playing && Math.abs(a.currentTime - want) > 0.05) a.currentTime = want;
          }
        }
      }
    }
    for (const [id, v] of this.videos) if (!activeIds.has(id) && !v.paused) v.pause();
    for (const [id, a] of this.audios) if (!activeIds.has(id) && !a.paused) a.pause();
  }

  draw() {
    const p = this.project;
    if (!p) return;
    const ctx = this.ctx;
    const W = this.canvas.width;
    const H = this.canvas.height;
    ctx.save();
    ctx.globalAlpha = 1;
    ctx.filter = "none";
    ctx.fillStyle = p.settings.background || "#000";
    ctx.fillRect(0, 0, W, H);
    for (const track of p.tracks) {
      if ((track.kind !== "video" && track.kind !== "text") || track.hidden) continue;
      const clips = track.clips.filter((c) => this.time >= c.start && this.time < c.start + c.duration).sort((a, b) => a.start - b.start);
      for (const c of clips) {
        if (c.kind === "adjustment") this.drawAdjustment(c);
        else this.drawClip(track, c, W, H);
      }
    }
    ctx.restore();
  }

  private clipAlpha(c: Clip, local: number): number {
    let a = kfValue(c.keyframes.opacity, local, c.transform.opacity);
    let fi = c.fade_in;
    let fo = c.fade_out;
    if (c.kind === "text" && c.text && c.text.animation !== "none") {
      if (fi <= 0) fi = Math.min(0.5, c.duration / 4);
      if (fo <= 0) fo = Math.min(0.4, c.duration / 5);
    }
    if (c.transition_in && c.transition_in.duration > 0) fi = Math.max(fi, c.transition_in.duration);
    if (fi > 0 && local < fi) a *= local / fi;
    if (fo > 0 && local > c.duration - fo) a *= Math.max(0, (c.duration - local) / fo);
    return Math.max(0, Math.min(1, a));
  }

  private drawClip(track: Track, c: Clip, W: number, H: number) {
    const ctx = this.ctx;
    const p = this.project!;
    const local = this.time - c.start;
    const alpha = this.clipAlpha(c, local);
    if (alpha <= 0.001) return;
    let src: CanvasImageSource | null = null;
    let sw = W;
    let sh = H;
    if (c.kind === "media") {
      const m = this.media(c);
      if (!m) return;
      if (m.kind === "image") {
        const img = this.imageFor(m);
        if (!img.complete || !img.naturalWidth) return;
        src = img;
        sw = img.naturalWidth;
        sh = img.naturalHeight;
      } else if (m.kind === "video" && track.kind !== "audio") {
        const v = this.videoFor(c, m);
        if (v.readyState < 2) return;
        src = v;
        sw = v.videoWidth;
        sh = v.videoHeight;
      } else return;
    } else if (c.kind === "color") {
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.fillStyle = hexToRgba(c.fill, "#000");
      ctx.fillRect(0, 0, W, H);
      ctx.restore();
      return;
    } else if (c.kind === "text" && c.text) {
      this.drawText(c, c.text, local, alpha, W, H);
      return;
    }
    if (!src || !sw || !sh) return;
    const tr = c.transform;
    // recorte de origen
    const cl = tr.crop;
    let sx = cl.left * sw;
    let sy = cl.top * sh;
    let cw = sw * Math.max(0.02, 1 - cl.left - cl.right);
    let ch = sh * Math.max(0.02, 1 - cl.top - cl.bottom);
    // tamaño destino
    const k = W / p.settings.width;
    const scale = kfValue(c.keyframes.scale, local, tr.scale);
    let dw: number, dh: number;
    if (tr.fit === "cover") {
      const s = Math.max(W / cw, H / ch) * scale;
      dw = cw * s; dh = ch * s;
    } else if (tr.fit === "contain") {
      const s = Math.min(W / cw, H / ch) * scale;
      dw = cw * s; dh = ch * s;
    } else if (tr.fit === "stretch") {
      dw = W * scale; dh = H * scale;
    } else {
      dw = cw * k * scale; dh = ch * k * scale;
    }
    // movimiento de cámara virtual (recorta la ventana de origen)
    if (c.motion && c.motion.preset !== "none") {
      const mv = motionView(c.motion.preset, c.motion.intensity, Math.min(1, local / Math.max(0.01, c.duration)), local);
      const zw = cw / mv.z;
      const zh = ch / mv.z;
      sx += (cw - zw) * mv.ox;
      sy += (ch - zh) * mv.oy;
      cw = zw; ch = zh;
    }
    const cx = kfValue(c.keyframes.x, local, tr.x) * W;
    const cy = kfValue(c.keyframes.y, local, tr.y) * H;
    const rot = (kfValue(c.keyframes.rotation, local, tr.rotation) * Math.PI) / 180;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.filter = gradeFilter(c.color, c.effects);
    ctx.translate(cx, cy);
    if (rot) ctx.rotate(rot);
    ctx.scale(tr.flip_h || c.effects.some((e) => e.enabled && e.type === "mirror") ? -1 : 1, tr.flip_v ? -1 : 1);
    try {
      ctx.drawImage(src, sx, sy, cw, ch, -dw / 2, -dh / 2, dw, dh);
    } catch {
      /* fotograma aún no disponible */
    }
    ctx.restore();
    if (c.color.vignette > 0.01) this.vignette(c.color.vignette * alpha, W, H);
    for (const e of c.effects) {
      if (e.enabled && e.type === "letterbox") {
        const ratio = Number(e.params.ratio ?? 2.39);
        const bar = Math.max(0, (H - W / ratio) / 2);
        ctx.fillStyle = "#000";
        ctx.fillRect(0, 0, W, bar);
        ctx.fillRect(0, H - bar, W, bar);
      }
    }
  }

  private vignette(strength: number, W: number, H: number) {
    const ctx = this.ctx;
    const g = ctx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.3, W / 2, H / 2, Math.max(W, H) * 0.75);
    g.addColorStop(0, "rgba(0,0,0,0)");
    g.addColorStop(1, `rgba(0,0,0,${Math.min(0.85, strength).toFixed(3)})`);
    ctx.save();
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }

  private drawAdjustment(c: Clip) {
    const W = this.canvas.width;
    const H = this.canvas.height;
    if (this.scratch.width !== W || this.scratch.height !== H) {
      this.scratch.width = W;
      this.scratch.height = H;
    }
    const s = this.scratch.getContext("2d")!;
    s.drawImage(this.canvas, 0, 0);
    this.ctx.save();
    this.ctx.filter = gradeFilter(c.color, c.effects);
    this.ctx.drawImage(this.scratch, 0, 0);
    this.ctx.restore();
    if (c.color.vignette > 0.01) this.vignette(c.color.vignette, W, H);
  }

  private drawText(c: Clip, st: TextStyle, local: number, alpha: number, W: number, H: number) {
    const ctx = this.ctx;
    const size = Math.max(6, st.size * H * c.transform.scale);
    const family = `"${st.font}", Inter, "Helvetica Neue", Arial, sans-serif`;
    ctx.save();
    ctx.font = `${st.weight === "bold" ? "700" : "400"} ${size}px ${family}`;
    ctx.textBaseline = "top";
    let text = st.uppercase ? st.content.toUpperCase() : st.content;
    if (st.animation === "typewriter") {
      const reveal = Math.min(Math.max(0.3, c.duration * 0.6), Math.max(0.3, st.content.length * 0.045));
      text = text.slice(0, Math.round((text.length * Math.min(1, local / reveal))));
    }
    const maxW = st.max_width * W;
    const lines: string[] = [];
    for (const para of text.split("\n")) {
      let cur = "";
      for (const w of para.split(" ")) {
        const test = cur ? cur + " " + w : w;
        if (ctx.measureText(test).width <= maxW || !cur) cur = test;
        else {
          lines.push(cur);
          cur = w;
        }
      }
      lines.push(cur);
    }
    const lineH = size * 1.25 * st.line_spacing;
    const blockW = Math.max(...lines.map((l) => ctx.measureText(l).width), 1);
    const blockH = lineH * lines.length;
    const pad = size * 0.35;
    let cx = kfValue(c.keyframes.x, local, c.transform.x) * W;
    let cy = kfValue(c.keyframes.y, local, c.transform.y) * H;
    if (st.animation === "slide_up" || st.animation === "slide_down") {
      const q = 1 - Math.min(local / 0.6, 1);
      cy += (st.animation === "slide_up" ? 1 : -1) * H * 0.06 * q * q;
    }
    let zoom = 1;
    if (st.animation === "zoom") zoom = 0.85 + 0.15 * Math.min(local / 0.6, 1);
    ctx.translate(cx, cy);
    ctx.scale(zoom, zoom);
    const rot = (kfValue(c.keyframes.rotation, local, c.transform.rotation) * Math.PI) / 180;
    if (rot) ctx.rotate(rot);
    ctx.globalAlpha = alpha;
    const x0 = -blockW / 2 - pad;
    const y0 = -blockH / 2 - pad;
    if (st.background) {
      ctx.fillStyle = hexToRgba(st.background);
      const r = size * 0.25;
      const w = blockW + pad * 2;
      const h = blockH + pad * 2;
      ctx.beginPath();
      ctx.roundRect?.(x0, y0, w, h, r);
      if (!ctx.roundRect) ctx.rect(x0, y0, w, h);
      ctx.fill();
    }
    lines.forEach((ln, i) => {
      const lw = ctx.measureText(ln).width;
      const x = st.align === "left" ? -blockW / 2 : st.align === "right" ? blockW / 2 - lw : -lw / 2;
      const y = -blockH / 2 + i * lineH;
      if (st.shadow) {
        ctx.shadowColor = "rgba(0,0,0,0.65)";
        ctx.shadowBlur = size * 0.12;
        ctx.shadowOffsetX = size * 0.04;
        ctx.shadowOffsetY = size * 0.04;
      }
      if (st.stroke_width > 0) {
        ctx.lineWidth = st.stroke_width * size * 2;
        ctx.strokeStyle = hexToRgba(st.stroke_color, "#000");
        ctx.lineJoin = "round";
        ctx.strokeText(ln, x, y);
      }
      ctx.fillStyle = hexToRgba(st.color, "#fff");
      ctx.fillText(ln, x, y);
      ctx.shadowColor = "transparent";
    });
    ctx.restore();
  }
}

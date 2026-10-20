import type { Clip, ColorGrade, Keyframe, MediaItem, Project, TextStyle, Track, TrackKind, Transform } from "../types";

/** Copia profunda que también funciona con borradores de Immer (Proxy). */
export const deepClone = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

export const uid = (prefix = "") => prefix + Math.random().toString(16).slice(2, 14).padEnd(12, "0");

export function fmtTime(t: number, fps = 24, frames = true): string {
  if (!isFinite(t) || t < 0) t = 0;
  const total = Math.floor(t);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const f = Math.floor((t - total) * fps + 1e-6);
  const base = `${h > 0 ? String(h).padStart(2, "0") + ":" : ""}${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return frames ? `${base}:${String(f).padStart(2, "0")}` : base;
}

export function fmtDur(s: number | null | undefined): string {
  if (s == null) return "";
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

export function fmtBytes(n: number | null | undefined): string {
  if (!n) return "";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

export const defaultTransform = (): Transform => ({
  x: 0.5, y: 0.5, scale: 1, rotation: 0, opacity: 1, fit: "cover", flip_h: false, flip_v: false,
  crop: { left: 0, top: 0, right: 0, bottom: 0 },
});

export const defaultGrade = (): ColorGrade => ({
  exposure: 0, contrast: 1, saturation: 1, gamma: 1, temperature: 0, tint: 0, shadows: 0, highlights: 0,
  vignette: 0, grain: 0, sharpen: 0, blur: 0, look: null, lut: null, lut_intensity: 1,
});

export const defaultText = (content = "Tu texto aquí"): TextStyle => ({
  content, font: "Inter", size: 0.08, weight: "bold", color: "#FFFFFF", stroke_color: "#000000", stroke_width: 0,
  shadow: true, background: null, align: "center", line_spacing: 1.15, letter_spacing: 0, max_width: 0.9, animation: "fade", uppercase: false,
});

export function newClip(partial: Partial<Clip> = {}): Clip {
  return {
    id: uid("c_"), kind: "media", media_id: null, name: "", start: 0, duration: 5, in_point: 0, speed: 1, reverse: false,
    volume: 1, muted: false, audio_fade_in: 0, audio_fade_out: 0, fade_in: 0, fade_out: 0, transform: defaultTransform(),
    color: defaultGrade(), effects: [], transition_in: null, motion: { preset: "none", intensity: 0.5 }, keyframes: {},
    text: null, fill: "#000000", label_color: null, locked: false, ...partial,
  };
}

export function newTrack(kind: TrackKind, name: string): Track {
  return { id: uid("t_"), name, kind, clips: [], muted: false, hidden: false, locked: false, solo: false, volume: 1 };
}

export function clipEnd(c: Clip) {
  return c.start + c.duration;
}

export function projectDuration(p: Project): number {
  let end = 0;
  for (const t of p.tracks) for (const c of t.clips) end = Math.max(end, c.start + c.duration);
  return end;
}

export function mediaById(p: Project, id: string | null | undefined): MediaItem | undefined {
  if (!id) return undefined;
  return p.media.find((m) => m.id === id);
}

export function findClip(p: Project, id: string): { track: Track; clip: Clip; ti: number; ci: number } | null {
  for (let ti = 0; ti < p.tracks.length; ti++) {
    const t = p.tracks[ti];
    const ci = t.clips.findIndex((c) => c.id === id);
    if (ci >= 0) return { track: t, clip: t.clips[ci], ti, ci };
  }
  return null;
}

/** Pistas compatibles con un medio. */
export function trackAccepts(track: Track, kind: "video" | "image" | "audio" | "text"): boolean {
  if (track.kind === "text") return kind === "text";
  if (track.kind === "audio") return kind === "audio" || kind === "video";
  return kind === "video" || kind === "image";
}

export function clipFromMedia(m: MediaItem, start: number): Clip {
  const dur = m.kind === "image" ? 5 : Math.max(0.1, m.duration || 5);
  const c = newClip({ media_id: m.id, name: m.name, start, duration: dur });
  return c;
}

/** Divide un clip en ``t`` (tiempo de la línea de tiempo). Devuelve la segunda mitad. */
export function splitClip(c: Clip, t: number): Clip | null {
  if (t <= c.start + 1e-3 || t >= c.start + c.duration - 1e-3) return null;
  const first = t - c.start;
  const second: Clip = deepClone(c);
  second.id = uid("c_");
  second.start = t;
  second.duration = c.duration - first;
  second.in_point = c.in_point + first * c.speed;
  second.transition_in = null;
  second.fade_in = 0;
  second.audio_fade_in = 0;
  // keyframes: desplazar
  for (const key of Object.keys(second.keyframes)) {
    second.keyframes[key] = second.keyframes[key].map((k) => ({ ...k, t: k.t - first })).filter((k) => k.t >= -1e-6);
  }
  c.duration = first;
  c.fade_out = 0;
  c.audio_fade_out = 0;
  for (const key of Object.keys(c.keyframes)) c.keyframes[key] = c.keyframes[key].filter((k) => k.t <= first + 1e-6);
  return second;
}

/** Elimina el clip y desplaza los siguientes de la misma pista para cerrar el hueco. */
export function rippleDelete(track: Track, clipId: string) {
  const c = track.clips.find((x) => x.id === clipId);
  if (!c) return;
  const gap = c.duration;
  const end = c.start + c.duration;
  track.clips = track.clips.filter((x) => x.id !== clipId);
  for (const x of track.clips) if (x.start >= end - 1e-6) x.start = Math.max(0, x.start - gap);
}

export function sortTrack(t: Track) {
  t.clips.sort((a, b) => a.start - b.start);
}

export function ease(p: number, e: Keyframe["easing"]): number {
  switch (e) {
    case "ease_in": return p * p;
    case "ease_out": return 1 - (1 - p) * (1 - p);
    case "ease_in_out": return p * p * (3 - 2 * p);
    case "hold": return 0;
    default: return p;
  }
}

export function kfValue(kfs: Keyframe[] | undefined, t: number, def: number): number {
  if (!kfs || kfs.length === 0) return def;
  const ks = [...kfs].sort((a, b) => a.t - b.t);
  if (t <= ks[0].t) return ks[0].value;
  if (t >= ks[ks.length - 1].t) return ks[ks.length - 1].value;
  for (let i = 0; i < ks.length - 1; i++) {
    const a = ks[i], b = ks[i + 1];
    if (t >= a.t && t <= b.t) {
      const p = ease((t - a.t) / Math.max(1e-6, b.t - a.t), a.easing);
      return a.value + (b.value - a.value) * p;
    }
  }
  return def;
}

/** Puntos de imantado: bordes de clips, cabezal y marcadores. */
export function snapPoints(p: Project, playhead: number, exclude: Set<string>): number[] {
  const pts = [0, playhead];
  for (const t of p.tracks) for (const c of t.clips) if (!exclude.has(c.id)) pts.push(c.start, c.start + c.duration);
  for (const m of p.markers) pts.push(m.t);
  return pts;
}

export function snap(value: number, points: number[], threshold: number): number {
  let best = value;
  let bestD = threshold;
  for (const pt of points) {
    const d = Math.abs(pt - value);
    if (d < bestD) {
      bestD = d;
      best = pt;
    }
  }
  return best;
}

export const ASPECT_PRESETS = [
  { id: "yt4k", label: "YouTube 4K · 16:9", w: 3840, h: 2160, fps: 24 },
  { id: "hd", label: "Full HD · 16:9", w: 1920, h: 1080, fps: 24 },
  { id: "cine", label: "Cine 4K · 2.39:1", w: 4096, h: 1716, fps: 24 },
  { id: "reels", label: "Reels / TikTok · 9:16", w: 1080, h: 1920, fps: 30 },
  { id: "feed", label: "Feed Instagram · 4:5", w: 1080, h: 1350, fps: 30 },
  { id: "square", label: "Cuadrado · 1:1", w: 1080, h: 1080, fps: 30 },
  { id: "tv", label: "TV Europa · 25 fps", w: 1920, h: 1080, fps: 25 },
];

export function aspectId(w: number, h: number): string {
  const r = w / h;
  const table: [string, number][] = [["16:9", 16 / 9], ["9:16", 9 / 16], ["1:1", 1], ["4:5", 0.8], ["4:3", 4 / 3], ["2.39:1", 2.39], ["21:9", 21 / 9], ["1.85:1", 1.85]];
  let best = table[0];
  for (const x of table) if (Math.abs(x[1] - r) < Math.abs(best[1] - r)) best = x;
  return best[0];
}

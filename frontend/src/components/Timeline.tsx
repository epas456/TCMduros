import { Eye, EyeOff, Lock, LockOpen, Magnet, MousePointer2, Palette, Plus, Scissors, SlidersHorizontal, Trash2, Type, Volume2, VolumeX, ZoomIn, ZoomOut } from "lucide-react";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { api, urls } from "../api";
import { clipFromMedia, defaultText, fmtTime, mediaById, newClip, newTrack, projectDuration, snap, snapPoints, sortTrack, splitClip, trackAccepts } from "../lib/timeline";
import { useStore } from "../store";
import type { Clip, MediaItem, Project, Track } from "../types";
import { deleteSelection, splitAtPlayhead } from "./Editor";
import { IconButton } from "./ui";

const LANE_H: Record<Track["kind"], number> = { video: 62, audio: 50, text: 38 };

function niceStep(pps: number): number {
  const steps = [1 / 24, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200];
  return steps.find((s) => s * pps >= 80) ?? 1200;
}

const peaksCache = new Map<string, Promise<{ pps: number; peaks: number[] }>>();

function Waveform({ project, media, clip, width, height }: { project: Project; media: MediaItem; clip: Clip; width: number; height: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!media.waveform) return;
    const key = `${project.id}/${media.id}`;
    if (!peaksCache.has(key)) peaksCache.set(key, fetch(urls.file(project.id, media.waveform)).then((r) => r.json()));
    let alive = true;
    void peaksCache.get(key)!.then((data) => {
      const cv = ref.current;
      if (!alive || !cv) return;
      const w = Math.max(1, Math.min(4000, Math.floor(width)));
      cv.width = w;
      cv.height = height;
      const ctx = cv.getContext("2d")!;
      ctx.clearRect(0, 0, w, height);
      ctx.fillStyle = "rgba(220,255,240,0.75)";
      const srcStart = clip.in_point;
      const srcDur = clip.duration * clip.speed;
      for (let x = 0; x < w; x++) {
        const t = srcStart + (x / w) * srcDur;
        const i = Math.floor(t * data.pps);
        const v = data.peaks[i] ?? 0;
        const h = Math.max(1, v * height * clip.volume);
        ctx.fillRect(x, (height - h) / 2, 1, h);
      }
    });
    return () => {
      alive = false;
    };
  }, [project.id, media.id, media.waveform, clip.in_point, clip.duration, clip.speed, clip.volume, width, height]);
  return <canvas ref={ref} className="clip-wave" style={{ width, height }} />;
}

const ClipView = memo(function ClipView({ project, track, clip, pps, selected, onDown }: {
  project: Project; track: Track; clip: Clip; pps: number; selected: boolean;
  onDown: (e: React.PointerEvent, clip: Clip, track: Track, mode: "move" | "l" | "r") => void;
}) {
  const m = mediaById(project, clip.media_id);
  const kind = clip.kind === "media" ? (m?.kind ?? "video") : clip.kind;
  const left = clip.start * pps;
  const width = Math.max(4, clip.duration * pps);
  const style: React.CSSProperties = { left, width };
  if (m && (m.kind === "video" || m.kind === "image") && m.thumbnail && track.kind !== "audio") style.backgroundImage = `url(${urls.file(project.id, m.thumbnail)})`;
  if (clip.label_color) style.backgroundColor = clip.label_color;
  const label = clip.kind === "text" ? clip.text?.content : clip.kind === "color" ? `Color ${clip.fill}` : clip.kind === "adjustment" ? "Capa de ajuste" : clip.name || m?.name;
  const h = LANE_H[track.kind] - 6;
  return (
    <div className={`clip k-${track.kind === "audio" && kind === "video" ? "audio" : kind} ${selected ? "sel" : ""}`} style={style}
      onPointerDown={(e) => onDown(e, clip, track, "move")} title={label ?? ""}>
      {clip.transition_in && <div className="clip-trans" style={{ width: Math.min(width, clip.transition_in.duration * pps) }} />}
      {m && m.has_audio && (track.kind === "audio" || m.kind === "audio") && width > 6 && <Waveform project={project} media={m} clip={clip} width={width} height={Math.round(h * 0.6)} />}
      <div className="clip-label">{label}</div>
      <div className="clip-badges">
        {m?.ai_generated && <span className="badge badge-ai">IA</span>}
        {clip.speed !== 1 && <span className="badge">{clip.speed.toFixed(2)}×</span>}
        {clip.reverse && <span className="badge">◀</span>}
        {Object.values(clip.keyframes).some((k) => k.length) && <span className="badge">◆</span>}
        {clip.color.look && <span className="badge">LUT</span>}
        {clip.muted && <span className="badge">🔇</span>}
      </div>
      {!track.locked && <div className="clip-handle l" onPointerDown={(e) => { e.stopPropagation(); onDown(e, clip, track, "l"); }} />}
      {!track.locked && <div className="clip-handle r" onPointerDown={(e) => { e.stopPropagation(); onDown(e, clip, track, "r"); }} />}
    </div>
  );
});

function Playhead({ pps }: { pps: number }) {
  const t = useStore((s) => s.playhead);
  return <div className="playhead" style={{ left: t * pps }} />;
}

function AutoScroll({ scroller, pps }: { scroller: React.RefObject<HTMLDivElement>; pps: number }) {
  const t = useStore((s) => s.playhead);
  const playing = useStore((s) => s.playing);
  useEffect(() => {
    const el = scroller.current;
    if (!el || !playing) return;
    const x = t * pps;
    if (x > el.scrollLeft + el.clientWidth - 60) el.scrollLeft = x - 80;
  }, [t, playing, pps, scroller]);
  return null;
}

export default function Timeline() {
  const project = useStore((s) => s.project)!;
  const pps = useStore((s) => s.pps);
  const selection = useStore((s) => s.selection);
  const tool = useStore((s) => s.tool);
  const snapping = useStore((s) => s.snapping);
  const inPoint = useStore((s) => s.inPoint);
  const outPoint = useStore((s) => s.outPoint);
  const scroller = useRef<HTMLDivElement>(null);
  const headsRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ left: 0, width: 1200 });
  const [dropLane, setDropLane] = useState<string | null>(null);
  const [snapLine, setSnapLine] = useState<number | null>(null);
  const st = useStore.getState();
  const sel = useMemo(() => new Set(selection), [selection]);
  const dur = projectDuration(project);
  const totalW = Math.max(view.width, (dur + 30) * pps);

  const display = useMemo(() => {
    const vis = project.tracks.filter((t) => t.kind !== "audio").reverse();
    const aud = project.tracks.filter((t) => t.kind === "audio");
    return [...vis, ...aud];
  }, [project.tracks]);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const onScroll = () => {
      setView({ left: el.scrollLeft, width: el.clientWidth });
      if (headsRef.current) headsRef.current.scrollTop = el.scrollTop;
    };
    onScroll();
    el.addEventListener("scroll", onScroll);
    const ro = new ResizeObserver(onScroll);
    ro.observe(el);
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const rect = el.getBoundingClientRect();
        const tAt = (e.clientX - rect.left + el.scrollLeft) / useStore.getState().pps;
        const f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
        const np = Math.min(800, Math.max(4, useStore.getState().pps * f));
        useStore.getState().setPps(np);
        requestAnimationFrame(() => (el.scrollLeft = tAt * np - (e.clientX - rect.left)));
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      el.removeEventListener("scroll", onScroll);
      el.removeEventListener("wheel", onWheel);
      ro.disconnect();
    };
  }, []);

  // al abrir un proyecto, encajar toda la pieza en la vista
  useEffect(() => {
    const el = scroller.current;
    if (!el || dur <= 0) return;
    if (dur * useStore.getState().pps > el.clientWidth - 40) {
      useStore.getState().setPps(Math.max(4, (el.clientWidth - 40) / dur));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  const step = niceStep(pps);
  const ticks: { t: number; major: boolean }[] = [];
  const t0 = Math.max(0, Math.floor(view.left / pps / step) * step);
  const t1 = (view.left + view.width) / pps + step;
  for (let t = t0; t <= t1; t += step / 4) {
    const major = Math.abs(t / step - Math.round(t / step)) < 1e-6;
    ticks.push({ t, major });
  }

  // ------------------------------------------------------------ interacción con el cabezal
  function scrub(e: React.PointerEvent) {
    const el = scroller.current!;
    const rect = el.getBoundingClientRect();
    const toTime = (cx: number) => Math.max(0, (cx - rect.left + el.scrollLeft) / useStore.getState().pps);
    st.setPlaying(false);
    st.setPlayhead(toTime(e.clientX));
    const move = (ev: PointerEvent) => st.setPlayhead(toTime(ev.clientX));
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  // ------------------------------------------------------------ arrastrar / recortar clips
  function onClipDown(e: React.PointerEvent, clip: Clip, track: Track, mode: "move" | "l" | "r") {
    if (e.button !== 0) return;
    e.preventDefault();
    const s = useStore.getState();
    const el = scroller.current!;
    const rect = el.getBoundingClientRect();
    const timeAt = (cx: number) => (cx - rect.left + el.scrollLeft) / s.pps;
    if (s.tool === "razor" && mode === "move") {
      const t = timeAt(e.clientX);
      s.edit((p) => {
        const tr = p.tracks.find((x) => x.id === track.id)!;
        const c = tr.clips.find((x) => x.id === clip.id)!;
        const second = splitClip(c, t);
        if (second) {
          tr.clips.push(second);
          sortTrack(tr);
        }
      });
      return;
    }
    if (track.locked) {
      s.select([clip.id], e.shiftKey);
      return;
    }
    let ids = s.selection;
    if (!sel.has(clip.id)) {
      ids = e.shiftKey ? [...s.selection, clip.id] : [clip.id];
      s.select(ids);
    } else if (e.shiftKey) {
      s.select([clip.id], true);
      return;
    }
    const startX = e.clientX;
    const p0 = s.project!;
    const originals = new Map<string, { start: number; duration: number; in_point: number; trackId: string }>();
    for (const t of p0.tracks) for (const c of t.clips) if (ids.includes(c.id) || c.id === clip.id) originals.set(c.id, { start: c.start, duration: c.duration, in_point: c.in_point, trackId: t.id });
    const media = mediaById(p0, clip.media_id);
    const pts = s.snapping ? snapPoints(p0, s.playhead, new Set(originals.keys())) : [];
    const thr = 8 / s.pps;
    let moved = false;
    s.beginGesture();
    const move = (ev: PointerEvent) => {
      const dt = (ev.clientX - startX) / s.pps;
      if (!moved && Math.abs(ev.clientX - startX) < 3) return;
      moved = true;
      const o = originals.get(clip.id)!;
      let snapAt: number | null = null;
      s.edit((p) => {
        if (mode === "move") {
          let d = dt;
          if (pts.length) {
            const a = snap(o.start + dt, pts, thr);
            const b = snap(o.start + o.duration + dt, pts, thr);
            if (a !== o.start + dt) { d = a - o.start; snapAt = a; }
            else if (b !== o.start + o.duration + dt) { d = b - o.start - o.duration; snapAt = b; }
          }
          const minStart = Math.min(...[...originals.values()].map((x) => x.start));
          d = Math.max(-minStart, d);
          // cambio de pista vertical (sólo un clip)
          let targetTrack: Track | null = null;
          if (originals.size === 1) {
            const lanes = document.querySelectorAll<HTMLElement>(".tl-lane");
            lanes.forEach((ln) => {
              const r = ln.getBoundingClientRect();
              if (ev.clientY >= r.top && ev.clientY < r.bottom) targetTrack = p.tracks.find((t) => t.id === ln.dataset.track) ?? null;
            });
          }
          for (const [id, orig] of originals) {
            const srcTrack = p.tracks.find((t) => t.id === orig.trackId)!;
            const idx = srcTrack.clips.findIndex((c) => c.id === id);
            let c: Clip;
            let curTrack = srcTrack;
            if (idx >= 0) c = srcTrack.clips[idx];
            else {
              curTrack = p.tracks.find((t) => t.clips.some((x) => x.id === id))!;
              c = curTrack.clips.find((x) => x.id === id)!;
            }
            c.start = Math.max(0, orig.start + d);
            const tt = targetTrack as Track | null;
            if (tt && tt.id !== curTrack.id && !tt.locked) {
              const mk = c.kind === "media" ? (mediaById(p, c.media_id)?.kind ?? "video") : c.kind === "text" ? "text" : "video";
              if (trackAccepts(tt, mk as "video")) {
                curTrack.clips = curTrack.clips.filter((x) => x.id !== id);
                tt.clips.push(c);
              }
            }
          }
        } else {
          const f = p.tracks.flatMap((t) => t.clips).find((c) => c.id === clip.id)!;
          const srcMax = media && media.kind !== "image" && media.duration ? media.duration : Infinity;
          if (mode === "l") {
            let ns = o.start + dt;
            if (pts.length) { const sn = snap(ns, pts, thr); if (sn !== ns) snapAt = sn; ns = sn; }
            const minByMedia = srcMax === Infinity ? 0 : o.start - o.in_point / clip.speed;
            ns = Math.max(Math.max(0, minByMedia), Math.min(ns, o.start + o.duration - 0.05));
            f.start = ns;
            f.duration = o.duration - (ns - o.start);
            if (f.kind === "media") f.in_point = Math.max(0, o.in_point + (ns - o.start) * clip.speed);
          } else {
            let ne = o.start + o.duration + dt;
            if (pts.length) { const sn = snap(ne, pts, thr); if (sn !== ne) snapAt = sn; ne = sn; }
            const maxDur = srcMax === Infinity ? Infinity : (srcMax - o.in_point) / clip.speed;
            f.duration = Math.max(0.05, Math.min(ne - o.start, maxDur));
          }
        }
        for (const t of p.tracks) sortTrack(t);
      }, false);
      setSnapLine(snapAt);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setSnapLine(null);
      s.endGesture();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  // ------------------------------------------------------------ soltar medios
  function onDrop(e: React.DragEvent, track: Track) {
    e.preventDefault();
    setDropLane(null);
    const mid = e.dataTransfer.getData("text/x-durostcm-media");
    if (!mid) return;
    const m = mediaById(project, mid);
    if (!m) return;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    let t = Math.max(0, (e.clientX - rect.left) / pps);
    if (snapping) t = snap(t, snapPoints(project, useStore.getState().playhead, new Set()), 10 / pps);
    let target = track;
    if (!trackAccepts(track, m.kind)) {
      const alt = project.tracks.find((x) => trackAccepts(x, m.kind) && !x.locked);
      if (!alt) return;
      target = alt;
    }
    const clip = clipFromMedia(m, t);
    st.edit((p) => {
      const tr = p.tracks.find((x) => x.id === target.id)!;
      tr.clips.push(clip);
      sortTrack(tr);
    });
    st.select([clip.id]);
  }

  // ------------------------------------------------------------ acciones de barra
  function addTrack(kind: Track["kind"]) {
    st.edit((p) => {
      const n = p.tracks.filter((t) => t.kind === kind).length + 1;
      const name = kind === "video" ? `V${n}` : kind === "audio" ? `A${n}` : `Texto ${n}`;
      const t = newTrack(kind, name);
      if (kind === "audio") p.tracks.push(t);
      else {
        const lastVis = p.tracks.map((x) => x.kind !== "audio").lastIndexOf(true);
        p.tracks.splice(lastVis + 1, 0, t);
      }
    });
  }

  function addSpecial(kind: "text" | "color" | "adjustment") {
    const t = useStore.getState().playhead;
    const clip = kind === "text"
      ? newClip({ kind: "text", start: t, duration: 4, name: "Texto", text: defaultText() })
      : newClip({ kind, start: t, duration: 5, name: kind === "color" ? "Color" : "Ajuste", fill: "#101820" });
    st.edit((p) => {
      let tr = kind === "text" ? p.tracks.find((x) => x.kind === "text") : [...p.tracks].reverse().find((x) => x.kind === "video");
      if (!tr) {
        tr = newTrack(kind === "text" ? "text" : "video", kind === "text" ? "Títulos" : "V");
        p.tracks.push(tr);
      }
      tr.clips.push(clip);
      sortTrack(tr);
    });
    st.select([clip.id]);
  }

  function fit() {
    const el = scroller.current;
    if (!el) return;
    st.setPps((el.clientWidth - 40) / Math.max(5, dur));
    el.scrollLeft = 0;
  }

  return (
    <>
      <div className="tl-toolbar">
        <IconButton title="Selección (V)" active={tool === "select"} onClick={() => st.set({ tool: "select" })}><MousePointer2 size={16} /></IconButton>
        <IconButton title="Cuchilla (C)" active={tool === "razor"} onClick={() => st.set({ tool: "razor" })}><Scissors size={16} /></IconButton>
        <IconButton title="Imantado (N)" active={snapping} onClick={() => st.set({ snapping: !snapping })}><Magnet size={16} /></IconButton>
        <span className="sep" style={{ width: 1, height: 20, margin: "0 4px" }} />
        <IconButton title="Dividir en el cabezal (S)" onClick={splitAtPlayhead}><Scissors size={15} style={{ transform: "rotate(90deg)" }} /></IconButton>
        <IconButton title="Eliminar (Supr) · Shift+Supr: eliminar cerrando hueco" disabled={!selection.length} onClick={() => deleteSelection()}><Trash2 size={15} /></IconButton>
        <span className="sep" style={{ width: 1, height: 20, margin: "0 4px" }} />
        <IconButton title="Añadir texto (T)" onClick={() => addSpecial("text")}><Type size={15} /></IconButton>
        <IconButton title="Añadir fondo de color" onClick={() => addSpecial("color")}><Palette size={15} /></IconButton>
        <IconButton title="Añadir capa de ajuste (etalonaje global)" onClick={() => addSpecial("adjustment")}><SlidersHorizontal size={15} /></IconButton>
        <span className="sep" style={{ width: 1, height: 20, margin: "0 4px" }} />
        <button className="btn btn-ghost btn-sm" onClick={() => addTrack("video")}><Plus size={13} /> Vídeo</button>
        <button className="btn btn-ghost btn-sm" onClick={() => addTrack("audio")}><Plus size={13} /> Audio</button>
        <button className="btn btn-ghost btn-sm" onClick={() => addTrack("text")}><Plus size={13} /> Texto</button>
        <div className="spacer" />
        <span className="small muted mono">{fmtTime(dur, project.settings.fps, false)}</span>
        <IconButton title="Alejar (-)" onClick={() => st.setPps(pps / 1.25)}><ZoomOut size={15} /></IconButton>
        <input type="range" min={4} max={800} step={1} value={pps} onChange={(e) => st.setPps(+e.target.value)} style={{ width: 110 }} aria-label="Zoom" />
        <IconButton title="Acercar (+)" onClick={() => st.setPps(pps * 1.25)}><ZoomIn size={15} /></IconButton>
        <button className="btn btn-ghost btn-sm" onClick={fit}>Ajustar</button>
      </div>
      <div className={`tl-body ${tool === "razor" ? "razor-cursor" : ""}`}>
        <div className="tl-heads" ref={headsRef}>
          <div className="tl-ruler-head small muted">Pistas</div>
          {display.map((t) => (
            <div key={t.id} className="tl-track-head" style={{ height: LANE_H[t.kind] }}>
              <input className="tname" value={t.name} onChange={(e) => st.edit((p) => { p.tracks.find((x) => x.id === t.id)!.name = e.target.value; }, false)} />
              {t.kind !== "audio" && (
                <IconButton title={t.hidden ? "Mostrar" : "Ocultar"} onClick={() => st.edit((p) => { const x = p.tracks.find((y) => y.id === t.id)!; x.hidden = !x.hidden; })}>
                  {t.hidden ? <EyeOff size={13} /> : <Eye size={13} />}
                </IconButton>
              )}
              {t.kind !== "text" && (
                <IconButton title={t.muted ? "Activar audio" : "Silenciar pista"} active={t.muted} onClick={() => st.edit((p) => { const x = p.tracks.find((y) => y.id === t.id)!; x.muted = !x.muted; })}>
                  {t.muted ? <VolumeX size={13} /> : <Volume2 size={13} />}
                </IconButton>
              )}
              {t.kind !== "text" && (
                <IconButton title="Solo" active={t.solo} onClick={() => st.edit((p) => { const x = p.tracks.find((y) => y.id === t.id)!; x.solo = !x.solo; })}>
                  <b style={{ fontSize: 10 }}>S</b>
                </IconButton>
              )}
              <IconButton title={t.locked ? "Desbloquear" : "Bloquear"} active={t.locked} onClick={() => st.edit((p) => { const x = p.tracks.find((y) => y.id === t.id)!; x.locked = !x.locked; })}>
                {t.locked ? <Lock size={13} /> : <LockOpen size={13} />}
              </IconButton>
              {t.clips.length === 0 && project.tracks.length > 1 && (
                <IconButton title="Eliminar pista vacía" onClick={() => st.edit((p) => { p.tracks = p.tracks.filter((x) => x.id !== t.id); })}><Trash2 size={12} /></IconButton>
              )}
            </div>
          ))}
        </div>
        <div className="tl-scroll" ref={scroller} onPointerDown={(e) => { if (e.target === e.currentTarget) st.select([]); }}>
          <div style={{ width: totalW, position: "relative", minHeight: "100%" }}>
            <div className="tl-ruler" onPointerDown={scrub}>
              {ticks.map(({ t, major }) => (
                <div key={t.toFixed(4)} className={`tick ${major ? "" : "minor"}`} style={{ left: t * pps }}>
                  {major ? fmtTime(t, project.settings.fps, step < 1) : ""}
                </div>
              ))}
              {inPoint != null && outPoint != null && outPoint > inPoint && (
                <div className="inout" style={{ left: inPoint * pps, width: (outPoint - inPoint) * pps }} />
              )}
              {project.markers.map((m) => (
                <div key={m.id} className="marker" style={{ left: m.t * pps, background: m.color }} title={`${m.label} — Alt+clic para borrar`}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    if (e.altKey) st.edit((p) => { p.markers = p.markers.filter((x) => x.id !== m.id); });
                    else st.setPlayhead(m.t);
                  }} />
              ))}
            </div>
            {display.map((t) => (
              <div key={t.id} data-track={t.id} className={`tl-lane kind-${t.kind} ${dropLane === t.id ? "drop" : ""}`} style={{ height: LANE_H[t.kind], opacity: t.hidden ? 0.45 : 1 }}
                onDragOver={(e) => { if (e.dataTransfer.types.includes("text/x-durostcm-media")) { e.preventDefault(); setDropLane(t.id); } }}
                onDragLeave={() => setDropLane(null)}
                onDrop={(e) => onDrop(e, t)}
                onPointerDown={(e) => { if (e.target === e.currentTarget) { st.select([]); scrub(e); } }}>
                {t.clips.map((c) => (
                  <ClipView key={c.id} project={project} track={t} clip={c} pps={pps} selected={sel.has(c.id)} onDown={onClipDown} />
                ))}
              </div>
            ))}
            <Playhead pps={pps} />
            {snapLine != null && <div className="snap-line" style={{ left: snapLine * pps }} />}
          </div>
        </div>
      </div>
      <AutoScroll scroller={scroller} pps={pps} />
    </>
  );
}

export async function uploadFiles(pid: string, files: FileList | File[]) {
  const fd = new FormData();
  for (const f of Array.from(files)) fd.append("files", f);
  return api.form<{ media: MediaItem[]; errors: { file: string; error: string }[] }>(`/api/projects/${pid}/media`, fd);
}

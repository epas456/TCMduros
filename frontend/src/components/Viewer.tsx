import { Activity, Camera, Grid3x3, Maximize, Pause, Play, Repeat, SkipBack, SkipForward, Volume2, VolumeX, Wand2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, urls } from "../api";
import { fmtTime, projectDuration } from "../lib/timeline";
import { Compositor } from "../player/compositor";
import { useStore } from "../store";
import type { Job } from "../types";
import Scopes from "./Scopes";
import { Button, IconButton, Modal, Select, Spinner } from "./ui";

const getters = new WeakMap<object, () => HTMLCanvasElement | null>();
function canvasGetter(ref: React.RefObject<HTMLCanvasElement>) {
  let g = getters.get(ref);
  if (!g) {
    g = () => ref.current;
    getters.set(ref, g);
  }
  return g;
}

export default function Viewer() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const comp = useRef<Compositor | null>(null);
  const project = useStore((s) => s.project);
  const playing = useStore((s) => s.playing);
  const playhead = useStore((s) => s.playhead);
  const inPoint = useStore((s) => s.inPoint);
  const outPoint = useStore((s) => s.outPoint);
  const [quality, setQuality] = useState<"0.5" | "1" | "0.25">("0.5");
  const [guides, setGuides] = useState(false);
  const [scopes, setScopes] = useState(false);
  const [muted, setMuted] = useState(false);
  const [loop, setLoop] = useState(false);
  const [exact, setExact] = useState<{ url?: string; job?: string; frame?: string } | null>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });

  useEffect(() => {
    const c = new Compositor(canvasRef.current!);
    comp.current = c;
    (window as unknown as { __durostcmCompositor?: Compositor }).__durostcmCompositor = c;
    c.onTime = (t) => useStore.getState().setPlayhead(t);
    c.onEnd = () => useStore.getState().setPlaying(false);
    return () => c.destroy();
  }, []);

  useEffect(() => {
    comp.current?.setScale(parseFloat(quality));
  }, [quality]);

  useEffect(() => {
    comp.current?.setProject(project);
  }, [project]);

  useEffect(() => {
    const c = comp.current;
    if (!c) return;
    if (playing && !c.playing) {
      c.seek(useStore.getState().playhead);
      c.play();
    } else if (!playing && c.playing) c.pause();
  }, [playing]);

  useEffect(() => {
    const c = comp.current;
    if (!c) return;
    if (!c.playing || Math.abs(c.time - playhead) > 0.25) c.seek(playhead);
  }, [playhead]);

  useEffect(() => {
    if (comp.current) comp.current.muted = muted;
  }, [muted]);

  useEffect(() => {
    if (comp.current) comp.current.loopRange = loop && inPoint != null && outPoint != null && outPoint > inPoint ? [inPoint, outPoint] : null;
  }, [loop, inPoint, outPoint]);

  // tamaño del lienzo dentro del escenario (para las guías)
  useEffect(() => {
    const el = stageRef.current;
    if (!el || !project) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      const aw = r.width - 28;
      const ah = r.height - 28;
      const ar = project.settings.width / project.settings.height;
      const w = Math.min(aw, ah * ar);
      setBox({ w, h: w / ar });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [project?.settings.width, project?.settings.height]);

  // seguimiento de la previsualización exacta
  const jobs = useStore((s) => s.jobs);
  useEffect(() => {
    if (!exact?.job || !project) return;
    const j: Job | undefined = jobs[exact.job];
    if (j?.status === "done" && j.result?.path) setExact({ url: urls.file(project.id, j.result.path) });
    if (j?.status === "error") setExact(null);
  }, [jobs, exact?.job, project]);

  if (!project) return null;
  const dur = projectDuration(project);
  const getCanvas = canvasGetter(canvasRef);
  const st = useStore.getState();

  async function exactPreview() {
    if (!project) return;
    const start = inPoint != null && outPoint != null && outPoint > inPoint ? inPoint : Math.max(0, playhead - 1);
    const end = inPoint != null && outPoint != null && outPoint > inPoint ? outPoint : Math.min(dur || start + 5, start + 6);
    const j = await api.post(`/api/projects/${project.id}/render`, { format: "mp4_h264", preview: true, start, end });
    setExact({ job: j.id });
  }

  return (
    <>
      <div className="viewer-bar">
        <span className="small muted">Visor</span>
        <Select value={quality} onChange={setQuality} options={[
          { value: "0.25", label: "Calidad ¼" }, { value: "0.5", label: "Calidad ½" }, { value: "1", label: "Calidad completa" },
        ]} className="grow" />
        <IconButton title="Guías de zona segura y tercios" active={guides} onClick={() => setGuides(!guides)}><Grid3x3 size={16} /></IconButton>
        <IconButton title="Monitores de color: histograma, forma de onda y vectorscopio" active={scopes} onClick={() => setScopes(!scopes)}><Activity size={16} /></IconButton>
        <IconButton title="Fotograma exacto del render final" onClick={() => setExact({ frame: urls.frame(project.id, playhead, 1080) + `&_=${Date.now()}` })}><Camera size={16} /></IconButton>
        <Button size="sm" icon={<Wand2 size={14} />} onClick={() => void exactPreview()} title="Renderiza con FFmpeg el tramo de entrada/salida (o 6 s alrededor del cabezal) para ver el resultado exacto">
          Previa exacta
        </Button>
        <IconButton title="Pantalla completa" onClick={() => canvasRef.current?.requestFullscreen?.()}><Maximize size={16} /></IconButton>
      </div>
      <div className="viewer-stage" ref={stageRef} onDoubleClick={() => st.setPlaying(!st.playing)}>
        <canvas ref={canvasRef} className="viewer-canvas" style={{ width: box.w || undefined, height: box.h || undefined }} />
        {guides && box.w > 0 && (
          <div className="safe-guides" style={{ width: box.w, height: box.h }}>
            <div className="g-thirds" /><div className="g-action" /><div className="g-title" />
          </div>
        )}
        {scopes && <Scopes source={getCanvas} />}
        {dur === 0 && (
          <div style={{ position: "absolute", textAlign: "center", color: "var(--muted)", maxWidth: 380 }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-2)", marginBottom: 6 }}>Tu línea de tiempo está vacía</div>
            Arrastra medios desde la biblioteca, genera planos en el <b>Estudio IA</b> o deja que el <b>Director IA</b> cree la pieza completa.
          </div>
        )}
      </div>
      <div className="transport">
        <IconButton title="Inicio (Home)" onClick={() => st.setPlayhead(0)}><SkipBack size={16} /></IconButton>
        <IconButton title="Fotograma anterior (←)" onClick={() => st.setPlayhead(playhead - 1 / project.settings.fps)}>‹</IconButton>
        <button className="play-btn" title="Reproducir / pausa (Espacio)" onClick={() => st.setPlaying(!playing)}>
          {playing ? <Pause size={18} /> : <Play size={18} style={{ marginLeft: 2 }} />}
        </button>
        <IconButton title="Fotograma siguiente (→)" onClick={() => st.setPlayhead(playhead + 1 / project.settings.fps)}>›</IconButton>
        <IconButton title="Final (End)" onClick={() => st.setPlayhead(dur)}><SkipForward size={16} /></IconButton>
        <span className="timecode">{fmtTime(playhead, project.settings.fps)}</span>
        <span className="small muted mono">/ {fmtTime(dur, project.settings.fps)}</span>
        <div className="spacer" />
        {inPoint != null && <span className="badge badge-info">E {fmtTime(inPoint, project.settings.fps)}</span>}
        {outPoint != null && <span className="badge badge-info">S {fmtTime(outPoint, project.settings.fps)}</span>}
        <IconButton title="Bucle entre entrada y salida (I / O)" active={loop} onClick={() => setLoop(!loop)}><Repeat size={16} /></IconButton>
        <IconButton title={muted ? "Activar sonido" : "Silenciar"} onClick={() => setMuted(!muted)}>{muted ? <VolumeX size={16} /> : <Volume2 size={16} />}</IconButton>
      </div>
      {exact && (
        <Modal title={exact.frame ? "Fotograma exacto (render FFmpeg)" : "Previsualización exacta"} wide onClose={() => setExact(null)}>
          {exact.frame ? (
            <img src={exact.frame} style={{ width: "100%", borderRadius: 8 }} alt="Fotograma renderizado" />
          ) : exact.url ? (
            <video src={exact.url} controls autoPlay style={{ width: "100%", borderRadius: 8, background: "#000" }} />
          ) : (
            <div className="row" style={{ justifyContent: "center", padding: 40 }}>
              <Spinner size={22} /> <span>Renderizando con FFmpeg… {Math.round((jobs[exact.job!]?.progress ?? 0) * 100)}%</span>
            </div>
          )}
        </Modal>
      )}
    </>
  );
}

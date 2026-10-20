import { Download, FileJson, FileText, Film, Import, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, urls } from "../api";
import { fmtBytes, fmtTime, projectDuration } from "../lib/timeline";
import { useStore } from "../store";
import { Badge, Button, Field, IconButton, Modal, Progress, Select, Tabs, Toggle } from "./ui";

interface RenderFile { name: string; path: string; size_bytes: number; time: number }

export default function ExportDialog() {
  const project = useStore((s) => s.project)!;
  const presets = useStore((s) => s.presets);
  const jobs = useStore((s) => s.jobs);
  const inPoint = useStore((s) => s.inPoint);
  const outPoint = useStore((s) => s.outPoint);
  const [format, setFormat] = useState("mp4_h264");
  const [kindTab, setKindTab] = useState<"video" | "master" | "web" | "image" | "audio">("video");
  const [res, setRes] = useState<string>("project");
  const [w, setW] = useState(project.settings.width);
  const [h, setH] = useState(project.settings.height);
  const [fps, setFps] = useState<string>("project");
  const [quality, setQuality] = useState("high");
  const [reframe, setReframe] = useState("blur_fill");
  const [range, setRange] = useState<"all" | "inout">(inPoint != null && outPoint != null && outPoint > inPoint ? "inout" : "all");
  const [loudness, setLoudness] = useState<string>("-14");
  const [transparent, setTransparent] = useState(false);
  const [aiMark, setAiMark] = useState(false);
  const [aiMeta, setAiMeta] = useState(true);
  const [subs, setSubs] = useState(true);
  const [title, setTitle] = useState(project.name);
  const [author, setAuthor] = useState("");
  const [copyright, setCopyright] = useState("");
  const [filename, setFilename] = useState("");
  const [renders, setRenders] = useState<RenderFile[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const st = useStore.getState();
  const close = () => st.set({ exportOpen: false });

  const loadRenders = () => api.get<{ renders: RenderFile[] }>(`/api/projects/${project.id}/renders`).then((r) => setRenders(r.renders)).catch(() => undefined);
  useEffect(() => {
    void loadRenders();
    api.get("/api/settings").then((s) => { setAiMark(s.ethics.ai_label_watermark); setAiMeta(s.ethics.ai_label_metadata); }).catch(() => undefined);
  }, []);
  const job = jobId ? jobs[jobId] : null;
  useEffect(() => {
    if (job?.status === "done") void loadRenders();
  }, [job?.status]);

  const groups: Record<string, string[]> = {
    video: ["mp4_h264", "mp4_h265", "mp4_av1", "mp4_h264_nvenc", "mp4_hevc_nvenc", "mp4_av1_nvenc", "mp4_hevc_videotoolbox", "mp4_hevc_qsv"],
    master: ["mov_prores_422hq", "mov_prores_4444", "mov_prores_proxy", "mov_prores_videotoolbox", "mxf_dnxhr_hq", "mov_dnxhr_444", "mkv_h264_lossless"],
    web: ["webm_vp9", "webm_vp9_alpha", "gif"],
    image: ["png_still", "jpg_still", "png_sequence", "jpg_sequence"],
    audio: ["wav", "mp3", "flac", "m4a"],
  };
  const fmts = useMemo(() => (presets?.formats ?? []).filter((f) => groups[kindTab].includes(f.id)), [presets, kindTab]);
  const fmt = presets?.formats.find((f) => f.id === format);
  const dims = res === "project" ? { w: project.settings.width, h: project.settings.height } : res === "custom" ? { w, h } : (() => {
    const r = presets?.resolutions.find((x) => x.id === res);
    if (!r) return { w: project.settings.width, h: project.settings.height };
    const portrait = project.settings.height > project.settings.width;
    return portrait ? { w: r.h, h: r.w } : { w: r.w, h: r.h };
  })();
  const aspectDiffers = Math.abs(dims.w / dims.h - project.settings.width / project.settings.height) > 0.01;
  const dur = projectDuration(project);
  const chapters = [{ t: 0, label: "Inicio" }, ...[...project.markers].sort((a, b) => a.t - b.t).filter((m) => m.t > 0.5).map((m) => ({ t: m.t, label: m.label }))]
    .map((c) => `${fmtTime(c.t, project.settings.fps, false)} ${c.label}`).join("\n");

  function applyPlatform(id: string) {
    const p = presets?.platforms.find((x) => x.id === id);
    if (!p) return;
    setFormat(p.format);
    setKindTab(Object.entries(groups).find(([, v]) => v.includes(p.format))?.[0] as any ?? "video");
    setRes("custom");
    setW(p.w);
    setH(p.h);
    setFps(p.fps ? String(p.fps) : "project");
    setLoudness(p.loudness != null ? String(p.loudness) : "off");
    setQuality(p.quality);
  }

  async function start() {
    const body = {
      format, quality, reframe, transparent, title, author, copyright,
      width: dims.w, height: dims.h, fps: fps === "project" ? null : parseFloat(fps),
      start: range === "inout" && inPoint != null ? inPoint : 0,
      end: range === "inout" && outPoint != null ? outPoint : null,
      loudness: loudness === "off" ? null : parseFloat(loudness),
      ai_watermark: aiMark, ai_metadata: aiMeta, subtitles_sidecar: subs,
      filename: filename.trim() || null,
    };
    try {
      await st.save();
      const j = await api.post(`/api/projects/${project.id}/render`, body);
      st.upsertJob(j);
      setJobId(j.id);
    } catch (e) {
      st.toast((e as Error).message, "error");
    }
  }

  return (
    <Modal title="Exportar" wide onClose={close} footer={
      <>
        {job && job.status === "running" && <div className="grow"><Progress value={job.progress} /><div className="small muted" style={{ marginTop: 4 }}>{Math.round(job.progress * 100)}% {job.eta ? `· quedan ${Math.round(job.eta)} s` : ""}</div></div>}
        {job && job.status === "done" && <div className="grow small" style={{ color: "var(--ok)" }}>✔ {job.result?.name} · {fmtBytes(job.result?.size_bytes)}</div>}
        {job && job.status === "error" && <div className="grow small" style={{ color: "#fca5a5" }}>✘ {job.error}</div>}
        {job && job.status === "running" && <Button kind="danger" onClick={() => api.post(`/api/jobs/${job.id}/cancel`)}>Cancelar</Button>}
        <Button kind="ghost" onClick={close}>Cerrar</Button>
        <Button kind="primary" icon={<Film size={15} />} onClick={() => void start()} disabled={!fmt?.available || dur === 0 || job?.status === "running"}>Exportar</Button>
      </>
    }>
      <div className="platforms">
        {(presets?.platforms ?? []).map((p) => <span key={p.id} className="chip" onClick={() => applyPlatform(p.id)}>{p.label}</span>)}
      </div>
      <div className="grid2" style={{ gridTemplateColumns: "1.3fr 1fr", gap: 18 }}>
        <div>
          <Tabs value={kindTab} onChange={setKindTab} tabs={[
            { value: "video", label: "Entrega" }, { value: "master", label: "Máster" }, { value: "web", label: "Web" }, { value: "image", label: "Imagen" }, { value: "audio", label: "Audio" },
          ]} />
          <div style={{ height: 8 }} />
          <div className="export-formats">
            {fmts.map((f) => (
              <button key={f.id} className={`fmt ${format === f.id ? "active" : ""}`} disabled={!f.available} onClick={() => setFormat(f.id)} title={f.available ? "" : "Tu FFmpeg no incluye este codificador"}>
                <div className="fmt-label">{f.label} {f.alpha && <Badge tone="info">alfa</Badge>}</div>
                <div className="fmt-desc">{f.available ? f.description : "No disponible en tu FFmpeg"}</div>
              </button>
            ))}
          </div>
          <div className="sep" />
          <div className="grid2">
            <Field label="Título (metadatos)"><input type="text" value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
            <Field label="Nombre de archivo"><input type="text" value={filename} onChange={(e) => setFilename(e.target.value)} placeholder="automático" /></Field>
            <Field label="Autor"><input type="text" value={author} onChange={(e) => setAuthor(e.target.value)} /></Field>
            <Field label="Copyright"><input type="text" value={copyright} onChange={(e) => setCopyright(e.target.value)} placeholder="© 2026 TCM" /></Field>
          </div>
        </div>
        <div>
          {fmt?.kind !== "audio" && (
            <>
              <Field label="Resolución">
                <Select value={res} onChange={setRes} options={[
                  { value: "project", label: `Del proyecto (${project.settings.width}×${project.settings.height})` },
                  ...(presets?.resolutions ?? []).map((r) => ({ value: r.id, label: `${r.label} · ${r.w}×${r.h}` })),
                  { value: "custom", label: "Personalizada" },
                ]} />
              </Field>
              {res === "custom" && (
                <div className="grid2">
                  <Field label="Ancho"><input type="number" value={w} onChange={(e) => setW(+e.target.value)} /></Field>
                  <Field label="Alto"><input type="number" value={h} onChange={(e) => setH(+e.target.value)} /></Field>
                </div>
              )}
              {aspectDiffers && (
                <Field label="Reencuadre (otra relación de aspecto)">
                  <Select value={reframe} onChange={setReframe} options={[
                    { value: "blur_fill", label: "Fondo difuminado (redes)" }, { value: "fit", label: "Bandas (letterbox)" }, { value: "fill", label: "Recortar al centro" }, { value: "stretch", label: "Estirar" },
                  ]} />
                </Field>
              )}
              <div className="grid2">
                <Field label="FPS"><Select value={fps} onChange={setFps} options={[{ value: "project", label: `Proyecto (${project.settings.fps})` }, ...(presets?.fps ?? []).map((f) => ({ value: String(f), label: String(f) }))]} /></Field>
                <Field label="Calidad"><Select value={quality} onChange={setQuality} options={[{ value: "draft", label: "Borrador" }, { value: "good", label: "Buena" }, { value: "high", label: "Alta" }, { value: "master", label: "Máster" }]} /></Field>
              </div>
            </>
          )}
          <div className="grid2">
            <Field label="Rango">
              <Select value={range} onChange={setRange} options={[{ value: "all", label: `Todo (${fmtTime(dur, project.settings.fps, false)})` },
                { value: "inout", label: inPoint != null && outPoint != null ? `Entrada→Salida (${(outPoint - inPoint).toFixed(1)} s)` : "Entrada→Salida (marca I/O)", disabled: !(inPoint != null && outPoint != null && outPoint > inPoint) }]} />
            </Field>
            <Field label="Sonoridad">
              <Select value={loudness} onChange={setLoudness} options={[
                { value: "off", label: "Sin normalizar" }, { value: "-14", label: "-14 LUFS (YouTube, Spotify)" }, { value: "-16", label: "-16 LUFS (Apple, podcast)" },
                { value: "-23", label: "-23 LUFS (TV EBU R128)" }, { value: "-24", label: "-24 LKFS (TV EE. UU.)" }, { value: "-27", label: "-27 LUFS (cine/streaming)" },
              ]} />
            </Field>
          </div>
          <div style={{ display: "grid", gap: 8, margin: "4px 0 10px" }}>
            {fmt?.alpha && <Toggle checked={transparent} onChange={setTransparent} label="Fondo transparente (canal alfa)" />}
            <Toggle checked={aiMeta} onChange={setAiMeta} label="Metadatos «generado con IA» (AI Act art. 50)" />
            <Toggle checked={aiMark} onChange={setAiMark} label="Marca visible «Generado con IA»" />
            <Toggle checked={subs} onChange={setSubs} label="Subtítulos .srt y manifiesto de procedencia" />
          </div>
          <div className="small muted">Salida: <b>{dims.w}×{dims.h}</b> · {fmt?.label}</div>
        </div>
      </div>
      {project.markers.length > 0 && (
        <>
          <div className="sep" />
          <div className="row" style={{ alignItems: "flex-start" }}>
            <div className="grow">
              <b>Capítulos de YouTube</b> <span className="small muted">(desde los marcadores)</span>
              <pre className="job-logs" style={{ maxHeight: 90 }}>{chapters}</pre>
            </div>
            <Button size="sm" onClick={() => { void navigator.clipboard?.writeText(chapters); st.toast("Capítulos copiados", "ok"); }}>Copiar</Button>
          </div>
        </>
      )}
      <div className="sep" />
      <div className="row" style={{ marginBottom: 8 }}>
        <b className="grow">Exportaciones del proyecto</b>
        <a className="btn btn-ghost btn-sm" href={urls.export(project.id, "fcpxml")} download><FileText size={13} /> FCPXML (Resolve/FCP)</a>
        <a className="btn btn-ghost btn-sm" href={urls.export(project.id, "edl")} download><FileText size={13} /> EDL</a>
        <a className="btn btn-ghost btn-sm" href={urls.export(project.id, "otio")} download><FileJson size={13} /> OTIO</a>
        <a className="btn btn-ghost btn-sm" href={urls.export(project.id, "srt")} download><FileText size={13} /> SRT</a>
      </div>
      {renders.length === 0 ? <div className="small muted">Todavía no hay exportaciones.</div> : renders.map((r) => (
        <div key={r.name} className="list-row">
          <div className="grow" style={{ minWidth: 0 }}>
            <div className="media-name">{r.name}</div>
            <div className="small muted">{fmtBytes(r.size_bytes)} · {new Date(r.time * 1000).toLocaleString()}</div>
          </div>
          <a className="icon-btn" href={urls.file(project.id, r.path)} download title="Descargar"><Download size={15} /></a>
          {/\.(mp4|mov|webm|mkv|mxf|wav|mp3|png|jpg|gif)$/.test(r.name) && (
            <IconButton title="Importar como medio" onClick={async () => { const m = await api.post(`/api/projects/${project.id}/renders/${encodeURIComponent(r.name)}/import`); st.mergeMedia([m]); st.toast("Añadido a Medios", "ok"); }}><Import size={15} /></IconButton>
          )}
          <IconButton title="Borrar" onClick={async () => { await api.del(`/api/projects/${project.id}/renders/${encodeURIComponent(r.name)}`); void loadRenders(); }}><Trash2 size={14} /></IconButton>
        </div>
      ))}
    </Modal>
  );
}

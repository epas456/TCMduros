import { FileAudio, FolderInput, Image as ImageIcon, Plus, Search, Trash2, Upload, Video } from "lucide-react";
import { useRef, useState } from "react";
import { api, urls } from "../api";
import { uploadFiles } from "../components/Timeline";
import { Badge, Button, Empty, IconButton, Modal, Spinner, Tabs } from "../components/ui";
import { clipFromMedia, fmtBytes, fmtDur, sortTrack, trackAccepts } from "../lib/timeline";
import { useStore } from "../store";
import type { MediaItem } from "../types";

type Filter = "all" | "video" | "image" | "audio" | "ai";

export function addToTimeline(m: MediaItem) {
  const st = useStore.getState();
  const clip = clipFromMedia(m, st.playhead);
  st.edit((p) => {
    // primera pista compatible y libre en el cabezal
    const cands = p.tracks.filter((t) => trackAccepts(t, m.kind) && !t.locked);
    const free = cands.find((t) => !t.clips.some((c) => clip.start < c.start + c.duration && clip.start + clip.duration > c.start));
    const track = free || cands[0];
    if (!track) return;
    track.clips.push(clip);
    sortTrack(track);
  });
  st.select([clip.id]);
}

export default function MediaPanel() {
  const project = useStore((s) => s.project)!;
  const selected = useStore((s) => s.selectedMedia);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [paths, setPaths] = useState("");
  const [info, setInfo] = useState<MediaItem | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const st = useStore.getState();

  async function upload(files: FileList | File[]) {
    if (!files.length) return;
    setBusy(true);
    try {
      const r = await uploadFiles(project.id, files);
      st.mergeMedia(r.media);
      if (r.errors.length) st.toast(`No se pudieron importar: ${r.errors.map((e) => e.file).join(", ")}`, "error");
      else st.toast(`${r.media.length} archivo(s) importados`, "ok");
    } catch (e) {
      st.toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function importPaths() {
    const list = paths.split("\n").map((x) => x.trim()).filter(Boolean);
    if (!list.length) return;
    setBusy(true);
    try {
      const r = await api.post(`/api/projects/${project.id}/media/import`, { paths: list, copy_files: true });
      st.mergeMedia(r.media);
      st.toast(`${r.media.length} archivo(s) importados${r.errors.length ? `, ${r.errors.length} con error` : ""}`, r.errors.length ? "warn" : "ok");
      setImportOpen(false);
      setPaths("");
    } finally {
      setBusy(false);
    }
  }

  async function remove(m: MediaItem) {
    const used = project.tracks.some((t) => t.clips.some((c) => c.media_id === m.id));
    if (!confirm(used ? `«${m.name}» se usa en la línea de tiempo. ¿Eliminarlo y quitar sus clips?` : `¿Eliminar «${m.name}» del proyecto?`)) return;
    await api.del(`/api/projects/${project.id}/media/${m.id}?delete_file=true`);
    if (!used) useStore.setState({ project: { ...useStore.getState().project!, media: useStore.getState().project!.media.filter((x) => x.id !== m.id) } });
  }

  const items = project.media
    .filter((m) => (filter === "all" ? true : filter === "ai" ? m.ai_generated : m.kind === filter))
    .filter((m) => !q || m.name.toLowerCase().includes(q.toLowerCase()) || m.tags.some((t) => t.toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => b.created - a.created);

  return (
    <div className="panel-pad"
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setOver(true); } }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { if (e.dataTransfer.files.length) { e.preventDefault(); setOver(false); void upload(e.dataTransfer.files); } }}>
      <div className={`dropzone ${over ? "over" : ""}`}>
        {busy ? <><Spinner /> Importando…</> : <>Arrastra aquí vídeos, imágenes o audio<br /><span className="small">MP4, MOV, ProRes, MKV, PNG, EXR, WAV, MP3…</span></>}
        <div className="row" style={{ justifyContent: "center", marginTop: 8 }}>
          <Button size="sm" icon={<Upload size={14} />} onClick={() => input.current?.click()}>Subir archivos</Button>
          <Button size="sm" kind="ghost" icon={<FolderInput size={14} />} onClick={() => setImportOpen(true)}>Desde ruta local</Button>
        </div>
        <input ref={input} type="file" multiple hidden accept="video/*,image/*,audio/*,.mxf,.mov,.mkv,.exr" onChange={(e) => e.target.files && void upload(e.target.files)} />
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        <div style={{ position: "relative" }} className="grow">
          <input type="search" placeholder="Buscar medios o etiquetas" value={q} onChange={(e) => setQ(e.target.value)} style={{ paddingLeft: 26 }} />
          <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--muted)" }} />
        </div>
      </div>
      <Tabs value={filter} onChange={setFilter} tabs={[
        { value: "all", label: "Todo" }, { value: "video", label: <Video size={14} />, title: "Vídeo" }, { value: "image", label: <ImageIcon size={14} />, title: "Imagen" },
        { value: "audio", label: <FileAudio size={14} />, title: "Audio" }, { value: "ai", label: "IA" },
      ]} />
      <div style={{ height: 10 }} />
      {items.length === 0 ? (
        <Empty title="Sin medios">Importa material o genéralo con el Estudio IA.</Empty>
      ) : (
        <div className="media-grid">
          {items.map((m) => (
            <div key={m.id} className={`media-card ${selected === m.id ? "sel" : ""}`} draggable
              onDragStart={(e) => { e.dataTransfer.setData("text/x-durostcm-media", m.id); e.dataTransfer.effectAllowed = "copy"; }}
              onClick={() => st.set({ selectedMedia: m.id })} onDoubleClick={() => addToTimeline(m)} title="Arrastra a la línea de tiempo o haz doble clic">
              <div className="media-thumb" style={m.thumbnail ? { backgroundImage: `url(${urls.file(project.id, m.thumbnail)})` } : undefined}>
                <div className="tl-badges">
                  {m.ai_generated && <Badge tone="ai">IA</Badge>}
                  {(m.height ?? 0) >= 2000 && <Badge tone="info">4K</Badge>}
                  {m.tags.includes("guía") && <Badge tone="warn">guía</Badge>}
                  {m.credit && <Badge tone="ok" title={m.credit.attribution}>CC</Badge>}
                </div>
                {m.duration != null && <span className="dur">{fmtDur(m.duration)}</span>}
              </div>
              <div className="media-meta">
                <div className="media-name">{m.name}</div>
                <div className="row small muted" style={{ gap: 4 }}>
                  <span className="grow">{m.kind === "audio" ? "Audio" : `${m.width ?? "?"}×${m.height ?? "?"}`}</span>
                  <IconButton title="Añadir en el cabezal" className="sm" onClick={(e) => { e.stopPropagation(); addToTimeline(m); }}><Plus size={13} /></IconButton>
                  <IconButton title="Detalles" onClick={(e) => { e.stopPropagation(); setInfo(m); }}>i</IconButton>
                  <IconButton title="Eliminar" onClick={(e) => { e.stopPropagation(); void remove(m); }}><Trash2 size={13} /></IconButton>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {importOpen && (
        <Modal title="Importar desde rutas locales" onClose={() => setImportOpen(false)} footer={<><Button kind="ghost" onClick={() => setImportOpen(false)}>Cancelar</Button><Button kind="primary" onClick={() => void importPaths()} disabled={busy}>Importar</Button></>}>
          <p className="panel-sub">Como durosTCM se ejecuta en tu equipo, puedes importar archivos o carpetas completas sin subirlos (se copian al proyecto). Una ruta por línea.</p>
          <textarea value={paths} onChange={(e) => setPaths(e.target.value)} placeholder={"/Users/estudio/Rodaje/A001_C003.mov\nD:\\Proyectos\\Campaña\\musica"} rows={6} />
        </Modal>
      )}
      {info && (
        <Modal title={info.name} onClose={() => setInfo(null)}>
          <div className="kv">
            <span>Tipo</span><span>{info.kind}</span>
            <span>Resolución</span><span>{info.width}×{info.height}</span>
            <span>Duración</span><span>{fmtDur(info.duration)}</span>
            <span>FPS</span><span>{info.fps ?? "—"}</span>
            <span>Códecs</span><span>{info.vcodec ?? "—"} / {info.acodec ?? "—"}</span>
            <span>Tamaño</span><span>{fmtBytes(info.size_bytes)}</span>
            <span>Origen</span><span>{info.source}{info.proxy ? " · con proxy" : ""}</span>
            {info.generation && <><span>Motor IA</span><span>{info.generation.engine} · {info.generation.model}</span></>}
            {info.generation && <><span>Semilla</span><span>{info.generation.seed}</span></>}
            {info.generation && <><span>Prompt</span><span style={{ whiteSpace: "pre-wrap" }}>{info.generation.prompt}</span></>}
            {info.credit && <><span>Licencia</span><span>{info.credit.attribution}</span></>}
          </div>
        </Modal>
      )}
    </div>
  );
}

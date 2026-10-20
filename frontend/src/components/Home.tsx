import { Clapperboard, Copy, Film, Megaphone, Plus, Sparkles, Trash2, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { api, urls } from "../api";
import { ASPECT_PRESETS } from "../lib/timeline";
import { useStore } from "../store";
import type { ProjectSummary } from "../types";
import { Button, Empty, Field, IconButton, Modal } from "./ui";

const QUICK = [
  { id: "character_4k", title: "Personaje hiperrealista 4K", icon: UserRound, grad: "linear-gradient(135deg,#ff7a1a,#e9246a)",
    desc: "Describe a tu personaje: durosTCM diseña su biblia, su hoja de referencia, lo anima en varias tomas y exporta un máster 4K.", preset: "yt4k" },
  { id: "ad", title: "Anuncio publicitario", icon: Megaphone, grad: "linear-gradient(135deg,#8b5cf6,#22d3ee)",
    desc: "Producto, público y tono → guion, planos, locución, música con ducking, rótulos y logo. Listo para redes o TV.", preset: "reels" },
  { id: "short_film", title: "Cortometraje", icon: Clapperboard, grad: "linear-gradient(135deg,#f59e0b,#ef4444)",
    desc: "Una idea → guion en 8 tiempos, personajes con voz propia, subtítulos, banda sonora y montaje en cinemascope.", preset: "cine" },
  { id: "blank", title: "Proyecto en blanco", icon: Film, grad: "linear-gradient(135deg,#334155,#0f172a)",
    desc: "Editor profesional multipista: importa tu material, etalona, rotula y exporta en cualquier formato.", preset: "hd" },
];

export default function Home() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [creating, setCreating] = useState<{ pipeline: string; preset: string } | null>(null);
  const [name, setName] = useState("");
  const [preset, setPreset] = useState("hd");
  const [custom, setCustom] = useState({ w: 1920, h: 1080, fps: 24 });
  const st = useStore.getState();

  const load = () => api.get<{ projects: ProjectSummary[] }>("/api/projects").then((r) => setProjects(r.projects)).catch(() => setProjects([]));
  useEffect(() => {
    void load();
  }, []);

  async function create() {
    const pr = ASPECT_PRESETS.find((p) => p.id === preset);
    const dims = preset === "custom" ? custom : { w: pr!.w, h: pr!.h, fps: pr!.fps };
    const p = await api.post("/api/projects", { name: name || "Proyecto sin título", width: dims.w, height: dims.h, fps: dims.fps });
    await st.openProject(p.id);
    if (creating && creating.pipeline !== "blank") st.set({ leftTab: "director", directorPreset: creating.pipeline });
    setCreating(null);
  }

  return (
    <main className="home">
      <section className="hero">
        <h1>duros<b>TCM</b> · estudio de cine con IA local</h1>
        <p>
          Crea personajes hiperrealistas, anuncios y cortometrajes en tu propio equipo. Editor profesional, IA imaginativa que escribe,
          dirige y genera cada plano, voces, música y exportación hasta 8K en ProRes, DNxHR, HEVC, AV1 y más. Tus datos no salen de tu máquina.
        </p>
      </section>
      <div className="quick">
        {QUICK.map((q) => (
          <div key={q.id} className="quick-card" onClick={() => { setCreating({ pipeline: q.id, preset: q.preset }); setPreset(q.preset); setName(q.id === "blank" ? "" : q.title); }}>
            <div className="qc-icon" style={{ background: q.grad }}><q.icon size={20} /></div>
            <h3>{q.title}</h3>
            <p>{q.desc}</p>
          </div>
        ))}
      </div>
      <section className="home-section">
        <div className="row" style={{ marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>Proyectos</h2>
          <div className="spacer" />
          <Button kind="primary" icon={<Plus size={15} />} onClick={() => { setCreating({ pipeline: "blank", preset: "hd" }); setPreset("hd"); setName(""); }}>Nuevo proyecto</Button>
        </div>
        {projects === null ? null : projects.length === 0 ? (
          <Empty icon={<Sparkles size={28} />} title="Aún no hay proyectos">Empieza con una de las plantillas de arriba.</Empty>
        ) : (
          <div className="proj-grid">
            {projects.map((p) => (
              <div key={p.id} className="proj-card" onClick={() => void st.openProject(p.id)}>
                <div className="proj-thumb" style={p.thumbnail ? { backgroundImage: `url(${urls.file(p.id, p.thumbnail)})` } : undefined}>
                  {!p.thumbnail && <Film size={26} />}
                </div>
                <div className="proj-meta">
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div className="media-name">{p.name}</div>
                    <div className="small muted">{p.width}×{p.height} · {p.fps} fps · {new Date(p.updated * 1000).toLocaleString()}</div>
                  </div>
                  <IconButton title="Duplicar" onClick={async (e) => { e.stopPropagation(); await api.post(`/api/projects/${p.id}/duplicate`); void load(); }}><Copy size={15} /></IconButton>
                  <IconButton title="Eliminar" onClick={async (e) => {
                    e.stopPropagation();
                    if (confirm(`¿Eliminar «${p.name}» y todos sus archivos?`)) { await api.del(`/api/projects/${p.id}`); void load(); }
                  }}><Trash2 size={15} /></IconButton>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
      {creating && (
        <Modal title="Nuevo proyecto" onClose={() => setCreating(null)} footer={
          <>
            <Button kind="ghost" onClick={() => setCreating(null)}>Cancelar</Button>
            <Button kind="primary" onClick={() => void create()}>Crear y abrir</Button>
          </>
        }>
          <Field label="Nombre">
            <input type="text" value={name} autoFocus placeholder="Mi producción" onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void create()} />
          </Field>
          <Field label="Formato">
            <div className="preset-grid">
              {ASPECT_PRESETS.map((p) => {
                const r = p.w / p.h;
                const w = r >= 1 ? 54 : 54 * r;
                const h = r >= 1 ? 54 / r : 54;
                return (
                  <button key={p.id} type="button" className={`preset ${preset === p.id ? "active" : ""}`} onClick={() => setPreset(p.id)}>
                    <div className="shape" style={{ width: w, height: h }} />
                    <div style={{ fontWeight: 600, fontSize: 12 }}>{p.label}</div>
                    <div className="small muted">{p.w}×{p.h} · {p.fps} fps</div>
                  </button>
                );
              })}
              <button type="button" className={`preset ${preset === "custom" ? "active" : ""}`} onClick={() => setPreset("custom")}>
                <div className="shape" style={{ width: 40, height: 40, borderStyle: "dashed" }} />
                <div style={{ fontWeight: 600, fontSize: 12 }}>Personalizado</div>
              </button>
            </div>
          </Field>
          {preset === "custom" && (
            <div className="grid3">
              <Field label="Ancho"><input type="number" value={custom.w} onChange={(e) => setCustom({ ...custom, w: +e.target.value })} /></Field>
              <Field label="Alto"><input type="number" value={custom.h} onChange={(e) => setCustom({ ...custom, h: +e.target.value })} /></Field>
              <Field label="FPS"><input type="number" value={custom.fps} onChange={(e) => setCustom({ ...custom, fps: +e.target.value })} /></Field>
            </div>
          )}
          {creating.pipeline !== "blank" && (
            <p className="panel-sub">Al abrir el proyecto se mostrará el <b>Director IA</b> con el asistente de «{QUICK.find((q) => q.id === creating.pipeline)?.title}».</p>
          )}
        </Modal>
      )}
    </main>
  );
}

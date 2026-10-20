import { Clapperboard, Clock, LayoutGrid, Megaphone, Play, ScrollText, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { api, urls } from "../api";
import { Badge, Button, Field, Progress, Select, Slider, Spinner, Toggle } from "../components/ui";
import { aspectId } from "../lib/timeline";
import { useStore } from "../store";
import type { Character, FaceRef } from "../types";

type Pipe = "character_4k" | "ad" | "short_film" | "storyboard";

const PIPES: { id: Pipe; title: string; desc: string; icon: typeof UserRound }[] = [
  { id: "character_4k", title: "Personaje hiperrealista 4K", icon: UserRound, desc: "Biblia del personaje → hoja de referencia → retrato 4K → 6 planos animados con la misma identidad → máster 4K." },
  { id: "ad", title: "Anuncio publicitario", icon: Megaphone, desc: "Gancho, deseo, revelación, beneficio y cierre con locución, música con ducking, rótulos y logo." },
  { id: "short_film", title: "Cortometraje", icon: Clapperboard, desc: "Guion en 8 tiempos, personajes con voz propia, subtítulos, banda sonora y montaje." },
  { id: "storyboard", title: "Sólo storyboard", icon: LayoutGrid, desc: "Escribe el guion técnico plano a plano para revisarlo antes de generar nada." },
];

function fmtEta(s: number) {
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

export default function DirectorPanel() {
  const project = useStore((s) => s.project)!;
  const preset = useStore((s) => s.directorPreset);
  const jobs = useStore((s) => s.jobs);
  const [pipe, setPipe] = useState<Pipe>((preset as Pipe) || "character_4k");
  const [p, setP] = useState<Record<string, any>>({});
  const [plan, setPlan] = useState<any>(null);
  const [chars, setChars] = useState<Character[]>([]);
  const [faces, setFaces] = useState<FaceRef[]>([]);
  const [busy, setBusy] = useState(false);
  const st = useStore.getState();
  const aspect = aspectId(project.settings.width, project.settings.height);

  useEffect(() => {
    if (preset) {
      setPipe(preset as Pipe);
      st.set({ directorPreset: null });
    }
  }, [preset]);
  useEffect(() => {
    api.get<{ items: Character[] }>("/api/library/characters").then((r) => setChars(r.items)).catch(() => undefined);
    api.get<{ items: FaceRef[] }>("/api/faces").then((r) => setFaces(r.items)).catch(() => undefined);
  }, []);
  useEffect(() => {
    const defaults: Record<Pipe, Record<string, any>> = {
      character_4k: { description: "", location: "", duration: 24, aspect: aspect === "9:16" ? "9:16" : "16:9", imagination: 0.6, reference_views: 4, upscale: true, auto_export: true, export_format: "mp4_h265", face_ids: [] },
      ad: { product: "", brand: "", description: "", audience: "", tone: "premium", cta: "", duration: 20, aspect, voiceover: true, music: true, subtitles: true, imagination: 0.6, auto_export: false },
      short_film: { idea: "", genre: "drama", duration: 60, aspect: aspect === "16:9" ? "2.39:1" : aspect, imagination: 0.7, character_ids: [] },
      storyboard: { brief: "", format: "short_film", duration: 30, character_ids: [] },
    };
    setP(defaults[pipe]);
  }, [pipe]);
  useEffect(() => {
    const t = setTimeout(() => {
      api.post(`/api/pipelines/${pipe}/plan`, { project_id: project.id, params: p }).then(setPlan).catch(() => setPlan(null));
    }, 300);
    return () => clearTimeout(t);
  }, [pipe, p.duration, p.reference_views, p.upscale]);

  const set = (k: string, v: unknown) => setP((x) => ({ ...x, [k]: v }));
  const running = Object.values(jobs).filter((j) => j.project_id === project.id && j.kind.startsWith("pipeline:")).sort((a, b) => b.created - a.created);

  async function launch() {
    setBusy(true);
    try {
      const j = await api.post(`/api/pipelines/${pipe}`, { project_id: project.id, params: p });
      st.upsertJob(j);
      if (j.ethics?.issues?.length) st.toast(`⚠ ${j.ethics.issues.join(" ")}`, "warn");
      st.toast("Producción en marcha. Puedes seguir editando mientras tanto.", "ok");
      if (pipe !== "character_4k") st.set({ centerTab: "storyboard" });
    } catch (e) {
      st.toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  const valid = pipe === "character_4k" ? !!p.description?.trim() : pipe === "ad" ? !!p.product?.trim() : pipe === "short_film" ? !!p.idea?.trim() : !!p.brief?.trim();

  return (
    <div className="panel-pad">
      <h3 className="panel-title"><Clapperboard size={16} color="var(--accent)" /> Director IA</h3>
      <p className="panel-sub">Describe lo que quieres. El equipo creativo de IA escribe, diseña, genera cada plano, pone voces y música y lo monta en la línea de tiempo.</p>
      <div className="pipe-cards">
        {PIPES.map((x) => (
          <button key={x.id} className={`pipe-card ${pipe === x.id ? "active" : ""}`} onClick={() => setPipe(x.id)}>
            <span className="pc-icon"><x.icon size={17} /></span>
            <span><div className="pc-title">{x.title}</div><div className="pc-desc">{x.desc}</div></span>
          </button>
        ))}
      </div>
      <div className="sep" />

      {pipe === "character_4k" && (
        <>
          <Field label="Describe al personaje">
            <textarea rows={4} value={p.description ?? ""} onChange={(e) => set("description", e.target.value)}
              placeholder="Detective de 45 años, mujer, pelirroja con canas, cicatriz en la ceja, gabardina gastada, mirada cansada pero brillante…" />
          </Field>
          <Field label="Localización (opcional)">
            <input type="text" value={p.location ?? ""} onChange={(e) => set("location", e.target.value)} placeholder="Azotea en Madrid de noche bajo la lluvia" />
          </Field>
          {faces.length > 0 && (
            <Field label="Rostros de inspiración (opcional)" hint="Se usan sus rasgos generales para crear una persona nueva.">
              <div className="face-grid">
                {faces.slice(0, 12).map((f) => {
                  const on = (p.face_ids ?? []).includes(f.id);
                  return (
                    <div key={f.id} className={`face-card ${on ? "sel" : ""}`} onClick={() => set("face_ids", on ? p.face_ids.filter((x: string) => x !== f.id) : [...(p.face_ids ?? []), f.id])}>
                      <img src={urls.face(f.id)} alt="" />
                    </div>
                  );
                })}
              </div>
            </Field>
          )}
          <div className="grid2">
            <Field label="Formato"><Select value={p.aspect ?? "16:9"} onChange={(v) => set("aspect", v)} options={[{ value: "16:9", label: "16:9 · 3840×2160" }, { value: "9:16", label: "9:16 · 2160×3840" }, { value: "1:1", label: "1:1 · 2160²" }, { value: "2.39:1", label: "Cinemascope 4K" }]} /></Field>
            <Field label="Duración (s)"><input type="number" min={6} max={120} value={p.duration ?? 24} onChange={(e) => set("duration", +e.target.value)} /></Field>
          </div>
          <Slider label="Imaginación" value={p.imagination ?? 0.6} min={0} max={1} onChange={(v) => set("imagination", v)} />
          <Field label="Vistas de referencia"><input type="number" min={1} max={6} value={p.reference_views ?? 4} onChange={(e) => set("reference_views", +e.target.value)} /></Field>
          <div className="row" style={{ gap: 14, flexWrap: "wrap" }}>
            <Toggle checked={!!p.upscale} onChange={(v) => set("upscale", v)} label="Escalar planos a 4K" />
            <Toggle checked={!!p.auto_export} onChange={(v) => set("auto_export", v)} label="Exportar máster al final" />
          </div>
        </>
      )}

      {pipe === "ad" && (
        <>
          <div className="grid2">
            <Field label="Producto"><input type="text" value={p.product ?? ""} onChange={(e) => set("product", e.target.value)} placeholder="Aurora" /></Field>
            <Field label="Marca"><input type="text" value={p.brand ?? ""} onChange={(e) => set("brand", e.target.value)} placeholder="Aurora Parfums" /></Field>
          </div>
          <Field label="¿Qué es y qué lo hace especial?"><textarea rows={3} value={p.description ?? ""} onChange={(e) => set("description", e.target.value)} placeholder="Perfume de autor con notas de azahar y cedro, frasco de cristal tallado a mano" /></Field>
          <div className="grid2">
            <Field label="Público"><input type="text" value={p.audience ?? ""} onChange={(e) => set("audience", e.target.value)} placeholder="Mujeres 30-45, urbanas" /></Field>
            <Field label="Tono"><Select value={p.tone ?? "premium"} onChange={(v) => set("tone", v)} options={["premium", "emocional", "divertido", "tecnológico", "natural"].map((x) => ({ value: x, label: x }))} /></Field>
          </div>
          <Field label="Llamada a la acción"><input type="text" value={p.cta ?? ""} onChange={(e) => set("cta", e.target.value)} placeholder="Descúbrelo en aurora.es" /></Field>
          <div className="grid2">
            <Field label="Duración"><Select value={String(p.duration ?? 20)} onChange={(v) => set("duration", +v)} options={["6", "10", "15", "20", "30", "45", "60"].map((x) => ({ value: x, label: `${x} s` }))} /></Field>
            <Field label="Formato"><Select value={p.aspect ?? "16:9"} onChange={(v) => set("aspect", v)} options={["16:9", "9:16", "1:1", "4:5"].map((x) => ({ value: x, label: x }))} /></Field>
          </div>
          <div className="grid2">
            <Field label="Logo (medio del proyecto)">
              <Select value={p.logo_media_id ?? ""} onChange={(v) => set("logo_media_id", v || null)} options={[{ value: "", label: "Sin logo" }, ...project.media.filter((m) => m.kind === "image").map((m) => ({ value: m.id, label: m.name }))]} />
            </Field>
            <Field label="Protagonista">
              <Select value={p.character_id ?? ""} onChange={(v) => set("character_id", v || null)} options={[{ value: "", label: "Automático" }, ...chars.map((c) => ({ value: c.id, label: c.name }))]} />
            </Field>
          </div>
          <div className="row" style={{ gap: 14, flexWrap: "wrap" }}>
            <Toggle checked={!!p.voiceover} onChange={(v) => set("voiceover", v)} label="Locución" />
            <Toggle checked={!!p.music} onChange={(v) => set("music", v)} label="Música" />
            <Toggle checked={!!p.subtitles} onChange={(v) => set("subtitles", v)} label="Subtítulos" />
            <Toggle checked={!!p.auto_export} onChange={(v) => set("auto_export", v)} label="Exportar al final" />
          </div>
        </>
      )}

      {pipe === "short_film" && (
        <>
          <Field label="Idea"><textarea rows={4} value={p.idea ?? ""} onChange={(e) => set("idea", e.target.value)} placeholder="Un relojero anciano descubre que puede detener el tiempo, pero sólo durante los últimos segundos de cada día…" /></Field>
          <div className="grid2">
            <Field label="Género"><Select value={p.genre ?? "drama"} onChange={(v) => set("genre", v)} options={["drama", "thriller", "ciencia ficción", "terror", "comedia", "romance", "acción", "fantasía", "noir"].map((x) => ({ value: x, label: x }))} /></Field>
            <Field label="Duración (s)"><input type="number" min={15} max={600} value={p.duration ?? 60} onChange={(e) => set("duration", +e.target.value)} /></Field>
          </div>
          <Field label="Formato"><Select value={p.aspect ?? "2.39:1"} onChange={(v) => set("aspect", v)} options={["2.39:1", "1.85:1", "16:9", "9:16"].map((x) => ({ value: x, label: x }))} /></Field>
          {chars.length > 0 && (
            <Field label="Reparto (opcional)">
              <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
                {chars.map((c) => {
                  const on = (p.character_ids ?? []).includes(c.id);
                  return <span key={c.id} className={`chip ${on ? "active" : ""}`} onClick={() => set("character_ids", on ? p.character_ids.filter((x: string) => x !== c.id) : [...(p.character_ids ?? []), c.id])}>{c.name}</span>;
                })}
              </div>
            </Field>
          )}
          <Slider label="Imaginación" value={p.imagination ?? 0.7} min={0} max={1} onChange={(v) => set("imagination", v)} />
        </>
      )}

      {pipe === "storyboard" && (
        <>
          <Field label="Brief o guion"><textarea rows={6} value={p.brief ?? ""} onChange={(e) => set("brief", e.target.value)} placeholder="Pega aquí el guion, el brief del cliente o la idea…" /></Field>
          <div className="grid2">
            <Field label="Formato"><Select value={p.format ?? "short_film"} onChange={(v) => set("format", v)} options={[{ value: "short_film", label: "Cortometraje" }, { value: "ad", label: "Anuncio" }, { value: "character", label: "Presentación de personaje" }, { value: "music_video", label: "Videoclip" }, { value: "trailer", label: "Tráiler" }]} /></Field>
            <Field label="Duración (s)"><input type="number" value={p.duration ?? 30} onChange={(e) => set("duration", +e.target.value)} /></Field>
          </div>
        </>
      )}

      {plan && (
        <div className="eta">
          <Clock size={15} />
          <div className="grow">
            Estimación en este equipo: <b>{fmtEta(plan.total_s)}</b> <span className="muted">({plan.tier_label})</span>
          </div>
          {plan.fits_2h ? <Badge tone="ok">≤ 2 h</Badge> : <Badge tone="warn">&gt; 2 h</Badge>}
        </div>
      )}
      <Button kind="primary" size="lg" className="grow" icon={busy ? <Spinner size={14} /> : <Play size={16} />} disabled={!valid || busy} onClick={() => void launch()}>
        {pipe === "storyboard" ? "Escribir storyboard" : "¡Acción!"}
      </Button>

      {running.length > 0 && (
        <>
          <div className="sep" />
          <div className="small muted" style={{ marginBottom: 6 }}>Producciones de este proyecto</div>
          {running.slice(0, 5).map((j) => (
            <div key={j.id} className="card" style={{ padding: 10 }}>
              <div className="row small"><b className="grow">{j.title}</b>
                <Badge tone={j.status === "done" ? "ok" : j.status === "error" ? "error" : j.status === "running" ? "info" : "default"}>{j.status}</Badge>
              </div>
              <div style={{ margin: "6px 0" }}><Progress value={j.progress} tone={j.status === "error" ? "error" : j.status === "done" ? "ok" : "default"} /></div>
              <div className="small muted">{j.stage}{j.eta ? ` · quedan ~${fmtEta(j.eta)}` : ""}</div>
              {j.error && <div className="small" style={{ color: "#fca5a5", marginTop: 4 }}>{j.error}</div>}
              {j.status === "done" && j.result?.render && (
                <a className="small" href={urls.file(project.id, j.result.render.path)} download>⬇ Descargar máster {j.result.render.width}×{j.result.render.height}</a>
              )}
            </div>
          ))}
          {project.storyboard && <Button size="sm" icon={<ScrollText size={14} />} onClick={() => st.set({ centerTab: "storyboard" })}>Ver storyboard</Button>}
        </>
      )}
    </div>
  );
}

import { Film, Image as ImageIcon, LayoutList, Plus, Printer, Trash2, Wand2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, urls } from "../api";
import { uid } from "../lib/timeline";
import { useStore } from "../store";
import type { Shot, Storyboard } from "../types";
import { Badge, Button, Empty, IconButton } from "./ui";

const SIZES = ["extreme_wide", "wide", "full", "medium", "medium_close", "close_up", "extreme_close_up", "insert", "over_shoulder", "two_shot"];
const SIZE_ES: Record<string, string> = { extreme_wide: "Gran general", wide: "General", full: "Entero", medium: "Medio", medium_close: "Medio corto", close_up: "Primer plano",
  extreme_close_up: "Primerísimo", insert: "Detalle", over_shoulder: "Sobre hombro", two_shot: "Dos" };
const MOVES = ["static", "dolly_in", "dolly_out", "pan", "tilt", "crane", "orbit", "handheld", "drone", "tracking", "push_in", "whip_pan", "fpv"];
const MOVE_ES: Record<string, string> = { static: "Fija", dolly_in: "Travelling in", dolly_out: "Travelling out", pan: "Panorámica", tilt: "Tilt", crane: "Grúa", orbit: "Órbita",
  handheld: "En mano", drone: "Dron", tracking: "Seguimiento", push_in: "Empuje", whip_pan: "Barrido", fpv: "FPV" };

export default function StoryboardView() {
  const project = useStore((s) => s.project)!;
  const sb = project.storyboard;
  const [local, setLocal] = useState<Storyboard | null>(sb);
  const timer = useRef<number>();
  const st = useStore.getState();

  useEffect(() => setLocal(sb), [sb]);

  if (!local) {
    return (
      <div className="storyboard">
        <Empty icon={<LayoutList size={28} />} title="Sin storyboard">Usa el <b>Director IA</b> para escribirlo automáticamente a partir de una idea o un guion.</Empty>
      </div>
    );
  }

  function update(fn: (s: Storyboard) => void) {
    const next = structuredClone(local!) as Storyboard;
    fn(next);
    setLocal(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      void api.put(`/api/projects/${project.id}/storyboard`, next).then(() => st.setStoryboard(next));
    }, 600);
  }

  async function produce(ids: string[] | null, video = true) {
    await api.put(`/api/projects/${project.id}/storyboard`, local);
    const j = await api.post("/api/pipelines/produce", { project_id: project.id, params: { shot_ids: ids, video } });
    st.upsertJob(j);
    st.toast(ids ? "Generando plano…" : "Generando todos los planos…", "info");
  }

  async function assemble() {
    await api.put(`/api/projects/${project.id}/storyboard`, local);
    const j = await api.post("/api/pipelines/assemble", { project_id: project.id, params: {} });
    st.upsertJob(j);
  }

  const total = local.shots.reduce((a, s) => a + s.duration, 0);
  const media = (id: string | null) => project.media.find((m) => m.id === id);

  return (
    <div className="storyboard">
      <div className="sb-head">
        <div className="grow" style={{ minWidth: 220 }}>
          <input className="sb-title" style={{ background: "transparent", border: "none", width: "100%", fontSize: 18, fontWeight: 800 }} value={local.title}
            onChange={(e) => update((s) => { s.title = e.target.value; })} />
          <div className="small muted">{local.logline}</div>
        </div>
        <Badge tone="info">{local.shots.length} planos · {total.toFixed(1)} s</Badge>
        {local.look && <Badge>{local.look}</Badge>}
        <Button size="sm" kind="ai" icon={<Wand2 size={14} />} onClick={() => void produce(null)}>Generar todo</Button>
        <Button size="sm" icon={<Film size={14} />} onClick={() => void assemble()}>Montar en la línea de tiempo</Button>
        <IconButton title="Imprimir / PDF" onClick={() => window.print()}><Printer size={16} /></IconButton>
      </div>
      <div className="sb-grid">
        {local.shots.map((s, i) => {
          const img = media(s.image_media_id);
          const vid = media(s.video_media_id);
          return (
            <div key={s.id} className="shot">
              <div className="shot-img" style={img?.thumbnail ? { backgroundImage: `url(${urls.file(project.id, img.thumbnail)})` } : undefined}>
                {vid && <video src={urls.media(project.id, vid.id, true, "video")} muted loop playsInline onMouseEnter={(e) => void e.currentTarget.play()} onMouseLeave={(e) => e.currentTarget.pause()} poster={img?.thumbnail ? urls.file(project.id, img.thumbnail) : undefined} />}
                <span className="shot-num">{i + 1}</span>
                <span className="shot-status">
                  <Badge tone={s.status === "done" ? "ok" : s.status === "error" ? "error" : s.status === "image" ? "info" : "default"}>
                    {({ draft: "borrador", image: "fotograma", video: "vídeo", done: "listo", error: "error" } as const)[s.status]}
                  </Badge>
                </span>
              </div>
              <div className="shot-body">
                <div className="row">
                  <input type="text" value={s.scene} onChange={(e) => update((d) => { d.shots[i].scene = e.target.value; })} style={{ fontWeight: 700 }} />
                  <input type="number" step={0.5} min={1} value={s.duration} onChange={(e) => update((d) => { d.shots[i].duration = +e.target.value; })} style={{ width: 64 }} title="Duración (s)" />
                </div>
                <textarea value={s.description} onChange={(e) => update((d) => { d.shots[i].description = e.target.value; })} placeholder="Qué ocurre (español)" />
                <textarea value={s.prompt} onChange={(e) => update((d) => { d.shots[i].prompt = e.target.value; })} placeholder="Prompt visual (inglés recomendado)" />
                <div className="shot-cam">
                  <select value={s.camera.shot_size} onChange={(e) => update((d) => { d.shots[i].camera.shot_size = e.target.value; })}>
                    {SIZES.map((x) => <option key={x} value={x}>{SIZE_ES[x]}</option>)}
                  </select>
                  <select value={s.camera.movement} onChange={(e) => update((d) => { d.shots[i].camera.movement = e.target.value; })}>
                    {MOVES.map((x) => <option key={x} value={x}>{MOVE_ES[x]}</option>)}
                  </select>
                  <input type="text" value={s.camera.lens} onChange={(e) => update((d) => { d.shots[i].camera.lens = e.target.value; })} title="Lente" />
                </div>
                {s.dialogue.map((d, k) => (
                  <div key={k} className="row small">
                    <span className="muted" style={{ flex: "none" }}>🎙</span>
                    <input type="text" value={d.text} onChange={(e) => update((x) => { x.shots[i].dialogue[k].text = e.target.value; })} />
                  </div>
                ))}
                <input type="text" value={s.on_screen_text} placeholder="Rótulo en pantalla" onChange={(e) => update((d) => { d.shots[i].on_screen_text = e.target.value; })} />
              </div>
              <div className="shot-actions">
                <Button size="sm" icon={<ImageIcon size={13} />} onClick={() => void produce([s.id], false)}>Fotograma</Button>
                <Button size="sm" kind="ai" icon={<Film size={13} />} onClick={() => void produce([s.id], true)}>Plano</Button>
                <div className="spacer" />
                <IconButton title="Añadir diálogo" onClick={() => update((d) => { d.shots[i].dialogue.push({ speaker: "narrador", text: "", voice: null }); })}>🎙</IconButton>
                <IconButton title="Eliminar plano" onClick={() => update((d) => { d.shots.splice(i, 1); d.shots.forEach((x, n) => (x.index = n)); })}><Trash2 size={13} /></IconButton>
              </div>
            </div>
          );
        })}
        <button className="shot" style={{ alignItems: "center", justifyContent: "center", minHeight: 200, cursor: "pointer", borderStyle: "dashed", background: "transparent", color: "var(--muted)" }}
          onClick={() => update((d) => {
            const last = d.shots[d.shots.length - 1];
            const shot: Shot = {
              id: uid("s_"), index: d.shots.length, scene: "Nuevo plano", description: "", prompt: "", negative: "", duration: 4,
              camera: { shot_size: "medium", angle: "eye_level", movement: "static", lens: "35mm" }, lighting: last?.lighting ?? "", mood: last?.mood ?? "",
              characters: last?.characters ?? [], location: last?.location ?? null, dialogue: [], on_screen_text: "", sfx: "", transition: "cut", seed: null,
              image_media_id: null, video_media_id: null, audio_media_ids: [], status: "draft",
            };
            d.shots.push(shot);
          })}>
          <Plus size={22} /><div>Añadir plano</div>
        </button>
      </div>
    </div>
  );
}

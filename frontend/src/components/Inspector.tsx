import { Diamond, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { defaultGrade, findClip, fmtDur, kfValue, mediaById } from "../lib/timeline";
import { useStore } from "../store";
import type { Clip, Keyframe, Project } from "../types";
import { Badge, Button, ColorInput, Empty, Field, IconButton, NumberInput, Section, Select, Slider, Toggle } from "./ui";

type Path = "transform.x" | "transform.y" | "transform.scale" | "transform.rotation" | "transform.opacity" | "volume";
const KF_KEY: Record<Path, string> = {
  "transform.x": "x", "transform.y": "y", "transform.scale": "scale", "transform.rotation": "rotation", "transform.opacity": "opacity", volume: "volume",
};

function usePatch(clipId: string) {
  const st = useStore.getState();
  return (fn: (c: Clip, p: Project) => void, history = true) =>
    st.edit((p) => {
      const f = findClip(p, clipId);
      if (f) fn(f.clip, p);
    }, history);
}

function KfSlider({ clip, path, label, min, max, step = 0.01, fmt }: { clip: Clip; path: Path; label: string; min: number; max: number; step?: number; fmt?: (v: number) => string }) {
  const patch = usePatch(clip.id);
  const playhead = useStore((s) => s.playhead);
  const key = KF_KEY[path];
  const kfs = clip.keyframes[key] || [];
  const local = playhead - clip.start;
  const base = path === "volume" ? clip.volume : (clip.transform as any)[path.split(".")[1]];
  const value = kfs.length ? kfValue(kfs, local, base) : base;
  const atKf = kfs.find((k) => Math.abs(k.t - local) < 1 / 48);
  const inside = local >= 0 && local <= clip.duration;

  function set(v: number) {
    patch((c) => {
      const ks = c.keyframes[key];
      if (ks && ks.length) {
        const ex = ks.find((k) => Math.abs(k.t - local) < 1 / 48);
        if (ex) ex.value = v;
        else if (inside) {
          ks.push({ t: local, value: v, easing: "ease_in_out" });
          ks.sort((a, b) => a.t - b.t);
        }
      } else if (path === "volume") c.volume = v;
      else (c.transform as any)[path.split(".")[1]] = v;
    }, false);
  }
  function toggleKf() {
    patch((c) => {
      const ks: Keyframe[] = c.keyframes[key] ? [...c.keyframes[key]] : [];
      const idx = ks.findIndex((k) => Math.abs(k.t - local) < 1 / 48);
      if (idx >= 0) ks.splice(idx, 1);
      else if (inside) ks.push({ t: Math.max(0, local), value, easing: "ease_in_out" });
      ks.sort((a, b) => a.t - b.t);
      if (ks.length) c.keyframes[key] = ks;
      else delete c.keyframes[key];
    });
  }
  return (
    <div className="row" style={{ alignItems: "flex-end" }}>
      <div className="grow"><Slider label={label + (kfs.length ? ` ◆${kfs.length}` : "")} value={value} min={min} max={max} step={step} fmt={fmt} onChange={set}
        onStart={() => useStore.getState().beginGesture()} onCommit={() => useStore.getState().endGesture()} /></div>
      <button className={`kf-btn ${atKf ? "on" : ""}`} title={atKf ? "Quitar keyframe" : "Añadir keyframe en el cabezal"} onClick={toggleKf} disabled={!inside} style={{ marginBottom: 10 }}>
        <Diamond size={11} fill={atKf ? "currentColor" : "none"} />
      </button>
    </div>
  );
}

function AIActions({ clip }: { clip: Clip }) {
  const project = useStore((s) => s.project)!;
  const m = mediaById(project, clip.media_id);
  const st = useStore.getState();
  if (!m) return null;
  async function run(capability: string, params: Record<string, unknown> = {}, replace = true) {
    try {
      const j = await api.post("/api/ai/generate", { project_id: project.id, capability, params, source_media_id: m!.id });
      if (replace) st.watchReplace(j.id, clip.id);
      st.toast("Trabajo de IA en cola: aparecerá en Trabajos", "info");
    } catch (e) {
      st.toast((e as Error).message, "error");
    }
  }
  const ar = (m.width || 16) / (m.height || 9);
  const t4k = ar >= 1 ? { target_width: 3840, target_height: Math.round(3840 / ar / 2) * 2 } : { target_height: 3840, target_width: Math.round(3840 * ar / 2) * 2 };
  return (
    <Section title="IA sobre este clip" right={<Sparkles size={14} color="var(--ai)" />}>
      <div className="grid2">
        {m.kind === "image" && <Button size="sm" onClick={() => void run("image2video", { prompt: m.generation?.prompt || "subtle natural motion, cinematic", duration: clip.duration, width: m.width || 1280, height: m.height || 720 })}>Animar (img→vídeo)</Button>}
        {m.kind === "image" && <Button size="sm" onClick={() => void run("upscale_image", { scale: 4, ...t4k })}>Escalar a 4K</Button>}
        {m.kind === "image" && <Button size="sm" onClick={() => void run("image2image", { prompt: m.generation?.prompt || "", strength: 0.45 })}>Variación</Button>}
        {m.kind === "image" && <Button size="sm" onClick={() => void run("remove_bg", {})}>Quitar fondo</Button>}
        {m.kind === "video" && <Button size="sm" onClick={() => void run("upscale_video", { scale: 4, ...t4k })}>Escalar a 4K</Button>}
        {m.kind === "video" && <Button size="sm" onClick={() => void run("interpolate", { target_fps: 60 })}>Fluido 60 fps</Button>}
        {m.kind === "video" && <Button size="sm" onClick={() => void run("interpolate", { target_fps: 24, extra: { slowmo: 2 } }, false)}>Cámara lenta ×2</Button>}
        {m.generation && (m.kind === "image" || m.kind === "video") && (
          <Button size="sm" onClick={() => void run(m.generation!.capability, { ...m.generation!.params, prompt: m.generation!.prompt, negative: m.generation!.negative, seed: -1 })}>Regenerar</Button>
        )}
      </div>
      {m.generation && (
        <div className="small muted" style={{ marginTop: 8, lineHeight: 1.45 }}>
          <Badge tone="ai">{m.generation.engine}</Badge> {m.generation.model} · semilla {m.generation.seed}
          <div style={{ marginTop: 4, maxHeight: 80, overflow: "auto" }}>{m.generation.prompt}</div>
        </div>
      )}
    </Section>
  );
}

export default function Inspector() {
  const project = useStore((s) => s.project);
  const selection = useStore((s) => s.selection);
  const presets = useStore((s) => s.presets);
  const fonts = useStore((s) => s.fonts);
  const [luts, setLuts] = useState<string[]>([]);
  useEffect(() => {
    api.get<{ luts: string[] }>("/api/luts").then((r) => setLuts(r.luts)).catch(() => undefined);
  }, []);
  if (!project) return null;
  const st = useStore.getState();

  if (selection.length !== 1) {
    return (
      <div className="panel-body">
        <div className="panel-pad">
          <h3 className="panel-title">Proyecto</h3>
          {selection.length > 1 && <p className="panel-sub">{selection.length} clips seleccionados. Selecciona uno para editarlo.</p>}
        </div>
        <Section title="Lienzo">
          <div className="grid3">
            <Field label="Ancho"><NumberInput value={project.settings.width} step={2} min={16} max={8192} onChange={(v) => st.edit((p) => { p.settings.width = Math.round(v / 2) * 2; })} /></Field>
            <Field label="Alto"><NumberInput value={project.settings.height} step={2} min={16} max={8192} onChange={(v) => st.edit((p) => { p.settings.height = Math.round(v / 2) * 2; })} /></Field>
            <Field label="FPS">
              <Select value={String(project.settings.fps)} onChange={(v) => st.edit((p) => { p.settings.fps = parseFloat(v); })}
                options={(presets?.fps ?? [24, 25, 30, 60]).map((f) => ({ value: String(f), label: String(f) }))} />
            </Field>
          </div>
          <Field label="Fondo"><ColorInput value={project.settings.background} onChange={(v) => st.edit((p) => { p.settings.background = v; })} /></Field>
        </Section>
        <Section title="Notas de producción" defaultOpen={false}>
          <textarea value={project.notes} placeholder="Guion, notas del cliente, referencias…" onChange={(e) => st.edit((p) => { p.notes = e.target.value; }, false)} />
        </Section>
        <Section title="Créditos y licencias" defaultOpen={false}>
          {project.credits.length === 0 ? <p className="small muted">Sin recursos de terceros.</p> : project.credits.map((c, i) => (
            <div key={i} className="small" style={{ marginBottom: 6 }}>{c.attribution || `${c.title} — ${c.creator} (${c.license})`}</div>
          ))}
        </Section>
        <Empty title="Selecciona un clip">Haz clic en un clip de la línea de tiempo para ver sus propiedades, etalonaje, keyframes y acciones de IA.</Empty>
      </div>
    );
  }

  const f = findClip(project, selection[0]);
  if (!f) return null;
  const { clip, track } = f;
  const m = mediaById(project, clip.media_id);
  const patch = (fn: (c: Clip) => void, history = true) => st.edit((p) => { const x = findClip(p, clip.id); if (x) fn(x.clip); }, history);
  const begin = () => st.beginGesture();
  const end = () => st.endGesture();
  const isVisual = clip.kind !== "media" || (m && m.kind !== "audio" && track.kind !== "audio");
  const hasAudio = clip.kind === "media" && m?.has_audio;
  const isMediaTimed = clip.kind === "media" && m && m.kind !== "image";

  return (
    <div className="panel-body">
      <div className="panel-pad" style={{ paddingBottom: 6 }}>
        <div className="row">
          <h3 className="panel-title grow" style={{ margin: 0 }}>
            {clip.kind === "text" ? "Texto" : clip.kind === "color" ? "Color" : clip.kind === "adjustment" ? "Capa de ajuste" : m?.kind === "audio" ? "Audio" : m?.kind === "image" ? "Imagen" : "Vídeo"}
          </h3>
          {m?.ai_generated && <Badge tone="ai">IA</Badge>}
          <IconButton title="Eliminar clip" onClick={() => { st.edit((p) => { const x = findClip(p, clip.id); if (x) x.track.clips = x.track.clips.filter((c) => c.id !== clip.id); }); st.select([]); }}><Trash2 size={15} /></IconButton>
        </div>
        <input type="text" value={clip.name} placeholder={m?.name || "Nombre del clip"} onChange={(e) => patch((c) => { c.name = e.target.value; }, false)} style={{ marginTop: 8 }} />
        {m && <div className="small muted" style={{ marginTop: 6 }}>{m.width ? `${m.width}×${m.height}` : ""} {m.fps ? `· ${m.fps} fps` : ""} {m.duration ? `· ${fmtDur(m.duration)}` : ""} {m.vcodec ? `· ${m.vcodec}` : ""}</div>}
      </div>

      <Section title="Tiempo">
        <div className="grid2">
          <Field label="Inicio (s)"><NumberInput value={clip.start} min={0} onChange={(v) => patch((c) => { c.start = v; })} /></Field>
          <Field label="Duración (s)"><NumberInput value={clip.duration} min={0.04} onChange={(v) => patch((c) => { c.duration = v; })} /></Field>
          {isMediaTimed && <Field label="Entrada en origen (s)"><NumberInput value={clip.in_point} min={0} onChange={(v) => patch((c) => { c.in_point = v; })} /></Field>}
          {isMediaTimed && <Field label="Velocidad"><NumberInput value={clip.speed} min={0.05} max={16} step={0.05} onChange={(v) => patch((c) => { const end = c.in_point + c.duration * c.speed; c.speed = v; c.duration = Math.max(0.04, (end - c.in_point) / v); })} /></Field>}
        </div>
        {isMediaTimed && <Toggle checked={clip.reverse} onChange={(v) => patch((c) => { c.reverse = v; })} label="Marcha atrás" />}
      </Section>

      {clip.kind === "text" && clip.text && (
        <Section title="Texto">
          <textarea value={clip.text.content} onFocus={begin} onBlur={end} onChange={(e) => patch((c) => { c.text!.content = e.target.value; }, false)} />
          <div className="grid2" style={{ marginTop: 8 }}>
            <Field label="Fuente">
              <Select value={clip.text.font} onChange={(v) => patch((c) => { c.text!.font = v; })}
                options={[...new Set(["Inter", ...fonts])].slice(0, 200).map((f2) => ({ value: f2, label: f2 }))} />
            </Field>
            <Field label="Peso"><Select value={clip.text.weight} onChange={(v) => patch((c) => { c.text!.weight = v; })} options={[{ value: "normal", label: "Normal" }, { value: "bold", label: "Negrita" }]} /></Field>
          </div>
          <Slider label="Tamaño" value={clip.text.size} min={0.02} max={0.3} step={0.005} fmt={(v) => `${Math.round(v * 100)}%`} onChange={(v) => patch((c) => { c.text!.size = v; }, false)} onStart={begin} onCommit={end} />
          <div className="grid2">
            <Field label="Color"><ColorInput value={clip.text.color} onChange={(v) => patch((c) => { c.text!.color = v; })} /></Field>
            <Field label="Caja de fondo"><ColorInput value={clip.text.background || ""} onChange={(v) => patch((c) => { c.text!.background = v || null; })} /></Field>
            <Field label="Contorno"><ColorInput value={clip.text.stroke_color} onChange={(v) => patch((c) => { c.text!.stroke_color = v; })} /></Field>
            <Field label="Grosor contorno"><NumberInput value={clip.text.stroke_width} step={0.01} min={0} max={0.3} onChange={(v) => patch((c) => { c.text!.stroke_width = v; })} /></Field>
          </div>
          <div className="grid2">
            <Field label="Alineación"><Select value={clip.text.align} onChange={(v) => patch((c) => { c.text!.align = v; })} options={[{ value: "left", label: "Izquierda" }, { value: "center", label: "Centro" }, { value: "right", label: "Derecha" }]} /></Field>
            <Field label="Animación">
              <Select value={clip.text.animation} onChange={(v) => patch((c) => { c.text!.animation = v; })}
                options={[{ value: "none", label: "Ninguna" }, { value: "fade", label: "Fundido" }, { value: "slide_up", label: "Subir" }, { value: "slide_down", label: "Bajar" }, { value: "zoom", label: "Zoom" }, { value: "typewriter", label: "Máquina de escribir" }]} />
            </Field>
          </div>
          <div className="row" style={{ gap: 14 }}>
            <Toggle checked={clip.text.shadow} onChange={(v) => patch((c) => { c.text!.shadow = v; })} label="Sombra" />
            <Toggle checked={clip.text.uppercase} onChange={(v) => patch((c) => { c.text!.uppercase = v; })} label="MAYÚSCULAS" />
          </div>
          <div className="row" style={{ marginTop: 8, flexWrap: "wrap", gap: 4 }}>
            <Button size="sm" onClick={() => patch((c) => { c.transform.y = 0.88; c.text!.size = 0.045; c.text!.background = "#000000A0"; c.text!.shadow = false; c.text!.animation = "none"; c.text!.weight = "normal"; })}>Subtítulo</Button>
            <Button size="sm" onClick={() => patch((c) => { c.transform.x = 0.28; c.transform.y = 0.8; c.text!.align = "left"; c.text!.size = 0.05; c.text!.background = "#E9246ACC"; c.text!.animation = "slide_up"; })}>Rótulo inferior</Button>
            <Button size="sm" onClick={() => patch((c) => { c.transform.y = 0.5; c.text!.size = 0.12; c.text!.uppercase = true; c.text!.letter_spacing = 0.08; c.text!.animation = "zoom"; })}>Título cine</Button>
          </div>
        </Section>
      )}

      {clip.kind === "color" && (
        <Section title="Color">
          <Field label="Relleno"><ColorInput value={clip.fill} onChange={(v) => patch((c) => { c.fill = v; })} /></Field>
        </Section>
      )}

      {isVisual && clip.kind !== "adjustment" && (
        <Section title="Transformación">
          {clip.kind === "media" && (
            <Field label="Encaje">
              <Select value={clip.transform.fit} onChange={(v) => patch((c) => { c.transform.fit = v; })}
                options={[{ value: "cover", label: "Rellenar (recorta)" }, { value: "contain", label: "Encajar (bandas)" }, { value: "stretch", label: "Estirar" }, { value: "none", label: "Tamaño original" }]} />
            </Field>
          )}
          <KfSlider clip={clip} path="transform.x" label="Posición X" min={-0.5} max={1.5} />
          <KfSlider clip={clip} path="transform.y" label="Posición Y" min={-0.5} max={1.5} />
          <KfSlider clip={clip} path="transform.scale" label="Escala" min={0.05} max={4} fmt={(v) => `${Math.round(v * 100)}%`} />
          <KfSlider clip={clip} path="transform.rotation" label="Rotación" min={-180} max={180} step={0.5} fmt={(v) => `${v.toFixed(1)}°`} />
          <KfSlider clip={clip} path="transform.opacity" label="Opacidad" min={0} max={1} fmt={(v) => `${Math.round(v * 100)}%`} />
          {clip.kind === "media" && (
            <>
              <div className="row" style={{ gap: 14, margin: "4px 0 8px" }}>
                <Toggle checked={clip.transform.flip_h} onChange={(v) => patch((c) => { c.transform.flip_h = v; })} label="Voltear H" />
                <Toggle checked={clip.transform.flip_v} onChange={(v) => patch((c) => { c.transform.flip_v = v; })} label="Voltear V" />
              </div>
              <div className="grid2">
                {(["left", "right", "top", "bottom"] as const).map((k) => (
                  <Slider key={k} label={`Recorte ${({ left: "izq.", right: "der.", top: "sup.", bottom: "inf." })[k]}`} value={clip.transform.crop[k]} min={0} max={0.45}
                    fmt={(v) => `${Math.round(v * 100)}%`} onChange={(v) => patch((c) => { c.transform.crop[k] = v; }, false)} onStart={begin} onCommit={end} />
                ))}
              </div>
              <Button size="sm" kind="ghost" icon={<RotateCcw size={13} />} onClick={() => patch((c) => {
                c.transform = { ...c.transform, x: 0.5, y: 0.5, scale: 1, rotation: 0, opacity: 1, flip_h: false, flip_v: false, crop: { left: 0, top: 0, right: 0, bottom: 0 } };
                for (const k of ["x", "y", "scale", "rotation", "opacity"]) delete c.keyframes[k];
              })}>Restablecer</Button>
            </>
          )}
        </Section>
      )}

      {clip.kind === "media" && m?.kind !== "audio" && track.kind !== "audio" && (
        <Section title="Movimiento de cámara virtual">
          <Field label="Movimiento">
            <Select value={clip.motion.preset} onChange={(v) => patch((c) => { c.motion.preset = v; })} options={[
              { value: "none", label: "Ninguno" }, { value: "push_in", label: "Acercamiento (Ken Burns)" }, { value: "pull_out", label: "Alejamiento" },
              { value: "pan_left", label: "Paneo a la izquierda" }, { value: "pan_right", label: "Paneo a la derecha" }, { value: "tilt_up", label: "Tilt arriba" },
              { value: "tilt_down", label: "Tilt abajo" }, { value: "handheld", label: "Cámara en mano" }, { value: "drift", label: "Deriva suave" },
            ]} />
          </Field>
          {clip.motion.preset !== "none" && <Slider label="Intensidad" value={clip.motion.intensity} min={0.05} max={1} onChange={(v) => patch((c) => { c.motion.intensity = v; }, false)} onStart={begin} onCommit={end} />}
        </Section>
      )}

      {isVisual && clip.kind !== "text" && (
        <Section title="Etalonaje" right={<IconButton title="Restablecer etalonaje" onClick={() => patch((c) => { c.color = defaultGrade(); })}><RotateCcw size={13} /></IconButton>}>
          <Field label="Look">
            <Select value={clip.color.look || ""} onChange={(v) => patch((c) => { c.color.look = v || null; })}
              options={[{ value: "", label: "Ninguno" }, ...(presets?.looks ?? []).map((l) => ({ value: l.id, label: l.label }))]} />
          </Field>
          <Slider label="Exposición" value={clip.color.exposure} min={-2} max={2} reset={0} fmt={(v) => `${v > 0 ? "+" : ""}${v.toFixed(2)} EV`} onChange={(v) => patch((c) => { c.color.exposure = v; }, false)} onStart={begin} onCommit={end} />
          <Slider label="Contraste" value={clip.color.contrast} min={0.3} max={2} reset={1} onChange={(v) => patch((c) => { c.color.contrast = v; }, false)} onStart={begin} onCommit={end} />
          <Slider label="Saturación" value={clip.color.saturation} min={0} max={3} reset={1} onChange={(v) => patch((c) => { c.color.saturation = v; }, false)} onStart={begin} onCommit={end} />
          <Slider label="Temperatura" value={clip.color.temperature} min={-1} max={1} reset={0} onChange={(v) => patch((c) => { c.color.temperature = v; }, false)} onStart={begin} onCommit={end} />
          <Slider label="Matiz (verde ↔ magenta)" value={clip.color.tint} min={-1} max={1} reset={0} onChange={(v) => patch((c) => { c.color.tint = v; }, false)} onStart={begin} onCommit={end} />
          <Slider label="Sombras" value={clip.color.shadows} min={-1} max={1} reset={0} onChange={(v) => patch((c) => { c.color.shadows = v; }, false)} onStart={begin} onCommit={end} />
          <Slider label="Altas luces" value={clip.color.highlights} min={-1} max={1} reset={0} onChange={(v) => patch((c) => { c.color.highlights = v; }, false)} onStart={begin} onCommit={end} />
          <Slider label="Gamma" value={clip.color.gamma} min={0.4} max={2.5} reset={1} onChange={(v) => patch((c) => { c.color.gamma = v; }, false)} onStart={begin} onCommit={end} />
          <Slider label="Viñeta" value={clip.color.vignette} min={0} max={1} reset={0} onChange={(v) => patch((c) => { c.color.vignette = v; }, false)} onStart={begin} onCommit={end} />
          <Slider label="Grano de película" value={clip.color.grain} min={0} max={1} reset={0} onChange={(v) => patch((c) => { c.color.grain = v; }, false)} onStart={begin} onCommit={end} />
          <Slider label="Nitidez" value={clip.color.sharpen} min={0} max={1} reset={0} onChange={(v) => patch((c) => { c.color.sharpen = v; }, false)} onStart={begin} onCommit={end} />
          <Slider label="Desenfoque" value={clip.color.blur} min={0} max={1} reset={0} onChange={(v) => patch((c) => { c.color.blur = v; }, false)} onStart={begin} onCommit={end} />
          <Field label="LUT (.cube)" hint="Sube LUTs en Ajustes → LUTs">
            <Select value={clip.color.lut || ""} onChange={(v) => patch((c) => { c.color.lut = v || null; })} options={[{ value: "", label: "Ninguno" }, ...luts.map((l) => ({ value: l, label: l }))]} />
          </Field>
          {clip.color.lut && <Slider label="Intensidad LUT" value={clip.color.lut_intensity} min={0} max={1} onChange={(v) => patch((c) => { c.color.lut_intensity = v; }, false)} onStart={begin} onCommit={end} />}
        </Section>
      )}

      {isVisual && clip.kind !== "text" && (
        <Section title="Efectos" defaultOpen={clip.effects.length > 0}>
          {clip.effects.map((e, i) => (
            <div key={i} className="card" style={{ padding: 8 }}>
              <div className="row">
                <Toggle checked={e.enabled} onChange={(v) => patch((c) => { c.effects[i].enabled = v; })} />
                <b className="grow">{presets?.effects.find((x) => x.id === e.type)?.label ?? e.type}</b>
                <IconButton title="Quitar" onClick={() => patch((c) => { c.effects.splice(i, 1); })}><Trash2 size={13} /></IconButton>
              </div>
              {Object.entries(e.params).map(([k, v]) => (
                <Field key={k} label={k} inline>
                  {typeof v === "number" ? <NumberInput value={v} step={0.01} onChange={(nv) => patch((c) => { c.effects[i].params[k] = nv; })} />
                    : typeof v === "boolean" ? <Toggle checked={v} onChange={(nv) => patch((c) => { c.effects[i].params[k] = nv; })} />
                      : String(v).startsWith("#") ? <ColorInput value={String(v)} onChange={(nv) => patch((c) => { c.effects[i].params[k] = nv; })} />
                        : <input type="text" value={String(v)} onChange={(ev) => patch((c) => { c.effects[i].params[k] = ev.target.value; })} />}
                </Field>
              ))}
            </div>
          ))}
          <Select value="" onChange={(v) => { if (!v) return; const def = presets?.effects.find((x) => x.id === v); patch((c) => { c.effects.push({ type: v, enabled: true, params: { ...(def?.params ?? {}) } }); }); }}
            options={[{ value: "", label: "+ Añadir efecto…" }, ...(presets?.effects ?? []).map((x) => ({ value: x.id, label: x.label }))]} />
        </Section>
      )}

      {isVisual && (
        <Section title="Transición y fundidos" defaultOpen={!!clip.transition_in || clip.fade_in > 0 || clip.fade_out > 0}>
          <Field label="Transición de entrada">
            <Select value={clip.transition_in?.type || ""} onChange={(v) => patch((c) => { c.transition_in = v ? { type: v, duration: c.transition_in?.duration || 0.6 } : null; })}
              options={[{ value: "", label: "Corte" }, ...(presets?.transitions ?? ["fade"]).map((t) => ({ value: t, label: t }))]} />
          </Field>
          {clip.transition_in && <Slider label="Duración transición" value={clip.transition_in.duration} min={0.1} max={3} fmt={(v) => `${v.toFixed(2)} s`} onChange={(v) => patch((c) => { c.transition_in!.duration = v; }, false)} onStart={begin} onCommit={end} />}
          <p className="small muted" style={{ marginTop: 0 }}>Solapa este clip con el anterior de la misma pista para que la transición use ambos planos.</p>
          <div className="grid2">
            <Slider label="Fundido entrada" value={clip.fade_in} min={0} max={Math.min(5, clip.duration)} fmt={(v) => `${v.toFixed(1)} s`} onChange={(v) => patch((c) => { c.fade_in = v; }, false)} onStart={begin} onCommit={end} />
            <Slider label="Fundido salida" value={clip.fade_out} min={0} max={Math.min(5, clip.duration)} fmt={(v) => `${v.toFixed(1)} s`} onChange={(v) => patch((c) => { c.fade_out = v; }, false)} onStart={begin} onCommit={end} />
          </div>
        </Section>
      )}

      {hasAudio && (
        <Section title="Audio">
          <KfSlider clip={clip} path="volume" label="Volumen" min={0} max={2} fmt={(v) => `${Math.round(v * 100)}%`} />
          <Toggle checked={clip.muted} onChange={(v) => patch((c) => { c.muted = v; })} label="Silenciar clip" />
          <div className="grid2" style={{ marginTop: 8 }}>
            <Slider label="Fundido entrada" value={clip.audio_fade_in} min={0} max={Math.min(10, clip.duration)} fmt={(v) => `${v.toFixed(1)} s`} onChange={(v) => patch((c) => { c.audio_fade_in = v; }, false)} onStart={begin} onCommit={end} />
            <Slider label="Fundido salida" value={clip.audio_fade_out} min={0} max={Math.min(10, clip.duration)} fmt={(v) => `${v.toFixed(1)} s`} onChange={(v) => patch((c) => { c.audio_fade_out = v; }, false)} onStart={begin} onCommit={end} />
          </div>
        </Section>
      )}

      {Object.keys(clip.keyframes).length > 0 && (
        <Section title="Keyframes">
          {Object.entries(clip.keyframes).map(([k, ks]) => (
            <div key={k} style={{ marginBottom: 8 }}>
              <div className="small muted" style={{ marginBottom: 4 }}>{k}</div>
              {ks.map((kf, i) => (
                <div key={i} className="row small" style={{ marginBottom: 3 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => st.setPlayhead(clip.start + kf.t)}>◆ {kf.t.toFixed(2)} s</button>
                  <span className="grow mono">{kf.value.toFixed(3)}</span>
                  <Select value={kf.easing} onChange={(v) => patch((c) => { c.keyframes[k][i].easing = v; })}
                    options={[{ value: "linear", label: "Lineal" }, { value: "ease_in", label: "Entrada suave" }, { value: "ease_out", label: "Salida suave" }, { value: "ease_in_out", label: "Suave" }, { value: "hold", label: "Mantener" }]} />
                  <IconButton title="Borrar" onClick={() => patch((c) => { c.keyframes[k].splice(i, 1); if (!c.keyframes[k].length) delete c.keyframes[k]; })}><Trash2 size={12} /></IconButton>
                </div>
              ))}
            </div>
          ))}
        </Section>
      )}

      {clip.kind === "media" && <AIActions clip={clip} />}

      {m?.credit && (
        <Section title="Licencia" defaultOpen={false}>
          <div className="small">{m.credit.attribution}</div>
        </Section>
      )}
    </div>
  );
}

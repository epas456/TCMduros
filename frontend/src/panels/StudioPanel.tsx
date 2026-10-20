import { AudioLines, Film, Image as ImageIcon, Maximize2, MessageCircle, Music, Repeat2, Scissors, Shuffle, Sparkles, UserRound, Wand2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Badge, Button, Field, Section, Select, Slider, Spinner } from "../components/ui";
import { aspectId } from "../lib/timeline";
import { useStore } from "../store";
import type { Character, WorkflowInfo } from "../types";

type Cap = "text2image" | "text2video" | "image2video" | "image2image" | "tts" | "music" | "upscale" | "interpolate" | "remove_bg" | "lipsync";

const CAPS: { id: Cap; label: string; icon: typeof ImageIcon; backend: string }[] = [
  { id: "text2image", label: "Imagen", icon: ImageIcon, backend: "text2image" },
  { id: "text2video", label: "Vídeo", icon: Film, backend: "text2video" },
  { id: "image2video", label: "Animar", icon: Wand2, backend: "image2video" },
  { id: "image2image", label: "Variar", icon: Repeat2, backend: "image2image" },
  { id: "tts", label: "Voz", icon: AudioLines, backend: "tts" },
  { id: "music", label: "Música", icon: Music, backend: "music" },
  { id: "upscale", label: "Escalar", icon: Maximize2, backend: "upscale_image" },
  { id: "interpolate", label: "Fluidez", icon: Shuffle, backend: "interpolate" },
  { id: "lipsync", label: "Hablar", icon: MessageCircle, backend: "lipsync" },
];

const SIZES: Record<string, [number, number]> = {
  "16:9": [1344, 768], "9:16": [768, 1344], "1:1": [1024, 1024], "4:5": [896, 1120], "2.39:1": [1536, 640], "4:3": [1152, 864], "21:9": [1536, 640], "1.85:1": [1408, 768],
};

const STYLES = [
  { value: "cinematic", label: "Cine" }, { value: "commercial", label: "Publicidad" }, { value: "editorial", label: "Editorial / moda" },
  { value: "documentary", label: "Documental" }, { value: "noir", label: "Noir" }, { value: "fantasy", label: "Fantasía" }, { value: "scifi", label: "Ciencia ficción" },
];

export default function StudioPanel() {
  const project = useStore((s) => s.project)!;
  const engines = useStore((s) => s.engines);
  const capabilities = useStore((s) => s.capabilities);
  const selectedMedia = useStore((s) => s.selectedMedia);
  const [cap, setCap] = useState<Cap>("text2image");
  const [prompt, setPrompt] = useState("");
  const [negative, setNegative] = useState("");
  const [imagination, setImagination] = useState(0.5);
  const [realism, setRealism] = useState(1);
  const [style, setStyle] = useState("cinematic");
  const [aspect, setAspect] = useState(aspectId(project.settings.width, project.settings.height));
  const [seed, setSeed] = useState<string>("");
  const [count, setCount] = useState(1);
  const [duration, setDuration] = useState(5);
  const [fps, setFps] = useState(24);
  const [engine, setEngine] = useState("");
  const [workflow, setWorkflow] = useState("");
  const [workflows, setWorkflows] = useState<WorkflowInfo[]>([]);
  const [source, setSource] = useState("");
  const [strength, setStrength] = useState(0.55);
  const [voice, setVoice] = useState("");
  const [voices, setVoices] = useState<Record<string, [string, string][]>>({});
  const [speechSpeed, setSpeechSpeed] = useState(1);
  const [language, setLanguage] = useState("es");
  const [targetFps, setTargetFps] = useState(60);
  const [upTarget, setUpTarget] = useState("4k");
  const [busy, setBusy] = useState(false);
  const [imagining, setImagining] = useState(false);
  const [variations, setVariations] = useState<{ prompt: string; breakdown: Record<string, string> }[]>([]);
  const [chars, setChars] = useState<Character[]>([]);
  const [charId, setCharId] = useState("");
  const st = useStore.getState();
  const capDef = CAPS.find((c) => c.id === cap)!;
  const sourceMedia = project.media.find((m) => m.id === source);
  const backendCap = cap === "upscale" ? (sourceMedia?.kind === "video" ? "upscale_video" : "upscale_image") : capDef.backend;

  useEffect(() => {
    api.get("/api/ai/voices").then((v) => setVoices(v.kokoro)).catch(() => undefined);
    api.get<{ items: Character[] }>("/api/library/characters").then((r) => setChars(r.items)).catch(() => undefined);
  }, []);
  useEffect(() => {
    setWorkflow("");
    api.get<{ workflows: WorkflowInfo[] }>(`/api/ai/workflows?capability=${backendCap}`).then((r) => setWorkflows(r.workflows)).catch(() => setWorkflows([]));
  }, [backendCap]);
  useEffect(() => {
    if (selectedMedia && ["image2video", "image2image", "upscale", "interpolate", "remove_bg"].includes(cap)) {
      const m = project.media.find((x) => x.id === selectedMedia);
      if (m && (m.kind === "image" || (m.kind === "video" && (cap === "upscale" || cap === "interpolate")))) setSource(m.id);
    }
  }, [selectedMedia, cap, project.media]);

  const capInfo = capabilities[backendCap];
  const engineOpts = useMemo(() => engines.filter((e) => e.capabilities.includes(backendCap)), [engines, backendCap]);
  const needsSource = ["image2video", "image2image", "upscale", "interpolate", "remove_bg", "lipsync"].includes(cap);
  const [audioSrc, setAudioSrc] = useState("");
  const audios = project.media.filter((m) => m.has_audio);
  const sourceKinds = cap === "upscale" ? ["image", "video"] : cap === "interpolate" ? ["video"] : ["image"];
  const sources = project.media.filter((m) => sourceKinds.includes(m.kind));

  async function imagine() {
    if (!prompt.trim()) return;
    setImagining(true);
    try {
      const kind = cap === "text2video" || cap === "image2video" ? "video" : "image";
      const r = await api.post("/api/ai/imagine/prompt", { idea: prompt, kind, style, realism, imagination, seed: seed ? +seed : null });
      setPrompt(r.prompt);
      if (r.negative) setNegative(r.negative);
      st.toast(r.source === "llm" ? "Prompt reescrito por tu LLM local" : "Prompt enriquecido por el motor de imaginación", "ok");
    } catch (e) {
      st.toast((e as Error).message, "error");
    } finally {
      setImagining(false);
    }
  }

  async function vary() {
    if (!prompt.trim()) return;
    const kind = cap === "text2video" || cap === "image2video" ? "video" : "image";
    const r = await api.post("/api/ai/imagine/variations?n=4", { idea: prompt, kind, style, realism, imagination: Math.max(0.6, imagination), seed: Math.floor(Math.random() * 1e6) });
    setVariations(r.variations);
  }

  function useCharacter(id: string) {
    setCharId(id);
    const c = chars.find((x) => x.id === id);
    if (!c) return;
    setPrompt((p) => `${c.identity_prompt}. ${p}`.trim());
    if (c.seed != null) setSeed(String(c.seed));
    if (c.voice?.voice_id) setVoice(c.voice.voice_id);
  }

  async function generate() {
    const [w, h] = SIZES[aspect] ?? [1344, 768];
    const params: Record<string, unknown> = { prompt, negative, width: w, height: h, count, seed: seed ? +seed : null, workflow: workflow || null };
    if (cap === "text2video" || cap === "image2video") Object.assign(params, { duration, fps, count: 1 });
    if (cap === "image2image") params.strength = strength;
    if (cap === "tts") Object.assign(params, { text: prompt, voice: voice || null, speech_speed: speechSpeed, language });
    if (cap === "music") Object.assign(params, { duration });
    if (cap === "interpolate") params.target_fps = targetFps;
    if (cap === "upscale" && sourceMedia) {
      const ar = (sourceMedia.width || 16) / (sourceMedia.height || 9);
      const long = upTarget === "8k" ? 7680 : upTarget === "4k" ? 3840 : 2560;
      Object.assign(params, ar >= 1 ? { target_width: long, target_height: Math.round(long / ar / 2) * 2, scale: 4 } : { target_height: long, target_width: Math.round(long * ar / 2) * 2, scale: 4 });
    }
    if (cap === "lipsync") {
      const a = project.media.find((m) => m.id === audioSrc);
      if (!a) { st.toast("Elige la voz (audio) que dirá el personaje", "warn"); return; }
      Object.assign(params, { duration: a.duration ?? 4, prompt: prompt || "talking naturally to camera, natural lip movement" });
    }
    if (needsSource && !source) {
      st.toast("Elige un medio de entrada", "warn");
      return;
    }
    setBusy(true);
    try {
      const body: Record<string, unknown> = { project_id: project.id, capability: backendCap, params, engine: engine || null };
      if (needsSource) body.source_media_id = source;
      if (cap === "lipsync") body.audio_media_id = audioSrc;
      const j = await api.post("/api/ai/generate", body);
      if (j.ethics?.issues?.length) st.toast(`⚠ ${j.ethics.issues.join(" ")} ${j.ethics.advice.join(" ")}`, "warn");
      st.toast(`En cola: ${capDef.label}. El resultado aparecerá en Medios.`, "info");
    } catch (e) {
      st.toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  const isText = cap === "tts";
  const placeholder = {
    text2image: "Describe la imagen: «retrato de una cocinera vasca en su cocina al amanecer, luz de ventana»",
    text2video: "Describe el plano y su movimiento: «dron sobre acantilados al atardecer, olas rompiendo»",
    image2video: "¿Qué ocurre en el plano? «gira la cabeza hacia la cámara y sonríe, el viento mueve su pelo»",
    image2image: "Cambios: «la misma persona en un mercado de especias de noche»",
    tts: "Texto a locutar…",
    music: "Estado de ánimo: «épica de tráiler», «corporativa alegre», «tensión de thriller»…",
    upscale: "", interpolate: "", remove_bg: "", lipsync: "Opcional: «habla con calma, sonríe al final»",
  }[cap];

  return (
    <div className="panel-pad">
      <h3 className="panel-title"><Sparkles size={16} color="var(--ai)" /> Estudio IA</h3>
      <p className="panel-sub">Genera material nuevo con los motores locales. Todo queda en Medios con su prompt y semilla para regenerarlo.</p>
      <div className="cap-tabs">
        {CAPS.map((c) => {
          const be = c.id === "upscale" ? "upscale_image" : c.backend;
          const q = capabilities[be]?.quality;
          return (
            <button key={c.id} className={`cap-tab ${cap === c.id ? "active" : ""}`} onClick={() => setCap(c.id)}>
              <c.icon size={16} />
              {c.label}
              <span className={`q ${q === "pro" ? "" : "muted"}`}>{q === "pro" ? "PRO" : q === "preview" ? "boceto" : q ? "std" : "—"}</span>
            </button>
          );
        })}
      </div>
      {capInfo && (
        <div className="small" style={{ marginBottom: 10 }}>
          Motor: <Badge tone={capInfo.quality === "pro" ? "ok" : capInfo.quality === "preview" ? "warn" : "info"}>{capInfo.best ?? "ninguno"}</Badge>
          {capInfo.quality === "preview" && <span className="muted"> · sin GPU/modelos se genera un boceto. Configura ComfyUI en «Motores».</span>}
        </div>
      )}

      {needsSource && (
        <Field label="Medio de entrada">
          <Select value={source} onChange={setSource} options={[{ value: "", label: sources.length ? "Elige…" : "Sin medios compatibles" }, ...sources.map((m) => ({ value: m.id, label: `${m.kind === "video" ? "🎬" : "🖼"} ${m.name}` }))]} />
        </Field>
      )}

      {cap === "lipsync" && (
        <Field label="Voz (audio del proyecto)" hint="Genera la voz en «Voz» y elige aquí el retrato en «Medio de entrada».">
          <Select value={audioSrc} onChange={setAudioSrc} options={[{ value: "", label: audios.length ? "Elige…" : "Sin audios" }, ...audios.map((m) => ({ value: m.id, label: `🎙 ${m.name}` }))]} />
        </Field>
      )}

      {cap !== "upscale" && cap !== "interpolate" && cap !== "remove_bg" && (
        <>
          {(cap === "text2image" || cap === "text2video" || cap === "image2image") && chars.length > 0 && (
            <Field label="Personaje del reparto">
              <Select value={charId} onChange={useCharacter} options={[{ value: "", label: "— ninguno —" }, ...chars.map((c) => ({ value: c.id, label: `${c.name} · ${c.role || "personaje"}` }))]} />
            </Field>
          )}
          <div className="prompt-box field">
            <span className="field-label">{isText ? "Texto" : "Prompt"}</span>
            <textarea value={prompt} placeholder={placeholder} onChange={(e) => setPrompt(e.target.value)} rows={5} />
            {!isText && cap !== "music" && (
              <div className="prompt-tools">
                <Button size="sm" kind="ai" icon={imagining ? <Spinner size={12} /> : <Sparkles size={13} />} onClick={() => void imagine()} disabled={!prompt.trim() || imagining}
                  title="Convierte tu idea en un prompt cinematográfico detallado">Imaginar</Button>
                <Button size="sm" kind="ghost" onClick={() => void vary()} disabled={!prompt.trim()} title="Propuestas alternativas">Variantes</Button>
              </div>
            )}
          </div>
          {variations.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              {variations.map((v, i) => (
                <div key={i} className="card" style={{ padding: 8, cursor: "pointer" }} onClick={() => { setPrompt(v.prompt); setVariations([]); }}>
                  <div className="small"><b>Idea {i + 1}:</b> {Object.values(v.breakdown).slice(2).join(" · ")}</div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {(cap === "text2image" || cap === "text2video" || cap === "image2video" || cap === "image2image") && (
        <>
          <Slider label="Imaginación" value={imagination} min={0} max={1} fmt={(v) => (v < 0.3 ? "fiel" : v < 0.65 ? "creativa" : "desbordante")} onChange={setImagination} />
          <Slider label="Realismo" value={realism} min={0} max={1} fmt={(v) => `${Math.round(v * 100)}%`} onChange={setRealism} />
          <div className="grid2">
            <Field label="Estilo"><Select value={style} onChange={setStyle} options={STYLES} /></Field>
            <Field label="Formato"><Select value={aspect} onChange={setAspect} options={Object.keys(SIZES).map((k) => ({ value: k, label: k }))} /></Field>
          </div>
        </>
      )}
      {(cap === "text2video" || cap === "image2video") && (
        <div className="grid2">
          <Field label="Duración (s)"><input type="number" min={1} max={20} step={0.5} value={duration} onChange={(e) => setDuration(+e.target.value)} /></Field>
          <Field label="FPS"><Select value={String(fps)} onChange={(v) => setFps(+v)} options={["16", "24", "25", "30"].map((x) => ({ value: x, label: x }))} /></Field>
        </div>
      )}
      {cap === "image2image" && <Slider label="Intensidad del cambio" value={strength} min={0.1} max={1} onChange={setStrength} />}
      {cap === "music" && <Field label="Duración (s)"><input type="number" min={2} max={300} value={duration} onChange={(e) => setDuration(+e.target.value)} /></Field>}
      {cap === "tts" && (
        <>
          <div className="grid2">
            <Field label="Idioma"><Select value={language} onChange={setLanguage} options={[{ value: "es", label: "Español" }, { value: "en", label: "Inglés" }, { value: "fr", label: "Francés" }, { value: "it", label: "Italiano" }, { value: "pt", label: "Portugués" }]} /></Field>
            <Field label="Voz">
              <Select value={voice} onChange={setVoice} options={[{ value: "", label: "Automática" }, ...Object.entries(voices).flatMap(([lang, vs]) => vs.map(([id, label]) => ({ value: id, label: `${label}` })).filter(() => lang === language || lang === "en"))]} />
            </Field>
          </div>
          <Slider label="Velocidad" value={speechSpeed} min={0.6} max={1.6} fmt={(v) => `${v.toFixed(2)}×`} onChange={setSpeechSpeed} />
        </>
      )}
      {cap === "upscale" && (
        <Field label="Resolución destino">
          <Select value={upTarget} onChange={setUpTarget} options={[{ value: "2k", label: "1440p / 2K" }, { value: "4k", label: "4K UHD" }, { value: "8k", label: "8K UHD" }]} />
        </Field>
      )}
      {cap === "interpolate" && (
        <Field label="FPS destino"><Select value={String(targetFps)} onChange={(v) => setTargetFps(+v)} options={["30", "48", "50", "60", "120"].map((x) => ({ value: x, label: `${x} fps` }))} /></Field>
      )}

      <Section title="Avanzado" defaultOpen={false}>
        {cap !== "tts" && cap !== "music" && cap !== "upscale" && cap !== "interpolate" && (
          <Field label="Prompt negativo"><textarea rows={2} value={negative} onChange={(e) => setNegative(e.target.value)} placeholder="Lo que NO quieres ver" /></Field>
        )}
        <div className="grid2">
          <Field label="Semilla" hint="Vacío = aleatoria"><input type="number" value={seed} onChange={(e) => setSeed(e.target.value)} /></Field>
          {cap === "text2image" && <Field label="Cantidad"><input type="number" min={1} max={8} value={count} onChange={(e) => setCount(+e.target.value)} /></Field>}
        </div>
        <Field label="Motor">
          <Select value={engine} onChange={setEngine} options={[{ value: "", label: "Automático (el mejor disponible)" }, ...engineOpts.map((e) => ({ value: e.id, label: `${e.name}${e.status.available ? "" : " (no disponible)"}`, disabled: !e.status.available }))]} />
        </Field>
        {workflows.length > 0 && (engine === "" || engine === "comfyui") && (
          <Field label="Flujo / modelo ComfyUI">
            <Select value={workflow} onChange={setWorkflow} options={[{ value: "", label: "Automático (mejor calidad instalada)" }, ...workflows.map((w) => ({ value: w.id, label: `${w.label}${w.available === false ? " — falta modelo" : ""}`, disabled: w.available === false }))]} />
          </Field>
        )}
      </Section>
      <div style={{ height: 10 }} />
      <Button kind="ai" size="lg" className="grow" icon={busy ? <Spinner size={14} /> : <Sparkles size={16} />} onClick={() => void generate()}
        disabled={busy || (!prompt.trim() && !needsSource && cap !== "music")}>
        Generar {capDef.label.toLowerCase()}
      </Button>
      {cap === "image2image" && <p className="small muted" style={{ marginTop: 8 }}><UserRound size={12} /> Con FLUX Kontext instalado en ComfyUI, «Variar» mantiene la identidad del personaje en escenas nuevas.</p>}
      {cap === "remove_bg" && <p className="small muted"><Scissors size={12} /> Requiere rembg.</p>}
    </div>
  );
}

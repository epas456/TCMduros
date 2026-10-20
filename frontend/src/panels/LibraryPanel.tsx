import { ArrowLeft, ImagePlus, MapPin, Plus, Sparkles, Trash2, UserRound, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, urls } from "../api";
import { Button, Empty, Field, IconButton, Select, Slider, Spinner, Tabs } from "../components/ui";
import { useStore } from "../store";
import type { Character, Location } from "../types";

export default function LibraryPanel() {
  const [tab, setTab] = useState<"characters" | "locations">("characters");
  const [chars, setChars] = useState<Character[]>([]);
  const [locs, setLocs] = useState<Location[]>([]);
  const [editing, setEditing] = useState<Character | null>(null);
  const [editingLoc, setEditingLoc] = useState<Location | null>(null);
  const [brief, setBrief] = useState("");
  const [imagination, setImagination] = useState(0.5);
  const [busy, setBusy] = useState(false);
  const st = useStore.getState();

  const load = () => {
    api.get<{ items: Character[] }>("/api/library/characters").then((r) => setChars(r.items)).catch(() => undefined);
    api.get<{ items: Location[] }>("/api/library/locations").then((r) => setLocs(r.items)).catch(() => undefined);
  };
  useEffect(load, []);

  async function design() {
    setBusy(true);
    try {
      if (tab === "characters") {
        const c = await api.post<Character>("/api/library/characters/design", { brief, imagination });
        setEditing(c);
      } else {
        const l = await api.post<Location>("/api/library/locations/design", { brief, imagination });
        setEditingLoc(l);
      }
      setBrief("");
      load();
    } catch (e) {
      st.toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  if (editing) return <CharacterEditor c={editing} onBack={() => { setEditing(null); load(); }} />;
  if (editingLoc) return <LocationEditor l={editingLoc} onBack={() => { setEditingLoc(null); load(); }} />;

  return (
    <div className="panel-pad">
      <h3 className="panel-title"><UserRound size={16} color="var(--accent)" /> Reparto y localizaciones</h3>
      <p className="panel-sub">Cada personaje tiene una «biblia» (rasgos, vestuario, voz, semilla y referencias) que mantiene su identidad en todos los planos y proyectos.</p>
      <Tabs value={tab} onChange={setTab} tabs={[{ value: "characters", label: <><UserRound size={14} /> Personajes</> }, { value: "locations", label: <><MapPin size={14} /> Localizaciones</> }]} />
      <div className="card ai" style={{ marginTop: 10 }}>
        <div className="card-title"><Sparkles size={15} /> Diseñar con IA</div>
        <textarea rows={3} value={brief} onChange={(e) => setBrief(e.target.value)}
          placeholder={tab === "characters" ? "«pescadora gallega de 60 años, curtida por el mar, ojos grises, risa contagiosa»" : "«faro abandonado en la Costa da Morte durante un temporal»"} />
        <Slider label="Imaginación" value={imagination} min={0} max={1} onChange={setImagination} />
        <div className="row">
          <Button kind="ai" icon={busy ? <Spinner size={12} /> : <Wand2 size={14} />} onClick={() => void design()} disabled={busy}>
            {brief.trim() ? "Diseñar" : "Sorpréndeme"}
          </Button>
          <Button kind="ghost" icon={<Plus size={14} />} onClick={async () => {
            if (tab === "characters") setEditing(await api.post("/api/library/characters", { name: "Nuevo personaje" }));
            else setEditingLoc(await api.post("/api/library/locations", { name: "Nueva localización" }));
          }}>En blanco</Button>
        </div>
      </div>
      {tab === "characters" ? (
        chars.length === 0 ? <Empty icon={<UserRound size={26} />} title="Sin personajes">Diseña tu primer personaje o lanza el pipeline «Personaje 4K».</Empty> : (
          <div className="char-grid">
            {chars.map((c) => (
              <div key={c.id} className="char-card" onClick={() => setEditing(c)}>
                <div className="char-img" style={c.hero_image ? { backgroundImage: `url(${urls.libImage("characters", c.id, c.hero_image)})` } : undefined}>
                  {!c.hero_image && <UserRound size={30} />}
                </div>
                <div className="char-meta">
                  <div className="media-name">{c.name}</div>
                  <div className="small muted">{[c.role, c.age ? `${c.age} años` : ""].filter(Boolean).join(" · ")}</div>
                </div>
              </div>
            ))}
          </div>
        )
      ) : locs.length === 0 ? <Empty icon={<MapPin size={26} />} title="Sin localizaciones" /> : (
        <div className="char-grid">
          {locs.map((l) => (
            <div key={l.id} className="char-card" onClick={() => setEditingLoc(l)}>
              <div className="char-img" style={{ aspectRatio: "16/9", ...(l.hero_image ? { backgroundImage: `url(${urls.libImage("locations", l.id, l.hero_image)})` } : {}) }}>
                {!l.hero_image && <MapPin size={26} />}
              </div>
              <div className="char-meta"><div className="media-name">{l.name}</div><div className="small muted">{l.time_of_day} · {l.weather}</div></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CharacterEditor({ c: initial, onBack }: { c: Character; onBack: () => void }) {
  const project = useStore((s) => s.project)!;
  const [c, setC] = useState<Character>(initial);
  const [saving, setSaving] = useState(false);
  const st = useStore.getState();
  const set = <K extends keyof Character>(k: K, v: Character[K]) => setC((x) => ({ ...x, [k]: v }));

  async function save(quiet = false) {
    setSaving(true);
    try {
      const r = await api.put<Character>(`/api/library/characters/${c.id}`, c);
      setC(r);
      if (!quiet) st.toast("Personaje guardado", "ok");
    } finally {
      setSaving(false);
    }
  }

  async function sheet() {
    await save(true);
    const r = await api.get<{ views: { view: string; prompt: string; negative: string }[] }>(`/api/library/characters/${c.id}/turnaround`);
    for (const v of r.views.slice(0, 4)) {
      await api.post("/api/ai/generate", { project_id: project.id, capability: "text2image", name: `${c.name} · ${v.view}`,
        params: { prompt: v.prompt, negative: v.negative, width: 896, height: 1152, seed: c.seed } });
    }
    st.toast("Hoja de referencia en cola. Cuando termine, añade la mejor imagen como referencia desde Medios.", "info");
  }

  async function addFromMedia(mid: string) {
    if (!mid) return;
    const fd = new FormData();
    fd.append("project_id", project.id);
    fd.append("media_id", mid);
    fd.append("hero", String(!c.hero_image));
    const r = await api.form(`/api/library/characters/${c.id}/images`, fd);
    setC(r.item);
  }

  const images = project.media.filter((m) => m.kind === "image");
  return (
    <div className="panel-pad">
      <div className="row" style={{ marginBottom: 10 }}>
        <IconButton title="Volver" onClick={() => { void save(true).then(onBack); }}><ArrowLeft size={16} /></IconButton>
        <b className="grow">{c.name}</b>
        {saving && <Spinner size={12} />}
        <IconButton title="Eliminar personaje" onClick={async () => { if (confirm(`¿Eliminar a ${c.name}?`)) { await api.del(`/api/library/characters/${c.id}`); onBack(); } }}><Trash2 size={15} /></IconButton>
      </div>
      {c.reference_images.length > 0 && (
        <div className="face-grid" style={{ marginBottom: 10 }}>
          {c.reference_images.map((n) => (
            <div key={n} className={`face-card ${c.hero_image === n ? "sel" : ""}`} onClick={() => set("hero_image", n)} title="Clic: imagen principal (héroe)">
              <img src={urls.libImage("characters", c.id, n)} alt="" />
            </div>
          ))}
        </div>
      )}
      <div className="row" style={{ marginBottom: 10, gap: 6 }}>
        <Select value="" onChange={(v) => void addFromMedia(v)} options={[{ value: "", label: "+ Referencia desde Medios…" }, ...images.map((m) => ({ value: m.id, label: m.name }))]} className="grow" />
        <Button size="sm" kind="ai" icon={<ImagePlus size={13} />} onClick={() => void sheet()}>Hoja de referencia</Button>
      </div>
      <div className="grid2">
        <Field label="Nombre"><input type="text" value={c.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Papel"><input type="text" value={c.role} onChange={(e) => set("role", e.target.value)} /></Field>
        <Field label="Edad"><input type="number" value={c.age ?? ""} onChange={(e) => set("age", e.target.value ? +e.target.value : null)} /></Field>
        <Field label="Género"><input type="text" value={c.gender} onChange={(e) => set("gender", e.target.value)} /></Field>
      </div>
      <Field label="Prompt de identidad (continuidad visual)" hint="Se inyecta en cada plano donde aparece el personaje.">
        <textarea rows={5} value={c.identity_prompt} onChange={(e) => set("identity_prompt", e.target.value)} />
      </Field>
      <div className="grid2">
        <Field label="Origen"><input type="text" value={c.heritage} onChange={(e) => set("heritage", e.target.value)} /></Field>
        <Field label="Complexión"><input type="text" value={c.build} onChange={(e) => set("build", e.target.value)} /></Field>
      </div>
      <Field label="Rostro"><input type="text" value={c.face} onChange={(e) => set("face", e.target.value)} /></Field>
      <div className="grid2">
        <Field label="Ojos"><input type="text" value={c.eyes} onChange={(e) => set("eyes", e.target.value)} /></Field>
        <Field label="Pelo"><input type="text" value={c.hair} onChange={(e) => set("hair", e.target.value)} /></Field>
      </div>
      <Field label="Piel y marcas"><input type="text" value={c.skin} onChange={(e) => set("skin", e.target.value)} /></Field>
      <Field label="Vestuario"><input type="text" value={c.wardrobe} onChange={(e) => set("wardrobe", e.target.value)} /></Field>
      <Field label="Personalidad"><input type="text" value={c.personality} onChange={(e) => set("personality", e.target.value)} /></Field>
      <Field label="Historia"><textarea rows={3} value={c.backstory} onChange={(e) => set("backstory", e.target.value)} /></Field>
      <div className="grid2">
        <Field label="Voz (Kokoro)"><input type="text" value={c.voice.voice_id} onChange={(e) => set("voice", { ...c.voice, voice_id: e.target.value })} placeholder="ef_dora / em_alex" /></Field>
        <Field label="Semilla"><input type="number" value={c.seed ?? ""} onChange={(e) => set("seed", e.target.value ? +e.target.value : null)} /></Field>
      </div>
      {c.inspiration.length > 0 && (
        <Field label="Inspiración (licencias)">
          {c.inspiration.map((cr, i) => <div key={i} className="small muted">{cr.attribution}</div>)}
        </Field>
      )}
      <div className="row">
        <Button kind="primary" onClick={() => void save()}>Guardar</Button>
        <Button onClick={async () => { await save(true); const r = await api.post(`/api/library/characters/${c.id}/to-project/${project.id}`); st.mergeMedia(r.media); st.toast("Referencias añadidas a Medios", "ok"); }}>Usar en el proyecto</Button>
      </div>
    </div>
  );
}

function LocationEditor({ l: initial, onBack }: { l: Location; onBack: () => void }) {
  const project = useStore((s) => s.project)!;
  const [l, setL] = useState<Location>(initial);
  const st = useStore.getState();
  const set = <K extends keyof Location>(k: K, v: Location[K]) => setL((x) => ({ ...x, [k]: v }));
  const save = async (quiet = false) => {
    const r = await api.put<Location>(`/api/library/locations/${l.id}`, l);
    setL(r);
    if (!quiet) st.toast("Localización guardada", "ok");
  };
  return (
    <div className="panel-pad">
      <div className="row" style={{ marginBottom: 10 }}>
        <IconButton title="Volver" onClick={() => { void save(true).then(onBack); }}><ArrowLeft size={16} /></IconButton>
        <b className="grow">{l.name}</b>
        <IconButton title="Eliminar" onClick={async () => { if (confirm("¿Eliminar localización?")) { await api.del(`/api/library/locations/${l.id}`); onBack(); } }}><Trash2 size={15} /></IconButton>
      </div>
      <Field label="Nombre"><input type="text" value={l.name} onChange={(e) => set("name", e.target.value)} /></Field>
      <Field label="Prompt de identidad"><textarea rows={5} value={l.identity_prompt} onChange={(e) => set("identity_prompt", e.target.value)} /></Field>
      <div className="grid2">
        <Field label="Época"><input type="text" value={l.era} onChange={(e) => set("era", e.target.value)} /></Field>
        <Field label="Momento del día"><input type="text" value={l.time_of_day} onChange={(e) => set("time_of_day", e.target.value)} /></Field>
        <Field label="Clima"><input type="text" value={l.weather} onChange={(e) => set("weather", e.target.value)} /></Field>
        <Field label="Ambiente sonoro"><input type="text" value={l.ambience} onChange={(e) => set("ambience", e.target.value)} /></Field>
      </div>
      <Field label="Iluminación"><input type="text" value={l.lighting} onChange={(e) => set("lighting", e.target.value)} /></Field>
      <Field label="Atrezo"><input type="text" value={l.props} onChange={(e) => set("props", e.target.value)} /></Field>
      <div className="row">
        <Button kind="primary" onClick={() => void save()}>Guardar</Button>
        <Button kind="ai" icon={<Sparkles size={13} />} onClick={async () => {
          await save(true);
          await api.post("/api/ai/generate", { project_id: project.id, capability: "text2image", name: `Localización · ${l.name}`, params: { prompt: `establishing shot, ${l.identity_prompt}, photorealistic, cinematic, 8k`, width: 1344, height: 768, seed: l.seed } });
          st.toast("Imagen de la localización en cola", "info");
        }}>Generar plano general</Button>
      </div>
    </div>
  );
}

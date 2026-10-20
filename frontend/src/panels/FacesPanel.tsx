import { Download, ExternalLink, FileSignature, ScanFace, Search, Sparkles, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, urls, withToken } from "../api";
import { Badge, Button, Empty, Field, IconButton, Spinner, Tabs, Toggle } from "../components/ui";
import { useStore } from "../store";
import type { Consent, FaceRef, FaceResult } from "../types";

const LICS = [
  { id: "cc0", label: "CC0" }, { id: "pdm", label: "Dominio público" }, { id: "by", label: "CC BY" }, { id: "by-sa", label: "CC BY-SA" },
];
const PROVIDERS = [
  { id: "openverse", label: "Openverse" }, { id: "wikimedia", label: "Wikimedia" }, { id: "pexels", label: "Pexels" }, { id: "unsplash", label: "Unsplash" },
];

export default function FacesPanel() {
  const [tab, setTab] = useState<"search" | "library" | "consents">("search");
  const [q, setQ] = useState("retrato mujer mayor sonriendo");
  const [lics, setLics] = useState<string[]>(["cc0", "pdm", "by", "by-sa"]);
  const [provs, setProvs] = useState<string[]>(["openverse", "wikimedia", "pexels", "unsplash"]);
  const [results, setResults] = useState<FaceResult[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(1);
  const [faces, setFaces] = useState<FaceRef[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [consents, setConsents] = useState<Consent[]>([]);
  const [importing, setImporting] = useState<string | null>(null);
  const st = useStore.getState();
  const fileRef = useRef<HTMLInputElement>(null);

  const loadLib = () => {
    api.get<{ items: FaceRef[]; notice: string }>("/api/faces").then((r) => { setFaces(r.items); setNotice(r.notice); }).catch(() => undefined);
    api.get<{ items: Consent[] }>("/api/consents").then((r) => setConsents(r.items)).catch(() => undefined);
  };
  useEffect(loadLib, []);

  async function search(pg = 1) {
    setBusy(true);
    try {
      const r = await api.get(`/api/faces/search?q=${encodeURIComponent(q)}&providers=${provs.join(",")}&licenses=${lics.join(",")}&page=${pg}`);
      setResults(pg === 1 ? r.results : [...results, ...r.results]);
      setErrors(r.errors);
      setNotice(r.notice);
      setPage(pg);
    } catch (e) {
      st.toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function importFace(r: FaceResult) {
    setImporting(r.id);
    try {
      await api.post("/api/faces/import", { result: r, describe: true });
      st.toast("Rostro guardado en tu biblioteca de inspiración", "ok");
      loadLib();
    } catch (e) {
      st.toast((e as Error).message, "error");
    } finally {
      setImporting(null);
    }
  }

  async function designFromFaces() {
    const c = await api.post("/api/library/characters/design", { brief: "", face_ids: picked, imagination: 0.6 });
    st.toast(`Personaje «${c.name}» creado en Reparto, inspirado en ${picked.length} rostro(s)`, "ok");
    setPicked([]);
    st.set({ leftTab: "library" });
  }

  return (
    <div className="panel-pad">
      <h3 className="panel-title"><ScanFace size={16} color="var(--ai)" /> Rostros de inspiración</h3>
      <p className="panel-sub">Busca caras con licencia libre para inspirar a tus personajes. Se guarda la atribución en los créditos de cada proyecto.</p>
      {notice && <div className="notice">⚖️ {notice}</div>}
      <Tabs value={tab} onChange={setTab} tabs={[{ value: "search", label: "Buscar" }, { value: "library", label: `Mi biblioteca (${faces.length})` }, { value: "consents", label: "Consentimientos" }]} />
      <div style={{ height: 10 }} />

      {tab === "search" && (
        <>
          <div className="row">
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void search(1)} placeholder="anciano pescador, mujer joven pecas…" />
            <Button kind="primary" icon={busy ? <Spinner size={12} /> : <Search size={14} />} onClick={() => void search(1)}>Buscar</Button>
          </div>
          <div className="row small" style={{ flexWrap: "wrap", gap: 4, margin: "8px 0" }}>
            {LICS.map((l) => <span key={l.id} className={`chip ${lics.includes(l.id) ? "active" : ""}`} onClick={() => setLics(lics.includes(l.id) ? lics.filter((x) => x !== l.id) : [...lics, l.id])}>{l.label}</span>)}
          </div>
          <div className="row small" style={{ flexWrap: "wrap", gap: 4, marginBottom: 10 }}>
            {PROVIDERS.map((p) => <span key={p.id} className={`chip ${provs.includes(p.id) ? "active" : ""}`} onClick={() => setProvs(provs.includes(p.id) ? provs.filter((x) => x !== p.id) : [...provs, p.id])}>{p.label}</span>)}
          </div>
          {Object.keys(errors).length > 0 && <div className="small muted" style={{ marginBottom: 8 }}>Sin respuesta de: {Object.keys(errors).join(", ")} (¿sin conexión?)</div>}
          {results.length === 0 ? <Empty icon={<Search size={24} />} title="Busca rostros">Pexels y Unsplash requieren clave gratuita (Ajustes).</Empty> : (
            <>
              <div className="face-grid">
                {results.map((r) => (
                  <div key={r.id} className="face-card" title={r.attribution}>
                    <img src={r.thumb_url} alt={r.title} loading="lazy" referrerPolicy="no-referrer" />
                    <div className="fc-meta"><Badge tone={r.commercial_ok ? "ok" : "warn"}>{r.license.toUpperCase()}</Badge> {r.provider}</div>
                    <div className="fc-actions">
                      <IconButton title="Guardar como inspiración" onClick={() => void importFace(r)} disabled={!r.commercial_ok || importing === r.id}>
                        {importing === r.id ? <Spinner size={12} /> : <Download size={14} />}
                      </IconButton>
                      {r.landing_url && <a className="icon-btn" href={r.landing_url} target="_blank" rel="noreferrer" title="Ver original"><ExternalLink size={14} /></a>}
                    </div>
                  </div>
                ))}
              </div>
              <Button size="sm" kind="ghost" onClick={() => void search(page + 1)} disabled={busy}>Cargar más</Button>
            </>
          )}
        </>
      )}

      {tab === "library" && (
        <>
          <div className="row" style={{ marginBottom: 10 }}>
            <Button size="sm" icon={<Upload size={13} />} onClick={() => fileRef.current?.click()}>Subir rostro propio</Button>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const fd = new FormData();
              fd.append("file", f);
              await api.form("/api/faces/upload", fd);
              loadLib();
            }} />
            <div className="spacer" />
            <Button size="sm" kind="ai" icon={<Sparkles size={13} />} disabled={!picked.length} onClick={() => void designFromFaces()}>Crear personaje ({picked.length})</Button>
          </div>
          {faces.length === 0 ? <Empty title="Biblioteca vacía">Guarda rostros desde «Buscar» o sube fotografías propias.</Empty> : (
            <div className="face-grid">
              {faces.map((f) => {
                const on = picked.includes(f.id);
                return (
                  <div key={f.id} className={`face-card ${on ? "sel" : ""}`} title={f.description || f.credit.attribution} onClick={() => setPicked(on ? picked.filter((x) => x !== f.id) : [...picked, f.id])}>
                    <img src={urls.face(f.id)} alt="" />
                    <div className="fc-meta">{f.credit.license.toUpperCase()} {f.description ? "· descrito" : ""}</div>
                    <div className="fc-actions">
                      <IconButton title="Describir rasgos con visión IA" onClick={async (e) => { e.stopPropagation(); try { await api.post(`/api/faces/${f.id}/describe`); loadLib(); } catch (err) { st.toast((err as Error).message, "warn"); } }}><Sparkles size={13} /></IconButton>
                      <IconButton title="Eliminar" onClick={async (e) => { e.stopPropagation(); await api.del(`/api/faces/${f.id}`); loadLib(); }}><Trash2 size={13} /></IconButton>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {tab === "consents" && <Consents items={consents} reload={loadLib} />}
    </div>
  );
}

function Consents({ items, reload }: { items: Consent[]; reload: () => void }) {
  const [name, setName] = useState("");
  const [scope, setScope] = useState("");
  const [until, setUntil] = useState("");
  const [signed, setSigned] = useState("");
  const [agree, setAgree] = useState(false);
  const doc = useRef<HTMLInputElement>(null);
  const st = useStore.getState();
  async function add() {
    const fd = new FormData();
    fd.append("person_name", name);
    fd.append("scope", scope);
    fd.append("valid_until", until);
    fd.append("signed_on", signed);
    const f = doc.current?.files?.[0];
    if (f) fd.append("document", f);
    await api.form("/api/consents", fd);
    setName(""); setScope(""); setUntil(""); setSigned(""); setAgree(false);
    st.toast("Cesión de derechos registrada", "ok");
    reload();
  }
  return (
    <>
      <p className="panel-sub">Para recrear con IA a una persona real (actor, modelo, empleado) registra aquí su cesión de derechos de imagen firmada. Así queda trazado en el manifiesto de procedencia.</p>
      <div className="card">
        <Field label="Persona"><input type="text" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Ámbito de uso"><input type="text" value={scope} onChange={(e) => setScope(e.target.value)} placeholder="Campaña primavera 2026, redes sociales y TV, España" /></Field>
        <div className="grid2">
          <Field label="Firmado el"><input type="text" value={signed} onChange={(e) => setSigned(e.target.value)} placeholder="2026-10-01" /></Field>
          <Field label="Válido hasta"><input type="text" value={until} onChange={(e) => setUntil(e.target.value)} placeholder="2027-10-01" /></Field>
        </div>
        <Field label="Documento firmado (PDF/imagen)"><input ref={doc} type="file" accept=".pdf,image/*" /></Field>
        <Toggle checked={agree} onChange={setAgree} label="Confirmo que la cesión es válida y cubre el uso con IA" />
        <div style={{ height: 8 }} />
        <Button kind="primary" icon={<FileSignature size={14} />} disabled={!name.trim() || !agree} onClick={() => void add()}>Registrar</Button>
      </div>
      {items.map((c) => (
        <div key={c.id} className="list-row">
          <div className="grow"><b>{c.person_name}</b><div className="small muted">{c.scope} {c.valid_until ? `· hasta ${c.valid_until}` : ""}</div></div>
          {c.document && <a className="icon-btn" href={withToken(`/api/consents/${c.id}/document`)} target="_blank" rel="noreferrer" title="Ver documento"><ExternalLink size={14} /></a>}
          <IconButton title="Eliminar" onClick={async () => { await api.del(`/api/consents/${c.id}`); reload(); }}><Trash2 size={14} /></IconButton>
        </div>
      ))}
    </>
  );
}

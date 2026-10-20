import { CheckCircle2, CircleDashed, Cpu, Download, RefreshCw, Server } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, Button, Section, Spinner } from "../components/ui";
import { useStore } from "../store";

interface ModelEntry {
  id: string; name: string; kind: string; engine: string; vram: number; license: string; commercial: boolean | null; notes?: string; installed: boolean | null; size_gb: number;
}

export default function EnginesPanel() {
  const engines = useStore((s) => s.engines);
  const caps = useStore((s) => s.capabilities);
  const [sys, setSys] = useState<any>(null);
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const st = useStore.getState();

  const load = async (refresh = false) => {
    setRefreshing(true);
    try {
      await st.loadEngines(refresh);
      setSys(await api.get("/api/system"));
      setModels((await api.get<{ models: ModelEntry[] }>("/api/models")).models);
    } finally {
      setRefreshing(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);

  async function download(m: ModelEntry) {
    try {
      const j = await api.post(`/api/models/${m.id}/download`);
      st.upsertJob(j);
      st.toast(`Descargando ${m.name}…`, "info");
    } catch (e) {
      st.toast((e as Error).message, "error");
    }
  }

  return (
    <div className="panel-pad">
      <div className="row" style={{ marginBottom: 6 }}>
        <h3 className="panel-title grow" style={{ margin: 0 }}><Cpu size={16} /> Motores y modelos</h3>
        <Button size="sm" kind="ghost" icon={refreshing ? <Spinner size={12} /> : <RefreshCw size={13} />} onClick={() => void load(true)}>Comprobar</Button>
      </div>
      {sys && (
        <div className="card">
          <div className="kv">
            <span>Equipo</span><span>{sys.hardware.os} · {sys.hardware.cores} núcleos · {sys.hardware.ram_gb} GB</span>
            <span>GPU</span><span>{sys.hardware.gpus.map((g: any) => `${g.name} (${g.vram_gb} GB)`).join(", ") || "Ninguna"}</span>
            <span>Nivel</span><span><Badge tone={sys.hardware.tier === "cpu" ? "warn" : "ok"}>{sys.tier_label}</Badge></span>
            <span>FFmpeg</span><span>{sys.ffmpeg.ok ? sys.ffmpeg.version.replace("ffmpeg version ", "").split(" ")[0] : "NO ENCONTRADO"}</span>
          </div>
          <div className="sep" />
          <div className="small muted" style={{ marginBottom: 4 }}>Recomendado para tu equipo</div>
          <div className="kv">
            <span>Imagen</span><span>{sys.recommendations.image}</span>
            <span>Vídeo</span><span>{sys.recommendations.video}</span>
            <span>Guionista</span><span>{sys.recommendations.llm}</span>
            <span>Voz</span><span>{sys.recommendations.tts}</span>
          </div>
        </div>
      )}
      <Section title="Capacidades">
        <div className="cap-grid">
          {Object.entries(caps).map(([k, v]) => (
            <div key={k} style={{ display: "contents" }}>
              <span>{v.label}</span>
              <span>{v.best ? <Badge tone={v.quality === "pro" ? "ok" : v.quality === "preview" ? "warn" : "info"}>{v.best}</Badge> : <Badge>—</Badge>}</span>
            </div>
          ))}
        </div>
      </Section>
      <Section title="Motores">
        {engines.map((e) => (
          <div key={e.id} className="engine-row">
            {e.status.available ? <CheckCircle2 size={16} color="var(--ok)" /> : <CircleDashed size={16} color="var(--muted)" />}
            <div className="grow">
              <div className="engine-name">{e.name} {e.quality === "pro" && <Badge tone="ok">PRO</Badge>}</div>
              <div className="small muted">{e.status.detail}</div>
              {e.status.available && e.status.models.length > 0 && <div className="small" style={{ marginTop: 3, color: "var(--text-2)" }}>{e.status.models.slice(0, 6).join(" · ")}</div>}
            </div>
          </div>
        ))}
        <p className="small muted">Configura direcciones y rutas en <a href="#" onClick={(e) => { e.preventDefault(); st.set({ settingsOpen: true }); }}>Ajustes</a>.</p>
      </Section>
      <Section title="Catálogo de modelos abiertos">
        <p className="small muted" style={{ marginTop: 0 }}>Los modelos de ComfyUI se descargan en su carpeta (configúrala en Ajustes). Revisa siempre la licencia antes de un uso comercial.</p>
        {models.map((m) => (
          <div key={m.id} className="engine-row">
            <Server size={15} color="var(--muted)" />
            <div className="grow">
              <div className="engine-name">{m.name}</div>
              <div className="small muted">{m.kind} · {m.engine} · {m.vram ? `${m.vram} GB VRAM` : "CPU"} {m.size_gb ? `· ${m.size_gb} GB` : ""}</div>
              <div className="small" style={{ marginTop: 2 }}>
                <Badge tone={m.commercial ? "ok" : m.commercial === false ? "error" : "warn"} title="Licencia orientativa">{m.license}</Badge>
              </div>
              {m.notes && <div className="small muted" style={{ marginTop: 3 }}>{m.notes}</div>}
            </div>
            {m.installed ? <Badge tone="ok">Instalado</Badge> : (m.engine === "comfyui" || m.engine === "ollama") ? (
              <Button size="sm" icon={<Download size={13} />} onClick={() => void download(m)}>Descargar</Button>
            ) : <Badge>auto</Badge>}
          </div>
        ))}
      </Section>
    </div>
  );
}

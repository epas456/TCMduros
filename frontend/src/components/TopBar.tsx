import { Clapperboard, Cpu, Download, Home as HomeIcon, ListChecks, Redo2, Settings, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { useStore } from "../store";
import { Button, IconButton, Spinner } from "./ui";

export function Logo({ onClick }: { onClick?: () => void }) {
  return (
    <div className="logo" onClick={onClick} title="durosTCM">
      <svg className="logo-mark" viewBox="0 0 64 64" aria-hidden>
        <defs>
          <linearGradient id="lg" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stopColor="#FF7A1A" />
            <stop offset="1" stopColor="#E9246A" />
          </linearGradient>
        </defs>
        <rect width="64" height="64" rx="14" fill="#141821" />
        <path d="M18 14h14c11 0 18 7 18 18s-7 18-18 18H18z" fill="url(#lg)" />
        <path d="M27 24v16l12-8z" fill="#0b0d12" />
      </svg>
      <span>duros<b>TCM</b></span>
    </div>
  );
}

export default function TopBar() {
  const view = useStore((s) => s.view);
  const project = useStore((s) => s.project);
  const dirty = useStore((s) => s.dirty);
  const saving = useStore((s) => s.saving);
  const past = useStore((s) => s.past.length);
  const future = useStore((s) => s.future.length);
  const jobs = useStore((s) => s.jobs);
  const centerTab = useStore((s) => s.centerTab);
  const [hw, setHw] = useState<{ label: string; ok: boolean } | null>(null);

  useEffect(() => {
    api.get("/api/system").then((s) => setHw({ label: s.tier_label, ok: s.hardware.tier !== "cpu" })).catch(() => undefined);
  }, []);

  const running = Object.values(jobs).filter((j) => j.status === "running" || j.status === "queued");
  const st = useStore.getState();

  return (
    <header className="topbar">
      <Logo onClick={() => { if (view === "editor") { void st.save(); st.closeProject(); } }} />
      {view === "editor" && project && (
        <>
          <IconButton title="Inicio" onClick={() => { void st.save(); st.closeProject(); }}><HomeIcon size={17} /></IconButton>
          <input className="project-name" value={project.name} aria-label="Nombre del proyecto"
            onChange={(e) => st.edit((p) => { p.name = e.target.value; }, false)} />
          <span className="save-state">
            {saving ? <><Spinner size={10} /> Guardando…</> : dirty ? "Cambios sin guardar" : "Guardado"}
          </span>
          <IconButton title="Deshacer (Ctrl+Z)" disabled={!past} onClick={() => st.undo()}><Undo2 size={17} /></IconButton>
          <IconButton title="Rehacer (Ctrl+Shift+Z)" disabled={!future} onClick={() => st.redo()}><Redo2 size={17} /></IconButton>
          <span className="small muted">{project.settings.width}×{project.settings.height} · {project.settings.fps} fps</span>
        </>
      )}
      <div className="spacer" />
      {hw && (
        <span className="hw-badge" title="Capacidad de este equipo para la IA local">
          <Cpu size={13} /> <span className="dot" style={{ background: hw.ok ? "var(--ok)" : "var(--warn)" }} /> {hw.label}
        </span>
      )}
      <Button kind="ghost" size="sm" icon={running.length ? <Spinner size={12} /> : <ListChecks size={15} />} onClick={() => { const s = useStore.getState(); s.set({ jobsOpen: !s.jobsOpen }); }}>
        {running.length ? `${running.length} en curso` : "Trabajos"}
      </Button>
      <IconButton title="Ajustes" onClick={() => st.set({ settingsOpen: true })}><Settings size={17} /></IconButton>
      {view === "editor" && (
        <>
          {project?.storyboard && (
            <Button size="sm" icon={<Clapperboard size={15} />} onClick={() => st.set({ centerTab: centerTab === "storyboard" ? "viewer" : "storyboard" })}>
              {centerTab === "storyboard" ? "Visor" : "Storyboard"}
            </Button>
          )}
          <Button kind="primary" icon={<Download size={15} />} onClick={() => st.set({ exportOpen: true })}>Exportar</Button>
        </>
      )}
    </header>
  );
}

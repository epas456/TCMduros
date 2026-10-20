import { useState } from "react";
import { api } from "../api";
import { useStore } from "../store";
import { Badge, Button, Empty, IconButton, Progress, useOutside } from "./ui";
import { X } from "lucide-react";

function fmtEta(s: number | null) {
  if (s == null) return "";
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

export function JobsPopover() {
  const jobs = useStore((s) => s.jobs);
  const [open, setOpen] = useState<string | null>(null);
  const ref = useOutside(() => useStore.getState().set({ jobsOpen: false }));
  const list = Object.values(jobs).sort((a, b) => b.created - a.created).slice(0, 60);
  return (
    <div className="jobs-pop" ref={ref}>
      <div className="row" style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)" }}>
        <b className="grow">Trabajos</b>
        <Button size="sm" kind="ghost" onClick={async () => {
          await api.del("/api/jobs");
          const keep = Object.fromEntries(Object.entries(useStore.getState().jobs).filter(([, j]) => j.status === "running" || j.status === "queued"));
          useStore.getState().set({ jobs: keep });
        }}>Limpiar terminados</Button>
        <IconButton title="Cerrar" onClick={() => useStore.getState().set({ jobsOpen: false })}><X size={15} /></IconButton>
      </div>
      {list.length === 0 && <Empty title="Sin trabajos">Las generaciones de IA, exportaciones y descargas aparecerán aquí.</Empty>}
      {list.map((j) => (
        <div key={j.id} className="job">
          <div className="job-head">
            <span className="job-title" title={j.title}>{j.parent_id ? "↳ " : ""}{j.title}</span>
            <Badge tone={j.status === "done" ? "ok" : j.status === "error" ? "error" : j.status === "running" ? "info" : j.status === "cancelled" ? "warn" : "default"}>
              {({ queued: "en cola", running: "en curso", done: "hecho", error: "error", cancelled: "cancelado" } as const)[j.status]}
            </Badge>
            {(j.status === "running" || j.status === "queued") && <Button size="sm" kind="ghost" onClick={() => api.post(`/api/jobs/${j.id}/cancel`)}>Cancelar</Button>}
          </div>
          {(j.status === "running" || j.status === "queued") && <Progress value={j.progress} />}
          <div className="job-stage">
            <span>{j.error ? j.error.slice(0, 160) : j.stage}</span>
            <span>{j.status === "running" ? `${Math.round(j.progress * 100)}% ${j.eta ? "· " + fmtEta(j.eta) : ""}` : ""}</span>
          </div>
          {j.logs.length > 0 && <a href="#" className="small" onClick={(e) => { e.preventDefault(); setOpen(open === j.id ? null : j.id); }}>{open === j.id ? "Ocultar registro" : "Ver registro"}</a>}
          {open === j.id && <div className="job-logs">{j.logs.join("\n")}</div>}
        </div>
      ))}
    </div>
  );
}

export function Toasts() {
  const toasts = useStore((s) => s.toasts);
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`} onClick={() => useStore.getState().dismissToast(t.id)}>{t.text}</div>
      ))}
    </div>
  );
}

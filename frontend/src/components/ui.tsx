import { X } from "lucide-react";
import { ReactNode, useEffect, useRef, useState } from "react";

export function Button({
  children, onClick, kind = "default", size = "md", disabled, title, type = "button", className = "", icon,
}: {
  children?: ReactNode; onClick?: (e: React.MouseEvent) => void; kind?: "default" | "primary" | "ghost" | "danger" | "ai"; size?: "sm" | "md" | "lg";
  disabled?: boolean; title?: string; type?: "button" | "submit"; className?: string; icon?: ReactNode;
}) {
  return (
    <button type={type} className={`btn btn-${kind} btn-${size} ${className}`} onClick={onClick} disabled={disabled} title={title}>
      {icon}
      {children != null && <span>{children}</span>}
    </button>
  );
}

export function IconButton({ children, onClick, title, active, disabled, className = "" }: {
  children: ReactNode; onClick?: (e: React.MouseEvent) => void; title?: string; active?: boolean; disabled?: boolean; className?: string;
}) {
  return (
    <button type="button" className={`icon-btn ${active ? "active" : ""} ${className}`} onClick={onClick} title={title} aria-label={title} disabled={disabled}>
      {children}
    </button>
  );
}

export function Field({ label, children, hint, inline }: { label: string; children: ReactNode; hint?: string; inline?: boolean }) {
  return (
    <label className={`field ${inline ? "inline" : ""}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function Slider({ label, value, min, max, step = 0.01, onChange, onCommit, onStart, fmt, reset }: {
  label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void; onCommit?: () => void;
  onStart?: () => void; fmt?: (v: number) => string; reset?: number;
}) {
  return (
    <div className="slider">
      <div className="slider-head">
        <span>{label}</span>
        <span className="slider-val" onDoubleClick={() => reset !== undefined && onChange(reset)} title={reset !== undefined ? "Doble clic para restablecer" : undefined}>
          {fmt ? fmt(value) : Number(value).toFixed(step >= 1 ? 0 : 2)}
        </span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))} onPointerDown={onStart} onPointerUp={onCommit} />
    </div>
  );
}

export function NumberInput({ value, onChange, step = 0.1, min, max, className = "" }: {
  value: number; onChange: (v: number) => void; step?: number; min?: number; max?: number; className?: string;
}) {
  const [txt, setTxt] = useState(String(value));
  useEffect(() => setTxt(String(Number(value.toFixed(4)))), [value]);
  return (
    <input className={`num ${className}`} type="number" step={step} min={min} max={max} value={txt}
      onChange={(e) => setTxt(e.target.value)}
      onBlur={() => { const v = parseFloat(txt); if (!isNaN(v)) onChange(Math.min(max ?? Infinity, Math.max(min ?? -Infinity, v))); else setTxt(String(value)); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );
}

export function Select<T extends string>({ value, onChange, options, className = "" }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string; disabled?: boolean }[]; className?: string;
}) {
  return (
    <select className={`select ${className}`} value={value} onChange={(e) => onChange(e.target.value as T)}>
      {options.map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
      ))}
    </select>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-track"><span className="toggle-thumb" /></span>
      {label && <span>{label}</span>}
    </label>
  );
}

export function Section({ title, children, defaultOpen = true, right }: { title: string; children: ReactNode; defaultOpen?: boolean; right?: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`section ${open ? "open" : ""}`}>
      <div className="section-head" onClick={() => setOpen(!open)}>
        <span className="chev">{open ? "▾" : "▸"}</span>
        <span className="section-title">{title}</span>
        <span className="section-right" onClick={(e) => e.stopPropagation()}>{right}</span>
      </div>
      {open && <div className="section-body">{children}</div>}
    </div>
  );
}

export function Modal({ title, onClose, children, wide, footer }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean; footer?: ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <IconButton title="Cerrar" onClick={onClose}><X size={18} /></IconButton>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, tabs }: { value: T; onChange: (v: T) => void; tabs: { value: T; label: ReactNode; title?: string }[] }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={value === t.value} className={`tab ${value === t.value ? "active" : ""}`} onClick={() => onChange(t.value)} title={t.title}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Badge({ children, tone = "default", title }: { children: ReactNode; tone?: "default" | "ai" | "ok" | "warn" | "error" | "info"; title?: string }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

export function Progress({ value, tone = "default" }: { value: number; tone?: "default" | "ok" | "error" }) {
  return (
    <div className={`progress progress-${tone}`}>
      <div className="progress-bar" style={{ width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%` }} />
    </div>
  );
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      {icon && <div className="empty-icon">{icon}</div>}
      <div className="empty-title">{title}</div>
      {children && <div className="empty-body">{children}</div>}
    </div>
  );
}

export function ColorInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const hex = (value || "#000000").slice(0, 7);
  return (
    <span className="color-input">
      <input type="color" value={hex} onChange={(e) => onChange(e.target.value.toUpperCase() + (value?.length === 9 ? value.slice(7) : ""))} />
      <input type="text" value={value || ""} onChange={(e) => onChange(e.target.value)} />
    </span>
  );
}

export function useOutside(cb: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) cb();
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [cb]);
  return ref;
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} />;
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}

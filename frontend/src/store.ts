import { produce } from "immer";
import { create } from "zustand";
import { api, ApiError, saveProject, wsUrl } from "./api";
import type { CapabilityInfo, EngineInfo, Job, MediaItem, Presets, Project, Storyboard } from "./types";
import { findClip } from "./lib/timeline";

export type LeftTab = "media" | "studio" | "director" | "library" | "faces" | "engines";
export type CenterTab = "viewer" | "storyboard";

interface Toast {
  id: number;
  text: string;
  kind: "info" | "ok" | "error" | "warn";
}

interface State {
  view: "home" | "editor";
  project: Project | null;
  dirty: boolean;
  saving: boolean;
  lastSaved: number;
  selection: string[];
  selectedTrack: string | null;
  selectedMedia: string | null;
  playhead: number;
  playing: boolean;
  pps: number;
  tool: "select" | "razor";
  snapping: boolean;
  inPoint: number | null;
  outPoint: number | null;
  past: Project[];
  future: Project[];
  gestureBase: Project | null;
  jobs: Record<string, Job>;
  presets: Presets | null;
  engines: EngineInfo[];
  capabilities: Record<string, CapabilityInfo>;
  leftTab: LeftTab;
  centerTab: CenterTab;
  toasts: Toast[];
  pendingReplace: Record<string, { clipId: string }>;
  exportOpen: boolean;
  settingsOpen: boolean;
  jobsOpen: boolean;
  directorPreset: string | null;
  fonts: string[];
}

interface Actions {
  openProject(id: string): Promise<void>;
  reloadProject(): Promise<void>;
  closeProject(): void;
  loadPresets(): Promise<void>;
  loadEngines(refresh?: boolean): Promise<void>;
  edit(fn: (p: Project) => void, history?: boolean): void;
  beginGesture(): void;
  endGesture(): void;
  undo(): void;
  redo(): void;
  save(): Promise<void>;
  select(ids: string[], additive?: boolean): void;
  setPlayhead(t: number): void;
  setPlaying(v: boolean): void;
  setPps(v: number): void;
  toast(text: string, kind?: Toast["kind"]): void;
  dismissToast(id: number): void;
  upsertJob(j: Job): void;
  mergeMedia(items: MediaItem[]): void;
  setStoryboard(sb: Storyboard | null): void;
  set(partial: Partial<State>): void;
  watchReplace(jobId: string, clipId: string): void;
}

let saveTimer: number | undefined;
let toastId = 1;

export const useStore = create<State & Actions>((set, get) => ({
  view: "home",
  project: null,
  dirty: false,
  saving: false,
  lastSaved: 0,
  selection: [],
  selectedTrack: null,
  selectedMedia: null,
  playhead: 0,
  playing: false,
  pps: 60,
  tool: "select",
  snapping: true,
  inPoint: null,
  outPoint: null,
  past: [],
  future: [],
  gestureBase: null,
  jobs: {},
  presets: null,
  engines: [],
  capabilities: {},
  leftTab: "media",
  centerTab: "viewer",
  toasts: [],
  pendingReplace: {},
  exportOpen: false,
  settingsOpen: false,
  jobsOpen: false,
  directorPreset: null,
  fonts: [],

  async openProject(id) {
    const p = await api.get<Project>(`/api/projects/${id}`);
    set({ project: p, view: "editor", dirty: false, past: [], future: [], selection: [], playhead: 0, playing: false, inPoint: null, outPoint: null,
          centerTab: p.storyboard && p.tracks.every((t) => t.clips.length === 0) ? "storyboard" : "viewer" });
    try {
      localStorage.setItem("durostcm.lastProject", id);
    } catch {
      /* sin almacenamiento */
    }
    const jobs = await api.get<{ jobs: Job[] }>(`/api/jobs?project_id=${id}`);
    const map: Record<string, Job> = {};
    for (const j of jobs.jobs) map[j.id] = j;
    set({ jobs: { ...get().jobs, ...map } });
  },

  async reloadProject() {
    const cur = get().project;
    if (!cur) return;
    const p = await api.get<Project>(`/api/projects/${cur.id}`);
    set({ project: p, dirty: false });
  },

  closeProject() {
    set({ project: null, view: "home", selection: [], playing: false });
  },

  async loadPresets() {
    if (get().presets) return;
    const [presets, fonts] = await Promise.all([api.get<Presets>("/api/presets"), api.get<{ fonts: string[] }>("/api/fonts")]);
    set({ presets, fonts: fonts.fonts });
  },

  async loadEngines(refresh = false) {
    const r = await api.get<{ engines: EngineInfo[]; capabilities: Record<string, CapabilityInfo> }>(`/api/ai/engines${refresh ? "?refresh=true" : ""}`);
    set({ engines: r.engines, capabilities: r.capabilities });
  },

  edit(fn, history = true) {
    const p = get().project;
    if (!p) return;
    const next = produce(p, fn);
    if (next === p) return;
    if (history && !get().gestureBase) {
      set({ past: [...get().past.slice(-99), p], future: [] });
    }
    set({ project: next, dirty: true });
    scheduleSave();
  },

  beginGesture() {
    set({ gestureBase: get().project });
  },

  endGesture() {
    const base = get().gestureBase;
    const cur = get().project;
    set({ gestureBase: null });
    if (base && cur && base !== cur) set({ past: [...get().past.slice(-99), base], future: [] });
  },

  undo() {
    const { past, project } = get();
    if (!past.length || !project) return;
    const prev = past[past.length - 1];
    set({ project: { ...prev, rev: project.rev, media: project.media, storyboard: project.storyboard }, past: past.slice(0, -1), future: [project, ...get().future], dirty: true });
    scheduleSave();
  },

  redo() {
    const { future, project } = get();
    if (!future.length || !project) return;
    const nxt = future[0];
    set({ project: { ...nxt, rev: project.rev, media: project.media, storyboard: project.storyboard }, future: future.slice(1), past: [...get().past, project], dirty: true });
    scheduleSave();
  },

  async save() {
    const p = get().project;
    if (!p || !get().dirty || get().saving) return;
    set({ saving: true });
    try {
      const r = await saveProject(p);
      const cur = get().project;
      if (cur && cur.id === p.id) {
        set({ project: { ...cur, rev: r.rev }, dirty: cur !== p, lastSaved: Date.now() });
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        set({ project: e.data.project as Project, dirty: false });
        get().toast("El proyecto se actualizó desde un proceso de IA: recargado", "warn");
      } else {
        get().toast(`Error al guardar: ${(e as Error).message}`, "error");
      }
    } finally {
      set({ saving: false });
      if (get().dirty) scheduleSave();
    }
  },

  select(ids, additive = false) {
    if (additive) {
      const cur = new Set(get().selection);
      for (const i of ids) {
        if (cur.has(i)) cur.delete(i);
        else cur.add(i);
      }
      set({ selection: [...cur] });
    } else set({ selection: ids });
  },

  setPlayhead(t) {
    set({ playhead: Math.max(0, t) });
  },
  setPlaying(v) {
    set({ playing: v });
  },
  setPps(v) {
    set({ pps: Math.min(800, Math.max(4, v)) });
  },

  toast(text, kind = "info") {
    const id = toastId++;
    set({ toasts: [...get().toasts, { id, text, kind }] });
    window.setTimeout(() => get().dismissToast(id), kind === "error" ? 9000 : 4500);
  },
  dismissToast(id) {
    set({ toasts: get().toasts.filter((t) => t.id !== id) });
  },

  upsertJob(j) {
    const prev = get().jobs[j.id];
    set({ jobs: { ...get().jobs, [j.id]: j } });
    if (prev?.status !== j.status) {
      if (j.status === "done") {
        if (!j.kind.startsWith("proxy")) get().toast(`✔ ${j.title}`, "ok");
        const rep = get().pendingReplace[j.id];
        const media = j.result?.media?.[0] as MediaItem | undefined;
        if (rep && media) {
          get().mergeMedia([media]);
          get().edit((p) => {
            const f = findClip(p, rep.clipId);
            if (f) {
              f.clip.media_id = media.id;
              if (media.duration && media.kind !== "image") f.clip.duration = Math.min(f.clip.duration, media.duration / f.clip.speed);
            }
          });
          const pr = { ...get().pendingReplace };
          delete pr[j.id];
          set({ pendingReplace: pr });
        }
      } else if (j.status === "error") get().toast(`✘ ${j.title}: ${j.error}`, "error");
    }
  },

  mergeMedia(items) {
    const p = get().project;
    if (!p) return;
    const map = new Map(p.media.map((m) => [m.id, m]));
    for (const it of items) map.set(it.id, it);
    set({ project: { ...p, media: [...map.values()] } });
  },

  setStoryboard(sb) {
    const p = get().project;
    if (!p) return;
    set({ project: { ...p, storyboard: sb } });
  },

  set(partial) {
    set(partial);
  },

  watchReplace(jobId, clipId) {
    set({ pendingReplace: { ...get().pendingReplace, [jobId]: { clipId } } });
  },
}));

function scheduleSave() {
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    if (useStore.getState().gestureBase) {
      scheduleSave();
      return;
    }
    void useStore.getState().save();
  }, 700);
}

// ------------------------------------------------------------------ WebSocket en vivo
let ws: WebSocket | null = null;
let retry = 1000;

export function connectLive() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  ws = new WebSocket(wsUrl());
  ws.onopen = () => {
    retry = 1000;
  };
  ws.onmessage = (ev) => {
    let msg: any;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    const st = useStore.getState();
    const pid = st.project?.id;
    switch (msg.type) {
      case "job":
        st.upsertJob(msg.job as Job);
        break;
      case "media_added":
      case "media_updated":
        if (msg.project_id === pid) st.mergeMedia(msg.media as MediaItem[]);
        break;
      case "storyboard":
        if (msg.project_id === pid) st.setStoryboard(msg.storyboard as Storyboard);
        break;
      case "project_changed":
        if (msg.project_id === pid) {
          void (async () => {
            if (st.dirty) await st.save();
            await useStore.getState().reloadProject();
          })();
        }
        break;
    }
  };
  ws.onclose = () => {
    ws = null;
    window.setTimeout(connectLive, retry);
    retry = Math.min(15000, retry * 2);
  };
}

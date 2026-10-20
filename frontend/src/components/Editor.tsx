import { useEffect, useRef } from "react";
import { deepClone, findClip, newClip, projectDuration, rippleDelete, sortTrack, splitClip, uid } from "../lib/timeline";
import { useStore } from "../store";
import type { Clip } from "../types";
import ExportDialog from "./ExportDialog";
import Inspector from "./Inspector";
import LeftPanel from "./LeftPanel";
import StoryboardView from "./StoryboardView";
import Timeline from "./Timeline";
import Viewer from "./Viewer";

let clipboard: { trackId: string; clip: Clip }[] = [];

export function splitAtPlayhead() {
  const st = useStore.getState();
  const t = st.playhead;
  st.edit((p) => {
    const sel = new Set(st.selection);
    for (const track of p.tracks) {
      if (track.locked) continue;
      const add: Clip[] = [];
      for (const c of track.clips) {
        if ((sel.size === 0 || sel.has(c.id)) && t > c.start && t < c.start + c.duration) {
          const second = splitClip(c, t);
          if (second) add.push(second);
        }
      }
      track.clips.push(...add);
      sortTrack(track);
    }
  });
}

export function deleteSelection(ripple = false) {
  const st = useStore.getState();
  if (!st.selection.length) return;
  st.edit((p) => {
    for (const id of st.selection) {
      const f = findClip(p, id);
      if (!f || f.track.locked) continue;
      if (ripple) rippleDelete(f.track, id);
      else f.track.clips = f.track.clips.filter((c) => c.id !== id);
    }
  });
  st.select([]);
}

function useResizable() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("durostcm.layout") || "{}");
      for (const k of ["--left", "--right", "--tl"]) if (saved[k]) document.documentElement.style.setProperty(k, saved[k]);
    } catch {
      /* sin almacenamiento */
    }
  }, []);
  const start = (varName: "--left" | "--right" | "--tl") => (e: React.PointerEvent) => {
    e.preventDefault();
    const root = document.documentElement;
    const startX = e.clientX;
    const startY = e.clientY;
    const startVal = parseFloat(getComputedStyle(root).getPropertyValue(varName)) || 300;
    const move = (ev: PointerEvent) => {
      let v = startVal;
      if (varName === "--left") v = startVal + (ev.clientX - startX);
      if (varName === "--right") v = startVal - (ev.clientX - startX);
      if (varName === "--tl") v = startVal - (ev.clientY - startY);
      const max = varName === "--tl" ? window.innerHeight * 0.7 : window.innerWidth * 0.45;
      root.style.setProperty(varName, `${Math.max(180, Math.min(max, v))}px`);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      try {
        const cs = getComputedStyle(root);
        localStorage.setItem("durostcm.layout", JSON.stringify({
          "--left": cs.getPropertyValue("--left").trim(), "--right": cs.getPropertyValue("--right").trim(), "--tl": cs.getPropertyValue("--tl").trim(),
        }));
      } catch {
        /* sin almacenamiento */
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  return { ref, start };
}

export default function Editor() {
  const centerTab = useStore((s) => s.centerTab);
  const exportOpen = useStore((s) => s.exportOpen);
  const { ref, start } = useResizable();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (e.target as HTMLElement)?.isContentEditable) return;
      const st = useStore.getState();
      const p = st.project;
      if (!p) return;
      const fps = p.settings.fps;
      const mod = e.ctrlKey || e.metaKey;
      const k = e.key.toLowerCase();
      if (mod && k === "z") { e.preventDefault(); e.shiftKey ? st.redo() : st.undo(); return; }
      if (mod && k === "y") { e.preventDefault(); st.redo(); return; }
      if (mod && k === "s") { e.preventDefault(); void st.save(); return; }
      if (mod && k === "e") { e.preventDefault(); st.set({ exportOpen: true }); return; }
      if (mod && k === "c") {
        clipboard = st.selection.map((id) => findClip(p, id)).filter(Boolean).map((f) => ({ trackId: f!.track.id, clip: deepClone(f!.clip) }));
        if (clipboard.length) st.toast(`${clipboard.length} clip(s) copiados`);
        return;
      }
      if (mod && k === "v") {
        if (!clipboard.length) return;
        const base = Math.min(...clipboard.map((c) => c.clip.start));
        const ids: string[] = [];
        st.edit((d) => {
          for (const item of clipboard) {
            const track = d.tracks.find((t) => t.id === item.trackId) || d.tracks[0];
            const c = { ...deepClone(item.clip), id: uid("c_"), start: st.playhead + (item.clip.start - base) };
            track.clips.push(c);
            sortTrack(track);
            ids.push(c.id);
          }
        });
        st.select(ids);
        return;
      }
      if (mod && k === "a") { e.preventDefault(); st.select(p.tracks.flatMap((t) => t.clips.map((c) => c.id))); return; }
      if (mod && k === "d") {
        e.preventDefault();
        const ids: string[] = [];
        st.edit((d) => {
          for (const id of st.selection) {
            const f = findClip(d, id);
            if (!f) continue;
            const c = { ...deepClone(f.clip), id: uid("c_"), start: f.clip.start + f.clip.duration };
            f.track.clips.push(c);
            sortTrack(f.track);
            ids.push(c.id);
          }
        });
        st.select(ids);
        return;
      }
      switch (k) {
        case " ":
        case "k":
          e.preventDefault();
          st.setPlaying(k === "k" ? false : !st.playing);
          break;
        case "l":
          st.setPlaying(true);
          break;
        case "j":
          st.setPlaying(false);
          st.setPlayhead(Math.max(0, st.playhead - 1));
          break;
        case "arrowleft":
          e.preventDefault();
          st.setPlayhead(Math.max(0, st.playhead - (e.shiftKey ? 1 : 1 / fps)));
          break;
        case "arrowright":
          e.preventDefault();
          st.setPlayhead(st.playhead + (e.shiftKey ? 1 : 1 / fps));
          break;
        case "home":
          st.setPlayhead(0);
          break;
        case "end":
          st.setPlayhead(projectDuration(p));
          break;
        case "s":
          splitAtPlayhead();
          break;
        case "c":
          st.set({ tool: st.tool === "razor" ? "select" : "razor" });
          break;
        case "v":
          st.set({ tool: "select" });
          break;
        case "n":
          st.set({ snapping: !st.snapping });
          break;
        case "delete":
        case "backspace":
          e.preventDefault();
          deleteSelection(e.shiftKey);
          break;
        case "i":
          st.set({ inPoint: st.playhead });
          break;
        case "o":
          st.set({ outPoint: st.playhead });
          break;
        case "x":
          st.set({ inPoint: null, outPoint: null });
          break;
        case "m":
          st.edit((d) => { d.markers.push({ id: uid("k_"), t: st.playhead, label: `Marca ${d.markers.length + 1}`, color: "#FFB020" }); });
          break;
        case "t":
          st.edit((d) => {
            const track = d.tracks.find((tr) => tr.kind === "text") || d.tracks[0];
            track.clips.push(newClip({ kind: "text", start: st.playhead, duration: 4, name: "Texto", text: { content: "Tu texto aquí", font: "Inter", size: 0.08, weight: "bold", color: "#FFFFFF", stroke_color: "#000000", stroke_width: 0, shadow: true, background: null, align: "center", line_spacing: 1.15, letter_spacing: 0, max_width: 0.9, animation: "fade", uppercase: false } }));
            sortTrack(track);
          });
          break;
        case "+":
        case "=":
          st.setPps(st.pps * 1.25);
          break;
        case "-":
          st.setPps(st.pps / 1.25);
          break;
        case "escape":
          st.select([]);
          st.set({ tool: "select" });
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="editor" ref={ref}>
      <aside className="panel panel-left"><LeftPanel /></aside>
      <div className="splitter-v" style={{ gridColumn: 2 }} onPointerDown={start("--left")} />
      <section className="center">{centerTab === "storyboard" ? <StoryboardView /> : <Viewer />}</section>
      <div className="splitter-v" style={{ gridColumn: 4 }} onPointerDown={start("--right")} />
      <aside className="panel panel-right"><Inspector /></aside>
      <div className="splitter-h" onPointerDown={start("--tl")} />
      <section className="timeline-wrap"><Timeline /></section>
      {exportOpen && <ExportDialog />}
    </div>
  );
}

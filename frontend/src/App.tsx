import { useEffect } from "react";
import Editor from "./components/Editor";
import Home from "./components/Home";
import { JobsPopover, Toasts } from "./components/Jobs";
import SettingsDialog from "./components/SettingsDialog";
import TopBar from "./components/TopBar";
import { connectLive, useStore } from "./store";

export default function App() {
  const view = useStore((s) => s.view);
  const settingsOpen = useStore((s) => s.settingsOpen);
  const jobsOpen = useStore((s) => s.jobsOpen);

  useEffect(() => {
    connectLive();
    void useStore.getState().loadPresets().catch(() => undefined);
    void useStore.getState().loadEngines().catch(() => undefined);
    const params = new URLSearchParams(location.search);
    const pid = params.get("project");
    if (pid) void useStore.getState().openProject(pid).catch(() => undefined);
    const beforeUnload = (e: BeforeUnloadEvent) => {
      if (useStore.getState().dirty) {
        void useStore.getState().save();
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, []);

  return (
    <div className="app">
      <TopBar />
      {view === "home" ? <Home /> : <Editor />}
      {jobsOpen && <JobsPopover />}
      {settingsOpen && <SettingsDialog />}
      <Toasts />
    </div>
  );
}

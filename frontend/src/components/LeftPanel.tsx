import { Clapperboard, Cpu, FolderOpen, ScanFace, Users, Wand2 } from "lucide-react";
import DirectorPanel from "../panels/DirectorPanel";
import EnginesPanel from "../panels/EnginesPanel";
import FacesPanel from "../panels/FacesPanel";
import LibraryPanel from "../panels/LibraryPanel";
import MediaPanel from "../panels/MediaPanel";
import StudioPanel from "../panels/StudioPanel";
import { LeftTab, useStore } from "../store";

const TABS: { id: LeftTab; label: string; icon: typeof FolderOpen; title: string }[] = [
  { id: "media", label: "Medios", icon: FolderOpen, title: "Biblioteca de medios del proyecto" },
  { id: "studio", label: "Estudio IA", icon: Wand2, title: "Genera imágenes, vídeos, voces y música" },
  { id: "director", label: "Director", icon: Clapperboard, title: "Producciones automáticas: personaje 4K, anuncio, cortometraje" },
  { id: "library", label: "Reparto", icon: Users, title: "Personajes y localizaciones con biblia de continuidad" },
  { id: "faces", label: "Rostros", icon: ScanFace, title: "Rostros de inspiración con licencia libre y consentimientos" },
  { id: "engines", label: "Motores", icon: Cpu, title: "Motores de IA, modelos y hardware" },
];

export default function LeftPanel() {
  const tab = useStore((s) => s.leftTab);
  const st = useStore.getState();
  return (
    <>
      <nav className="panel-tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`ptab ${tab === t.id ? "active" : ""}`} title={t.title} onClick={() => st.set({ leftTab: t.id })}>
            <t.icon size={17} />
            {t.label}
          </button>
        ))}
      </nav>
      <div className="panel-body">
        {tab === "media" && <MediaPanel />}
        {tab === "studio" && <StudioPanel />}
        {tab === "director" && <DirectorPanel />}
        {tab === "library" && <LibraryPanel />}
        {tab === "faces" && <FacesPanel />}
        {tab === "engines" && <EnginesPanel />}
      </div>
    </>
  );
}

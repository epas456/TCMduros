import { Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useStore } from "../store";
import { Button, Field, Modal, Tabs, Toggle } from "./ui";

export default function SettingsDialog() {
  const [s, setS] = useState<any>(null);
  const [tab, setTab] = useState<"engines" | "keys" | "ethics" | "luts" | "system">("engines");
  const [luts, setLuts] = useState<string[]>([]);
  const [token, setToken] = useState(() => { try { return localStorage.getItem("durostcm.token") || ""; } catch { return ""; } });
  const lutRef = useRef<HTMLInputElement>(null);
  const st = useStore.getState();
  const close = () => st.set({ settingsOpen: false });

  useEffect(() => {
    api.get("/api/settings").then(setS).catch((e) => st.toast(e.message, "error"));
    api.get("/api/luts").then((r) => setLuts(r.luts)).catch(() => undefined);
  }, []);
  if (!s) return null;
  const ep = s.endpoints;
  const setEp = (k: string, v: unknown) => setS({ ...s, endpoints: { ...ep, [k]: v } });
  const setKey = (k: string, v: string) => setS({ ...s, api_keys: { ...s.api_keys, [k]: v } });
  const setEth = (k: string, v: unknown) => setS({ ...s, ethics: { ...s.ethics, [k]: v } });
  const setDf = (k: string, v: unknown) => setS({ ...s, diffusers: { ...s.diffusers, [k]: v } });

  async function save() {
    try {
      await api.patch("/api/settings", s);
      try { if (token) localStorage.setItem("durostcm.token", token); else localStorage.removeItem("durostcm.token"); } catch { /* sin almacenamiento */ }
      st.toast("Ajustes guardados", "ok");
      void st.loadEngines(true);
      close();
    } catch (e) {
      st.toast((e as Error).message, "error");
    }
  }

  return (
    <Modal title="Ajustes" wide onClose={close} footer={<><Button kind="ghost" onClick={close}>Cancelar</Button><Button kind="primary" onClick={() => void save()}>Guardar</Button></>}>
      <Tabs value={tab} onChange={setTab} tabs={[
        { value: "engines", label: "Motores IA" }, { value: "keys", label: "Claves" }, { value: "ethics", label: "Ética y legal" }, { value: "luts", label: "LUTs" }, { value: "system", label: "Sistema" },
      ]} />
      <div style={{ height: 12 }} />
      {tab === "engines" && (
        <div className="grid2" style={{ gap: 14 }}>
          <div>
            <Field label="ComfyUI · URL" hint="Arranca ComfyUI y deja esta dirección. Puede ser otro PC de la red con GPU."><input type="text" value={ep.comfyui_url} onChange={(e) => setEp("comfyui_url", e.target.value)} /></Field>
            <Field label="ComfyUI · carpeta de instalación" hint="Para descargar modelos directamente en ComfyUI/models"><input type="text" value={ep.comfyui_path} onChange={(e) => setEp("comfyui_path", e.target.value)} placeholder="C:\\ComfyUI o ~/ComfyUI" /></Field>
            <Field label="Ollama · URL"><input type="text" value={ep.ollama_url} onChange={(e) => setEp("ollama_url", e.target.value)} /></Field>
            <div className="grid2">
              <Field label="Modelo guionista"><input type="text" value={ep.ollama_model} onChange={(e) => setEp("ollama_model", e.target.value)} /></Field>
              <Field label="Modelo de visión"><input type="text" value={ep.ollama_vision_model} onChange={(e) => setEp("ollama_vision_model", e.target.value)} /></Field>
            </div>
            <Field label="Servidor OpenAI compatible (LM Studio, llama.cpp…)"><input type="text" value={ep.openai_compat_url} onChange={(e) => setEp("openai_compat_url", e.target.value)} placeholder="http://127.0.0.1:1234/v1" /></Field>
            <Field label="Modelo"><input type="text" value={ep.openai_compat_model} onChange={(e) => setEp("openai_compat_model", e.target.value)} /></Field>
            <Field label="Automatic1111 / Forge · URL"><input type="text" value={ep.a1111_url} onChange={(e) => setEp("a1111_url", e.target.value)} /></Field>
          </div>
          <div>
            <Field label="Real-ESRGAN (ncnn-vulkan) · ruta del ejecutable"><input type="text" value={ep.realesrgan_bin} onChange={(e) => setEp("realesrgan_bin", e.target.value)} /></Field>
            <Field label="RIFE (ncnn-vulkan) · ruta del ejecutable"><input type="text" value={ep.rife_bin} onChange={(e) => setEp("rife_bin", e.target.value)} /></Field>
            <Field label="Piper · ejecutable"><input type="text" value={ep.piper_bin} onChange={(e) => setEp("piper_bin", e.target.value)} /></Field>
            <Field label="Piper · voz (.onnx)"><input type="text" value={ep.piper_voice} onChange={(e) => setEp("piper_voice", e.target.value)} /></Field>
            <div className="sep" />
            <Field label="Diffusers · modelo de imagen (Hugging Face)"><input type="text" value={s.diffusers.image_model} onChange={(e) => setDf("image_model", e.target.value)} /></Field>
            <Field label="Diffusers · modelo de vídeo"><input type="text" value={s.diffusers.video_model} onChange={(e) => setDf("video_model", e.target.value)} /></Field>
            <Field label="Diffusers · imagen→vídeo"><input type="text" value={s.diffusers.i2v_model} onChange={(e) => setDf("i2v_model", e.target.value)} /></Field>
            <Toggle checked={s.diffusers.cpu_offload} onChange={(v) => setDf("cpu_offload", v)} label="Descargar a CPU (menos VRAM, más lento)" />
          </div>
        </div>
      )}
      {tab === "keys" && (
        <>
          <p className="panel-sub">Opcionales. Se guardan sólo en tu equipo (config.yaml).</p>
          <Field label="Pexels API key" hint="Gratis en pexels.com/api"><input type="password" value={s.api_keys.pexels} onChange={(e) => setKey("pexels", e.target.value)} /></Field>
          <Field label="Unsplash Access Key" hint="Gratis en unsplash.com/developers"><input type="password" value={s.api_keys.unsplash} onChange={(e) => setKey("unsplash", e.target.value)} /></Field>
          <Field label="Hugging Face token" hint="Para modelos con acceso restringido (gated)"><input type="password" value={s.api_keys.huggingface} onChange={(e) => setKey("huggingface", e.target.value)} /></Field>
        </>
      )}
      {tab === "ethics" && (
        <div style={{ display: "grid", gap: 10 }}>
          <Toggle checked={s.ethics.ai_label_metadata} onChange={(v) => setEth("ai_label_metadata", v)} label="Añadir metadatos «generado con IA» en las exportaciones (recomendado, AI Act art. 50)" />
          <Toggle checked={s.ethics.ai_label_watermark} onChange={(v) => setEth("ai_label_watermark", v)} label="Marca visible «Generado con IA» por defecto" />
          <Toggle checked={s.ethics.provenance_sidecar} onChange={(v) => setEth("provenance_sidecar", v)} label="Manifiesto de procedencia (.provenance.json) junto a cada render" />
          <Toggle checked={s.ethics.require_consent_for_real_people} onChange={(v) => setEth("require_consent_for_real_people", v)} label="Avisar cuando un prompt apunta a una persona real" />
          <Field label="Licencias de rostros aceptadas" hint="cc0, pdm, by, by-sa (las NC/ND no permiten uso comercial o derivadas)">
            <input type="text" value={s.ethics.allowed_face_licenses.join(", ")} onChange={(e) => setEth("allowed_face_licenses", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} />
          </Field>
        </div>
      )}
      {tab === "luts" && (
        <>
          <p className="panel-sub">LUTs 3D (.cube) para etalonaje: conversiones Log→Rec.709 de tus cámaras o looks creativos.</p>
          <Button icon={<Upload size={14} />} onClick={() => lutRef.current?.click()}>Subir LUT</Button>
          <input ref={lutRef} type="file" accept=".cube,.3dl" hidden onChange={async (e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const fd = new FormData();
            fd.append("file", f);
            await api.form("/api/luts", fd);
            setLuts((await api.get("/api/luts")).luts);
          }} />
          <div style={{ marginTop: 10 }}>{luts.map((l) => <div key={l} className="list-row">{l}</div>)}</div>
        </>
      )}
      {tab === "system" && (
        <>
          <Field label="Puerto"><input type="number" value={s.port} onChange={(e) => setS({ ...s, port: +e.target.value })} /></Field>
          <Field label="Trabajos de GPU en paralelo"><input type="number" min={1} max={4} value={s.max_parallel_jobs} onChange={(e) => setS({ ...s, max_parallel_jobs: +e.target.value })} /></Field>
          <Field label="Token de acceso (servidor)" hint="Si lo defines, la interfaz y la API exigirán este token (útil al usarlo en red local)."><input type="password" value={s.auth_token} onChange={(e) => setS({ ...s, auth_token: e.target.value })} /></Field>
          <Field label="Token de este navegador"><input type="password" value={token} onChange={(e) => setToken(e.target.value)} /></Field>
          <Field label="FFmpeg"><input type="text" value={s.ffmpeg} onChange={(e) => setS({ ...s, ffmpeg: e.target.value })} /></Field>
        </>
      )}
    </Modal>
  );
}

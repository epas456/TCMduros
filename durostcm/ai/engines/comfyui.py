"""Motor ComfyUI: ejecuta flujos (integrados o del usuario) en un servidor ComfyUI local.

ComfyUI es el estándar para modelos locales (FLUX, Qwen-Image, Wan 2.2, LTX,
HunyuanVideo…). durosTCM comprueba qué nodos y modelos tiene instalados y elige el
mejor flujo disponible para cada capacidad.
"""

from __future__ import annotations

import asyncio
import io
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from ...config import get_config
from ...core.ffmpeg import run_ffmpeg
from .. import workflows as W
from ..base import Engine, EngineStatus, EngineUnavailable, GenContext, GenRequest, GenResult


class ComfyClient:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.client_id = uuid.uuid4().hex
        self._object_info: dict | None = None
        self._oi_time = 0.0

    def _http(self, timeout: float = 30) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.url, timeout=timeout, trust_env=False)

    async def ping(self) -> dict | None:
        try:
            async with self._http(3) as c:
                r = await c.get("/system_stats")
                r.raise_for_status()
                return r.json()
        except Exception:
            return None

    async def object_info(self, refresh: bool = False) -> dict:
        if self._object_info is None or refresh or time.time() - self._oi_time > 120:
            async with self._http(60) as c:
                r = await c.get("/object_info")
                r.raise_for_status()
                self._object_info = r.json()
                self._oi_time = time.time()
        return self._object_info

    def options(self, oi: dict, node: str, inp: str) -> list[str]:
        spec = oi.get(node, {}).get("input", {})
        for group in ("required", "optional"):
            v = spec.get(group, {}).get(inp)
            if v and isinstance(v, list) and v and isinstance(v[0], list):
                return [str(x) for x in v[0]]
            # formato nuevo: ["COMBO", {"options": [...]}]
            if v and isinstance(v, list) and len(v) > 1 and isinstance(v[1], dict) and "options" in v[1]:
                return [str(x) for x in v[1]["options"]]
        return []

    async def upload(self, path: Path) -> str:
        async with self._http(120) as c:
            with open(path, "rb") as f:
                files = {"image": (f"durostcm_{uuid.uuid4().hex[:8]}_{path.name}", f, "application/octet-stream")}
                r = await c.post("/upload/image", files=files, data={"overwrite": "true", "type": "input"})
            r.raise_for_status()
            data = r.json()
            sub = data.get("subfolder") or ""
            return f"{sub}/{data['name']}" if sub else data["name"]

    async def queue(self, workflow: dict) -> str:
        async with self._http(60) as c:
            r = await c.post("/prompt", json={"prompt": workflow, "client_id": self.client_id})
            if r.status_code >= 400:
                raise RuntimeError(f"ComfyUI rechazó el flujo: {r.text[:1500]}")
            return r.json()["prompt_id"]

    async def history(self, prompt_id: str) -> dict | None:
        async with self._http(30) as c:
            r = await c.get(f"/history/{prompt_id}")
            r.raise_for_status()
            return r.json().get(prompt_id)

    async def interrupt(self) -> None:
        try:
            async with self._http(5) as c:
                await c.post("/interrupt")
        except Exception:
            pass

    async def download(self, info: dict) -> bytes:
        async with self._http(600) as c:
            r = await c.get("/view", params={"filename": info["filename"], "subfolder": info.get("subfolder", ""), "type": info.get("type", "output")})
            r.raise_for_status()
            return r.content

    async def wait(self, prompt_id: str, ctx: GenContext, total_nodes: int) -> dict:
        """Espera el resultado escuchando el WebSocket de progreso (con sondeo de respaldo)."""
        done_nodes: set[str] = set()
        ws_task = asyncio.create_task(self._listen(prompt_id, ctx, done_nodes, total_nodes))
        try:
            while True:
                ctx.check()
                h = await self.history(prompt_id)
                if h and (h.get("status", {}).get("completed") or h.get("outputs")):
                    st = h.get("status", {})
                    if st.get("status_str") == "error":
                        msgs = [m for m in st.get("messages", []) if m and m[0] == "execution_error"]
                        detail = msgs[0][1].get("exception_message", "") if msgs else ""
                        raise RuntimeError(f"Error en ComfyUI: {detail[:800]}")
                    return h
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            await self.interrupt()
            raise
        finally:
            ws_task.cancel()

    async def _listen(self, prompt_id: str, ctx: GenContext, done_nodes: set[str], total: int) -> None:
        try:
            import websockets  # type: ignore
        except ImportError:
            return
        ws_url = self.url.replace("http", "ws", 1) + f"/ws?clientId={self.client_id}"
        try:
            async with websockets.connect(ws_url, max_size=None, open_timeout=5) as ws:
                async for msg in ws:
                    if isinstance(msg, bytes):
                        continue  # previsualizaciones binarias
                    data = json.loads(msg)
                    t, d = data.get("type"), data.get("data", {})
                    if d.get("prompt_id") not in (None, prompt_id):
                        continue
                    if t == "progress" and d.get("max"):
                        frac = (len(done_nodes) + d["value"] / d["max"]) / max(1, total)
                        await ctx.progress(min(0.97, 0.05 + 0.9 * frac), f"ComfyUI: paso {d['value']}/{d['max']}")
                    elif t == "executing" and d.get("node"):
                        done_nodes.add(str(d["node"]))
        except Exception:
            return


class ComfyUIEngine(Engine):
    id = "comfyui"
    name = "ComfyUI (local)"
    description = "Ejecuta FLUX, Qwen-Image, Wan 2.2, LTX-Video, Real-ESRGAN y tus propios flujos en tu GPU."
    capabilities = {"text2image", "image2image", "text2video", "image2video", "upscale_image", "lipsync", "music", "tts"}
    quality = "pro"

    def __init__(self) -> None:
        self._client: ComfyClient | None = None

    @property
    def client(self) -> ComfyClient:
        url = get_config().settings.endpoints.comfyui_url
        if self._client is None or self._client.url != url.rstrip("/"):
            self._client = ComfyClient(url)
        return self._client

    async def status(self) -> EngineStatus:
        stats = await self.client.ping()
        if not stats:
            return EngineStatus(available=False, detail=f"No responde en {self.client.url} (arranca ComfyUI)", quality="pro")
        try:
            oi = await self.client.object_info()
        except Exception as e:  # noqa: BLE001
            return EngineStatus(available=False, detail=f"Error leyendo nodos: {e}", quality="pro")
        usable = [w["meta"]["label"] for w in W.all_workflows().values() if not self._missing(w, oi)]
        dev = (stats.get("devices") or [{}])[0]
        vram = dev.get("vram_total")
        detail = f"{dev.get('name', 'GPU')} · {round(vram / 2**30, 1)} GB" if vram else "Conectado"
        return EngineStatus(available=bool(usable), detail=detail if usable else f"{detail} · sin modelos compatibles instalados", models=usable, quality="pro")

    def _missing(self, wf: dict, oi: dict) -> list[str]:
        missing = []
        nodes = {n["class_type"] for n in wf["workflow"].values() if isinstance(n, dict) and "class_type" in n}
        for n in nodes:
            if n not in oi:
                missing.append(f"nodo {n}")
        if missing:
            return missing
        meta = wf["meta"]
        for key, fname in (meta.get("models") or {}).items():
            node_id, inp = key.split(".", 1)
            node = wf["workflow"].get(node_id, {})
            opts = self.client.options(oi, node.get("class_type", ""), inp)
            if meta.get("any_model") and key == meta.get("main_model"):
                if not opts:
                    missing.append(f"algún modelo para {node.get('class_type')}")
                continue
            if fname not in opts:
                missing.append(fname)
        return missing

    async def workflows_for(self, capability: str) -> list[dict]:
        oi = await self.client.object_info()
        out = []
        for wid, wf in W.all_workflows().items():
            if wf["meta"].get("capability") != capability:
                continue
            missing = self._missing(wf, oi)
            out.append({**wf["meta"], "id": wid, "available": not missing, "missing": missing})
        out.sort(key=lambda m: (not m["available"], -m.get("tier", 0)))
        return out

    async def has_capability(self, capability: str) -> bool:
        try:
            return any(w["available"] for w in await self.workflows_for(capability))
        except Exception:
            return False

    async def run(self, capability: str, req: GenRequest, ctx: GenContext) -> GenResult:
        if not await self.client.ping():
            raise EngineUnavailable("ComfyUI no está en marcha")
        oi = await self.client.object_info()
        candidates = await self.workflows_for(capability)
        chosen = None
        if req.workflow:
            chosen = next((c for c in candidates if c["id"] == req.workflow), None)
        if chosen is None:
            want_ref = bool(req.references) and capability == "image2image"
            for c in candidates:
                if c["available"] and (not want_ref or c.get("reference")):
                    chosen = c
                    break
            if chosen is None:
                chosen = next((c for c in candidates if c["available"]), None)
        if chosen is None or not chosen["available"]:
            raise EngineUnavailable(f"ComfyUI no tiene un flujo listo para {capability}: " + "; ".join(
                f"{c['label']}: falta {', '.join(c['missing'][:3])}" for c in candidates[:3]))
        wf_def = W.all_workflows()[chosen["id"]]
        meta = wf_def["meta"]
        seed = req.resolved_seed()
        values: dict[str, Any] = {
            "prompt": req.prompt,
            "negative": req.negative or (W.NEG_WAN if "wan" in chosen["id"] else W.NEG_PHOTO),
            "seed": seed,
            "width": _snap(req.width, 16),
            "height": _snap(req.height, 16),
            "steps": req.steps,
            "cfg": req.guidance if "cfg" in json.dumps(wf_def["workflow"]) and req.guidance else None,
            "guidance": req.guidance,
            "strength": req.strength,
            "filename_prefix": f"durostcm/{capability}",
            "model": req.model,
        }
        if capability in ("text2video", "image2video"):
            fps = req.fps or meta.get("native_fps", 24)
            native_fps = meta.get("native_fps", fps)
            values["fps"] = native_fps
            values["frames"] = W.frames_for(req.duration, native_fps, meta.get("frames_rule"))
            nat = meta.get("native")
            if nat:
                # respetar la orientación pedida dentro del área nativa del modelo
                area = nat[0] * nat[1]
                ratio = req.width / max(1, req.height)
                h = int((area / ratio) ** 0.5)
                values["width"], values["height"] = _snap(int(h * ratio), 32), _snap(h, 32)
        for key in ("image", "end_image", "video", "audio"):
            src = getattr(req, key)
            if key == "image" and not src and req.references:
                src = req.references[0]
            if src:
                await ctx.progress(0.02, f"Subiendo {key}")
                values[key] = await self.client.upload(Path(src))
        workflow = W.fill(wf_def["workflow"], values)
        # Compatibilidad: si el ComfyUI no tiene CreateVideo/SaveVideo, guardar fotogramas
        if any(n.get("class_type") == "SaveVideo" for n in workflow.values()) and "SaveVideo" not in oi:
            for nid in [k for k, n in workflow.items() if n.get("class_type") in ("CreateVideo", "SaveVideo")]:
                frames_src = workflow[nid]["inputs"].get("images") if workflow[nid]["class_type"] == "CreateVideo" else None
                del workflow[nid]
                if frames_src:
                    workflow["95"] = {"class_type": "SaveImage", "inputs": {"images": frames_src, "filename_prefix": values["filename_prefix"]}}
        ctx.log(f"ComfyUI · flujo {chosen['id']} · semilla {seed}")
        await ctx.progress(0.04, f"En cola: {chosen['label']}")
        pid = await self.client.queue(workflow)
        hist = await self.client.wait(pid, ctx, total_nodes=len(workflow))
        files = await self._collect(hist, capability, values.get("fps") or req.fps, ctx)
        if not files:
            raise RuntimeError("ComfyUI terminó sin generar archivos")
        return GenResult(files=[str(f) for f in files], engine=self.id, model=chosen["id"], seed=seed, meta={"workflow": chosen["id"], "label": chosen["label"]})

    async def _collect(self, hist: dict, capability: str, fps: float, ctx: GenContext) -> list[Path]:
        videos: list[Path] = []
        images: list[tuple[str, bytes]] = []
        audios: list[Path] = []
        for _nid, out in (hist.get("outputs") or {}).items():
            for key in ("videos", "gifs", "images", "audio"):
                for info in out.get(key, []) or []:
                    if not isinstance(info, dict) or "filename" not in info:
                        continue
                    if info.get("type") == "temp":
                        continue
                    data = await self.client.download(info)
                    name = info["filename"]
                    ext = Path(name).suffix.lower()
                    if ext in (".mp4", ".webm", ".mov", ".mkv", ".gif") or key in ("videos", "gifs"):
                        p = ctx.path("comfy_video", ext.lstrip(".") or "mp4")
                        p.write_bytes(data)
                        videos.append(p)
                    elif ext in (".wav", ".flac", ".mp3", ".ogg", ".opus") or key == "audio":
                        p = ctx.path("comfy_audio", ext.lstrip(".") or "wav")
                        p.write_bytes(data)
                        audios.append(p)
                    elif ext == ".webp" and capability in ("text2video", "image2video", "lipsync"):
                        videos.append(await _webp_to_mp4(data, ctx, fps))
                    else:
                        images.append((name, data))
        if capability in ("text2video", "image2video", "lipsync"):
            if videos:
                return [await _ensure_mp4(v, ctx) for v in videos]
            if images:
                return [await _frames_to_mp4(images, ctx, fps)]
            return []
        if capability in ("music", "tts"):
            return audios
        out: list[Path] = []
        for name, data in images:
            p = ctx.path("comfy", Path(name).suffix.lstrip(".") or "png")
            p.write_bytes(data)
            out.append(p)
        return out


def _snap(v: int, m: int) -> int:
    return max(m, int(round(v / m)) * m)


async def _frames_to_mp4(images: list[tuple[str, bytes]], ctx: GenContext, fps: float) -> Path:
    folder = ctx.out_dir / f"_frames_{int(time.time() * 1000)}"
    folder.mkdir(parents=True, exist_ok=True)
    for i, (_n, data) in enumerate(sorted(images, key=lambda x: x[0])):
        (folder / f"f_{i:05d}.png").write_bytes(data)
    out = ctx.path("comfy_video", "mp4")
    await run_ffmpeg(["-framerate", str(fps), "-i", str(folder / "f_%05d.png"), "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", str(out)], label="ensamblar")
    import shutil

    shutil.rmtree(folder, ignore_errors=True)
    return out


async def _webp_to_mp4(data: bytes, ctx: GenContext, fps: float) -> Path:
    from PIL import Image

    im = Image.open(io.BytesIO(data))
    frames = []
    i = 0
    while True:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "PNG")
        frames.append((f"{i:05d}.png", buf.getvalue()))
        i += 1
        try:
            im.seek(i)
        except EOFError:
            break
    return await _frames_to_mp4(frames, ctx, fps)


async def _ensure_mp4(p: Path, ctx: GenContext) -> Path:
    if p.suffix.lower() == ".mp4":
        return p
    out = p.with_suffix(".mp4")
    await run_ffmpeg(["-i", str(p), "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", str(out)], label="convertir")
    return out

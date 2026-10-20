"""Servidores simulados de ComfyUI y Ollama para probar las integraciones sin GPU."""

from __future__ import annotations

import io
import json
import socket
import subprocess
import threading
import time
import uuid

import uvicorn
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from durostcm.ai import workflows as W
from durostcm.ai.engines.procedural_art import generate


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ServerThread(threading.Thread):
    def __init__(self, app, port: int):
        super().__init__(daemon=True)
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))

    def run(self):
        self.server.run()

    def start_and_wait(self):
        self.start()
        for _ in range(100):
            if self.server.started:
                return self
            time.sleep(0.05)
        raise RuntimeError("mock server no arrancó")

    def stop(self):
        self.server.should_exit = True
        self.join(timeout=5)


def comfy_app() -> FastAPI:
    app = FastAPI()
    state = {"history": {}, "files": {}, "prompts": []}

    def object_info() -> dict:
        info: dict = {}
        for wf in W.BUILTIN.values():
            for nid, node in wf["workflow"].items():
                ct = node["class_type"]
                spec = info.setdefault(ct, {"input": {"required": {}}})
                for k, v in node["inputs"].items():
                    model_key = f"{nid}.{k}"
                    models = wf["meta"].get("models", {})
                    if model_key in models:
                        opts = spec["input"]["required"].setdefault(k, [[]])[0]
                        if models[model_key] not in opts:
                            opts.append(models[model_key])
                    else:
                        spec["input"]["required"].setdefault(k, ["*"])
        return info

    @app.get("/system_stats")
    async def stats():
        return {"devices": [{"name": "Mock RTX 4090", "vram_total": 24 * 2**30}]}

    @app.get("/object_info")
    async def oi():
        return object_info()

    @app.post("/upload/image")
    async def upload(image: UploadFile = File(...)):
        data = await image.read()
        state["files"][image.filename] = data
        return {"name": image.filename, "subfolder": "", "type": "input"}

    @app.post("/prompt")
    async def prompt(request: Request):
        body = await request.json()
        wf = body["prompt"]
        state["prompts"].append(wf)
        pid = uuid.uuid4().hex
        outputs = {}
        width = height = 512
        frames = 1
        text = ""
        for node in wf.values():
            ins = node["inputs"]
            if "width" in ins and isinstance(ins["width"], int):
                width, height = ins["width"], ins["height"]
            if "length" in ins and isinstance(ins["length"], int):
                frames = ins["length"]
            if node["class_type"] == "CLIPTextEncode" and not text:
                text = ins.get("text", "")
            if node["class_type"] == "LoadImage":
                assert ins["image"] in state["files"], "imagen no subida"
        for nid, node in wf.items():
            if node["class_type"] == "SaveImage":
                img = generate(text or "mock", width, height, 1)
                buf = io.BytesIO()
                img.save(buf, "PNG")
                name = f"mock_{pid}.png"
                state["files"][name] = buf.getvalue()
                outputs[nid] = {"images": [{"filename": name, "subfolder": "", "type": "output"}]}
            if node["class_type"] == "SaveVideo":
                name = f"mock_{pid}.mp4"
                fps = 24
                dur = max(1, frames) / fps
                out = subprocess.run(
                    ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s={width}x{height}:r={fps}:d={dur:.3f}", "-pix_fmt", "yuv420p",
                     "-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "-"], capture_output=True, check=True,
                ).stdout
                state["files"][name] = out
                outputs[nid] = {"images": [{"filename": name, "subfolder": "", "type": "output"}], "animated": [True]}
        state["history"][pid] = {"status": {"status_str": "success", "completed": True, "messages": []}, "outputs": outputs}
        return {"prompt_id": pid, "number": 1}

    @app.get("/history/{pid}")
    async def history(pid: str):
        h = state["history"].get(pid)
        return {pid: h} if h else {}

    @app.get("/view")
    async def view(filename: str, subfolder: str = "", type: str = "output"):
        return Response(state["files"][filename], media_type="application/octet-stream")

    @app.post("/interrupt")
    async def interrupt():
        return {}

    app.state.mock = state
    return app


STORYBOARD_JSON = {
    "title": "La última función",
    "logline": "Un proyeccionista descubre que su cine guarda un secreto.",
    "style": "cinematic drama",
    "look": "warm_film",
    "music_prompt": "melancholic piano and strings",
    "shots": [
        {"scene": "Inicio", "description": "El cine vacío", "prompt": "empty vintage movie theater, dust in the projector beam", "duration": 4,
         "camera": {"shot_size": "wide", "angle": "eye_level", "movement": "dolly_in", "lens": "35mm"}, "lighting": "volumetric", "mood": "nostalgic",
         "characters": ["Mateo Vidal"], "dialogue": [{"speaker": "Mateo Vidal", "text": "Otra noche sin público."}], "on_screen_text": "La última función", "transition": "cut"},
        {"scene": "Giro", "description": "La pantalla se ilumina sola", "prompt": "the movie screen lights up by itself, astonished face", "duration": 5,
         "camera": {"shot_size": "close_up", "angle": "low", "movement": "push_in", "lens": "85mm"}, "lighting": "rim", "mood": "mysterious",
         "characters": ["Mateo Vidal"], "dialogue": [], "on_screen_text": "", "transition": "fade"},
    ],
}


def ollama_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/tags")
    async def tags():
        return {"models": [{"name": "qwen3:8b"}, {"name": "qwen2.5vl:7b"}]}

    @app.post("/api/chat")
    async def chat(request: Request):
        body = await request.json()
        user = body["messages"][-1]["content"]
        if body["messages"][-1].get("images"):
            content = "oval face, thick dark brows, almond hazel eyes, olive skin with freckles, wavy dark hair, about 35"
        elif "storyboard" in user.lower():
            content = "```json\n" + json.dumps(STORYBOARD_JSON) + "\n```"
        elif "personaje" in user.lower():
            content = json.dumps({"name": "Mateo Vidal", "role": "proyeccionista", "age": 61, "gender": "hombre", "heritage": "Andalusian Spanish",
                                  "identity_prompt": "a 61-year-old Andalusian man, weathered olive skin, kind deep-set brown eyes, grey mustache",
                                  "personality": "nostálgico", "backstory": "Lleva 40 años en el mismo cine."})
        else:
            content = json.dumps({"prompt": "cinematic photo of the idea, golden hour, 35mm", "negative": "cartoon", "title": "Idea"})
        return JSONResponse({"message": {"role": "assistant", "content": content}, "done": True})

    return app

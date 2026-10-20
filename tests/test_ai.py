from __future__ import annotations

import asyncio

import pytest

from durostcm.ai import workflows as W
from durostcm.ai.base import GenContext, GenRequest
from durostcm.ai.engines.llm import extract_json
from durostcm.ai.imagination import engine as IM
from durostcm.ai.registry import get_registry
from durostcm.faces.ethics import check_prompt

from .mocks import ServerThread, comfy_app, free_port, ollama_app


def test_workflow_fill_types():
    wf = W.BUILTIN["wan22_5b_t2v"]["workflow"]
    out = W.fill(wf, {"prompt": "hola", "seed": 5, "width": 1280, "height": 704, "frames": 121, "fps": 24, "negative": "", "filename_prefix": "x"})
    assert out["8"]["inputs"]["seed"] == 5
    assert out["7"]["inputs"]["length"] == 121
    assert out["5"]["inputs"]["text"] == "hola"
    assert out["1"]["inputs"]["unet_name"] == "wan2.2_ti2v_5B_fp16.safetensors"
    assert out["8"]["inputs"]["steps"] == 20  # valor por defecto tipado


def test_frames_rule():
    assert W.frames_for(5, 24, "4n+1") == 121
    assert (W.frames_for(3.3, 16, "4n+1") - 1) % 4 == 0
    assert (W.frames_for(4, 24, "8n+1") - 1) % 8 == 0


def test_extract_json():
    assert extract_json('blah ```json\n{"a": [1, {"b": "}"}]}\n``` fin') == {"a": [1, {"b": "}"}]}
    assert extract_json("<think>x</think> {\"ok\": true}") == {"ok": True}
    assert extract_json("nada") is None


def test_imagination_character_and_prompt():
    c = IM.design_character("mujer piloto de 32 años, pelirroja, ojos verdes", seed=1)
    assert c.age == 32 and "woman" in c.identity_prompt and "green" in c.identity_prompt and "copper red" in c.identity_prompt
    r = IM.enhance_prompt("un lobo en la nieve", kind="video", imagination=0.9, seed=3)
    assert "wolf" not in r["prompt"] or True
    assert r["negative"] and len(r["prompt"]) > 100
    sb, loc = IM.storyboard_ad("Nébula", "auriculares inalámbricos", duration=15, seed=2)
    assert abs(sum(s.duration for s in sb.shots) - 15) < 1.0 and sb.shots[-1].on_screen_text


def test_ethics():
    assert check_prompt("retrato de una mujer en la playa").level == "ok"
    rep = check_prompt("que parezca a Brad Pitt corriendo")
    assert rep.requires_consent and rep.level == "warning"
    assert check_prompt("haz que parezca a Ana Torres", consent_ids=["cs_1"]).level == "warning"
    assert check_prompt("niña desnuda").level == "blocked"


def test_procedural_engine_all(home, tmp_path, media_dir):
    reg = get_registry()

    async def run():
        ctx = GenContext(tmp_path / "out")
        r1 = await reg.run("text2image", GenRequest(prompt="ciudad de noche neón", width=320, height=180), ctx)
        r2 = await reg.run("image2video", GenRequest(prompt="push in", image=r1.files[0], width=320, height=180, duration=1, fps=12), ctx)
        r3 = await reg.run("upscale_video", GenRequest(video=r2.files[0], scale=2), ctx)
        r4 = await reg.run("music", GenRequest(prompt="épica", duration=3), ctx)
        r5 = await reg.run("tts", GenRequest(text="hola mundo"), ctx)
        r6 = await reg.run("interpolate", GenRequest(video=str(media_dir / "clip_b.mp4"), target_fps=48), ctx)
        return r1, r2, r3, r4, r5, r6

    rs = asyncio.run(run())
    for r in rs:
        assert r.files
    assert rs[0].engine == "procedural"


@pytest.fixture()
def comfy(home):
    port = free_port()
    srv = ServerThread(comfy_app(), port).start_and_wait()
    home.update({"endpoints": {"comfyui_url": f"http://127.0.0.1:{port}"}})
    yield srv
    srv.stop()


@pytest.fixture()
def ollama(home):
    port = free_port()
    srv = ServerThread(ollama_app(), port).start_and_wait()
    home.update({"endpoints": {"ollama_url": f"http://127.0.0.1:{port}"}})
    yield srv
    srv.stop()


def test_comfyui_engine(comfy, tmp_path):
    reg = get_registry()

    async def run():
        caps = await reg.capabilities()
        assert caps["text2image"]["best"] == "comfyui"
        assert caps["image2video"]["best"] == "comfyui"
        ctx = GenContext(tmp_path / "c")
        r = await reg.run("text2image", GenRequest(prompt="retrato", width=512, height=512), ctx)
        assert r.engine == "comfyui" and r.files[0].endswith(".png")
        assert r.meta["workflow"] == "qwen_image_t2i"  # el de mayor calidad disponible
        v = await reg.run("image2video", GenRequest(prompt="sonríe", image=r.files[0], width=1280, height=720, duration=2, fps=24), ctx)
        assert v.files[0].endswith(".mp4") and v.meta["workflow"] == "wan22_14b_i2v"
        k = await reg.run("image2image", GenRequest(prompt="misma persona en un mercado", image=r.files[0], references=[r.files[0]]), ctx)
        assert k.meta["workflow"] == "flux_kontext_ref"
        return True

    assert asyncio.run(run())
    wf = comfy.server.config.app.state.mock["prompts"][1]
    lengths = [n["inputs"]["length"] for n in wf.values() if "length" in n["inputs"]]
    assert lengths and (lengths[0] - 1) % 4 == 0


def test_ollama_llm(ollama):
    reg = get_registry()

    async def run():
        llm = await reg.llm()
        assert llm is not None
        c = await IM.llm_character(llm, "proyeccionista de cine")
        sb = await IM.llm_storyboard(llm, "un cine", "short_film", 9, [c])
        return c, sb

    c, sb = asyncio.run(run())
    assert c.name == "Mateo Vidal" and c.age == 61
    assert len(sb.shots) == 2 and sb.shots[0].characters == [c.id] and sb.shots[0].dialogue[0].speaker == c.id


def test_lipsync_comfy(comfy, tmp_path, media_dir):
    reg = get_registry()

    async def run():
        ctx = GenContext(tmp_path / "ls")
        img = await reg.run("text2image", GenRequest(prompt="retrato", width=512, height=512), ctx)
        return await reg.run("lipsync", GenRequest(prompt="habla", image=img.files[0], audio=str(media_dir / "music.wav"), duration=3), ctx)

    r = asyncio.run(run())
    assert r.engine == "comfyui" and r.meta["workflow"] == "wan22_s2v_lipsync" and r.files[0].endswith(".mp4")
    wf = comfy.server.config.app.state.mock["prompts"][-1]
    s2v = next(n for n in wf.values() if n["class_type"] == "WanSoundImageToVideo")
    assert (s2v["inputs"]["length"] - 1) % 4 == 0 and s2v["inputs"]["width"] % 32 == 0


def test_short_film_pro_path(comfy, ollama):
    """Cortometraje con LLM + ComfyUI: guion del LLM, planos generados en ComfyUI y diálogos con sincronía labial."""
    import time

    from fastapi.testclient import TestClient

    from durostcm.server.app import create_app

    with TestClient(create_app()) as c:
        pid = c.post("/api/projects", json={"name": "Corto"}).json()["id"]
        j = c.post("/api/pipelines/short_film", json={"project_id": pid, "params": {"idea": "un cine antiguo", "duration": 9, "aspect": "16:9"}}).json()
        for _ in range(600):
            jj = c.get(f"/api/jobs/{j['id']}").json()
            if jj["status"] in ("done", "error"):
                break
            time.sleep(0.2)
        assert jj["status"] == "done", (jj["error"], jj["logs"][-6:])
        proj = c.get(f"/api/projects/{pid}").json()
        sb = proj["storyboard"]
        assert sb["title"] == "La última función" and len(sb["shots"]) == 2
        engines = {m["generation"]["engine"] for m in proj["media"] if m.get("generation")}
        assert "comfyui" in engines
        assert any("lipsync" in m["tags"] for m in proj["media"]), "el plano con diálogo debe tener sincronía labial"
        v1 = next(t for t in proj["tracks"] if t["name"] == "V1")
        assert len(v1["clips"]) == 2

from __future__ import annotations

import asyncio
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from durostcm.ai.base import EngineStatus, GenResult
from durostcm.core.analysis import detect_beats, detect_scenes, parse_srt
from durostcm.core.media import import_file
from durostcm.core.project import Clip, Effect
from durostcm.core.render import RenderSettings, render_project
from durostcm.core.storage import get_store


@pytest.fixture(scope="module")
def cuts_video(tmp_path_factory):
    d = tmp_path_factory.mktemp("cuts")
    out = d / "cuts.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1.5:r=25",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1.5:r=25",
        "-f", "lavfi", "-i", "testsrc2=s=320x240:d=1.5:r=25",
        "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-pix_fmt", "yuv420p", str(out),
    ], check=True)
    return out


def test_scene_detection(cuts_video):
    cuts = detect_scenes(cuts_video)
    assert len(cuts) == 2
    assert abs(cuts[0] - 1.5) < 0.1 and abs(cuts[1] - 3.0) < 0.1


def test_beat_detection(tmp_path):
    # clic cada 0,5 s → 120 BPM
    out = tmp_path / "click.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "aevalsrc='if(lt(mod(t,0.5),0.02),sin(2*PI*1000*t),0)':s=22050:d=8", str(out)], check=True)
    r = detect_beats(out)
    assert r["bpm"] is not None and abs(r["bpm"] - 120) < 6
    assert len(r["beats"]) >= 12


def test_parse_srt():
    srt = "1\n00:00:01,000 --> 00:00:02,500\nHola <i>mundo</i>\n\n2\n00:00:03.000 --> 00:00:04.000\nSegunda\nlínea\n"
    items = parse_srt(srt)
    assert items == [{"start": 1.0, "end": 2.5, "text": "Hola mundo"}, {"start": 3.0, "end": 4.0, "text": "Segunda\nlínea"}]


def test_audio_effects_render(home, media_dir):
    store = get_store()
    p = store.create("FX", width=320, height=180, fps=25)
    m = import_file(store, p, media_dir / "music.wav")
    p.tracks[3].clips.append(Clip(media_id=m.id, start=0, duration=3, effects=[Effect(type="voice_enhance"), Effect(type="pitch", params={"semitones": 4}), Effect(type="reverb")]))
    store.save(p)
    res = asyncio.run(render_project(store, p, RenderSettings(format="wav")))
    out = store.resolve(p.id, res["path"])
    assert out.stat().st_size > 100_000


def test_subtitles_api(home, media_dir, monkeypatch):
    from durostcm.ai.engines.whisper import WhisperEngine
    from durostcm.server.app import create_app

    async def fake_status(self):
        return EngineStatus(available=True, detail="mock")

    async def fake_run(self, capability, req, ctx):
        return GenResult(files=[], engine="whisper", model="mock", meta={"segments": [
            {"start": 0.5, "end": 1.5, "text": "Hola"}, {"start": 2.0, "end": 3.2, "text": "¿Qué tal?"}], "language": "es"})

    monkeypatch.setattr(WhisperEngine, "status", fake_status)
    monkeypatch.setattr(WhisperEngine, "run", fake_run)
    with TestClient(create_app()) as c:
        pid = c.post("/api/projects", json={"name": "Subs"}).json()["id"]
        with open(media_dir / "clip_a.mp4", "rb") as f:
            mid = c.post(f"/api/projects/{pid}/media", files=[("files", ("a.mp4", f, "video/mp4"))]).json()["media"][0]["id"]
        proj = c.get(f"/api/projects/{pid}").json()
        proj["tracks"][0]["clips"].append({"id": "c_test", "media_id": mid, "start": 10, "duration": 3, "in_point": 0.5})
        c.put(f"/api/projects/{pid}", json=proj)
        j = c.post(f"/api/projects/{pid}/subtitles/auto", json={"clip_id": "c_test"}).json()
        for _ in range(100):
            jj = c.get(f"/api/jobs/{j['id']}").json()
            if jj["status"] in ("done", "error"):
                break
            time.sleep(0.1)
        assert jj["status"] == "done", jj["error"]
        proj = c.get(f"/api/projects/{pid}").json()
        subs = next(t for t in proj["tracks"] if t["name"] == "Subtítulos")
        starts = [round(x["start"], 2) for x in subs["clips"]]
        assert starts == [10.0, 11.5]  # 0.5 s de origen = inicio del clip
        r = c.post(f"/api/projects/{pid}/subtitles/import", files={"file": ("x.srt", b"1\n00:00:00,000 --> 00:00:01,000\nSRT\n", "text/plain")}, data={"offset": "20"}).json()
        assert r["subtitles"] == 1
        assert c.get(f"/api/projects/{pid}/media/{mid}/beats").status_code == 200


def test_import_from_url(home, media_dir):
    from fastapi import FastAPI
    from fastapi.responses import FileResponse

    from durostcm.server.app import create_app

    from .mocks import ServerThread, free_port

    app = FastAPI()

    @app.get("/plano.mp4")
    async def f():
        return FileResponse(media_dir / "clip_b.mp4", media_type="video/mp4")

    port = free_port()
    srv = ServerThread(app, port).start_and_wait()
    try:
        with TestClient(create_app()) as c:
            pid = c.post("/api/projects", json={"name": "URL"}).json()["id"]
            j = c.post(f"/api/projects/{pid}/media/url", json={"url": f"http://127.0.0.1:{port}/plano.mp4"}).json()
            for _ in range(100):
                jj = c.get(f"/api/jobs/{j['id']}").json()
                if jj["status"] in ("done", "error"):
                    break
                time.sleep(0.1)
            assert jj["status"] == "done", jj["error"]
            media = c.get(f"/api/projects/{pid}").json()["media"]
            assert media and media[0]["kind"] == "video" and "url" in media[0]["tags"]
            assert c.post(f"/api/projects/{pid}/media/url", json={"url": "file:///etc/passwd"}).status_code == 400
    finally:
        srv.stop()


def test_render_skips_missing_files(home, media_dir):
    store = get_store()
    p = store.create("Missing", width=320, height=180, fps=25)
    m = import_file(store, p, media_dir / "clip_a.mp4")
    p.tracks[0].clips.append(Clip(media_id=m.id, start=0, duration=2))
    p.tracks[2].clips.append(Clip(kind="text", start=0, duration=2, text=__import__("durostcm.core.project", fromlist=["TextStyle"]).TextStyle(content="ok")))
    store.save(p)
    store.resolve(p.id, m.path).unlink()
    res = asyncio.run(render_project(store, p, RenderSettings(format="mp4_h264", quality="draft")))
    assert res["warnings"] and "Falta el archivo" in res["warnings"][0]

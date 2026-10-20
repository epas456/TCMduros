from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(home):
    from durostcm.server.app import create_app

    with TestClient(create_app()) as c:
        yield c


def wait(client, job_id, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error", "cancelled"):
            return j
        time.sleep(0.2)
    raise TimeoutError(job_id)


def test_project_flow(client, media_dir):
    p = client.post("/api/projects", json={"name": "API"}).json()
    pid = p["id"]
    with open(media_dir / "clip_a.mp4", "rb") as f:
        r = client.post(f"/api/projects/{pid}/media", files=[("files", ("clip_a.mp4", f, "video/mp4"))]).json()
    assert r["media"] and not r["errors"]
    mid = r["media"][0]["id"]
    proj = client.get(f"/api/projects/{pid}").json()
    proj["tracks"][0]["clips"].append({"media_id": mid, "start": 0, "duration": 2})
    proj["media"][0]["name"] = "Renombrado"
    assert client.put(f"/api/projects/{pid}", json=proj).status_code == 200
    proj2 = client.get(f"/api/projects/{pid}").json()
    assert proj2["media"][0]["name"] == "Renombrado" and len(proj2["tracks"][0]["clips"]) == 1
    # autoguardado con medios ausentes no borra medios del servidor
    proj2["media"] = []
    client.put(f"/api/projects/{pid}", json=proj2)
    assert len(client.get(f"/api/projects/{pid}").json()["media"]) == 1
    # conflicto de revisión
    stale = {**proj2, "rev": proj2["rev"] - 1}
    r = client.put(f"/api/projects/{pid}", json=stale)
    assert r.status_code == 409 and "project" in r.json()
    j = client.post(f"/api/projects/{pid}/render", json={"format": "mp4_h264", "quality": "draft"}).json()
    j = wait(client, j["id"])
    assert j["status"] == "done", j["error"]
    assert client.get(f"/api/projects/{pid}/renders").json()["renders"]
    assert client.get(f"/api/projects/{pid}/frame?t=1").status_code == 200
    for fmt in ("edl", "fcpxml", "otio"):
        assert client.get(f"/api/projects/{pid}/export/{fmt}").status_code == 200
    f = client.get(f"/api/projects/{pid}/media/{mid}/file")
    assert f.status_code == 200 and len(f.content) > 1000


def test_generate_and_pipelines(client):
    pid = client.post("/api/projects", json={"name": "IA"}).json()["id"]
    j = client.post("/api/ai/generate", json={"project_id": pid, "capability": "text2image", "params": {"prompt": "faro", "width": 320, "height": 180}}).json()
    j = wait(client, j["id"])
    assert j["status"] == "done" and j["result"]["media"][0]["ai_generated"]
    j = client.post("/api/pipelines/ad", json={"project_id": pid, "params": {"product": "Nébula", "duration": 10, "aspect": "1:1"}}).json()
    j = wait(client, j["id"])
    assert j["status"] == "done", j["error"]
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["settings"]["width"] == proj["settings"]["height"]
    names = {t["name"]: len(t["clips"]) for t in proj["tracks"]}
    assert names["V1"] == 5 and names.get("Subtítulos", 0) >= 1 and names["A2 Música"] == 1
    total = max(c["start"] + c["duration"] for t in proj["tracks"] if t["kind"] == "video" for c in t["clips"])
    assert abs(total - 10) < 0.6
    assert client.get(f"/api/projects/{pid}/export/srt").status_code == 200


def test_character_pipeline(client):
    pid = client.post("/api/projects", json={"name": "Personaje"}).json()["id"]
    j = client.post("/api/pipelines/character_4k", json={"project_id": pid, "params": {
        "description": "guerrera nórdica de 30 años", "duration": 6, "reference_views": 2, "auto_export": True, "upscale": False}}).json()
    j = wait(client, j["id"], timeout=600)
    assert j["status"] == "done", (j["error"], j["logs"][-5:])
    res = j["result"]
    assert res["render"]["width"] == 3840 and res["render"]["height"] == 2160
    chars = client.get("/api/library/characters").json()["items"]
    assert any(c["id"] == res["character_id"] and c["hero_image"] for c in chars)


def test_library_and_faces(client, monkeypatch):
    from durostcm.faces import search as fs

    async def fake_search(q, providers=None, licenses=None, page=1):
        r = fs._apply_license(fs.FaceResult(id="openverse:1", provider="openverse", thumb_url="http://x/t.jpg", url="http://x/f.jpg", license="cc0"))
        return {"results": [r.model_dump()], "errors": {}, "licenses": ["cc0"]}

    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 150, 120)).save(buf, "JPEG")

    async def fake_download(url):
        return buf.getvalue()

    monkeypatch.setattr(fs, "search_faces", fake_search)
    monkeypatch.setattr(fs, "download", fake_download)
    r = client.get("/api/faces/search?q=retrato").json()
    assert r["results"][0]["commercial_ok"] is True and r["notice"]
    face = client.post("/api/faces/import", json={"result": r["results"][0], "describe": False}).json()
    assert face["credit"]["license"] == "cc0"
    assert client.get(f"/api/faces/{face['id']}/image?thumb=true").status_code == 200
    bad = fs.FaceResult(id="x", provider="openverse", thumb_url="t", url="u", license="by-nc").model_dump()
    bad = {**bad, "commercial_ok": True, "modification_ok": True}  # el servidor no se fía del cliente
    assert client.post("/api/faces/import", json={"result": bad}).status_code == 400
    c = client.post("/api/library/characters/design", json={"brief": "anciano pescador gallego", "face_ids": [face["id"]]}).json()
    assert c["inspiration"][0]["license"] == "cc0"
    cs = client.post("/api/consents", data={"person_name": "Actriz Ejemplo", "scope": "Campaña 2026"}).json()
    assert client.get("/api/consents").json()["items"][0]["id"] == cs["id"]


def test_settings_patch(client):
    s = client.patch("/api/settings", json={"endpoints": {"ollama_model": "llama3.2"}}).json()
    assert s["endpoints"]["ollama_model"] == "llama3.2" and s["endpoints"]["comfyui_url"]

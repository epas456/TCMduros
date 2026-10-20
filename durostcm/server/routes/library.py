"""Rutas de biblioteca: personajes, localizaciones, rostros de inspiración y consentimientos."""

from __future__ import annotations

import asyncio
import io
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ...ai.imagination import engine as IM
from ...ai.registry import get_registry
from ...ai.service import project_lock
from ...core.library import Character, Consent, FaceRef, Location, get_library
from ...core.media import register_media, unique_name
from ...core.project import Credit
from ...core.storage import get_store
from ...faces import search as face_search
from ...faces.ethics import face_usage_notice

router = APIRouter()


class DesignBody(BaseModel):
    brief: str = ""
    seed: int | None = None
    imagination: float = 0.5
    use_llm: bool = True
    face_ids: list[str] = []


# ------------------------------------------------------------------ personajes
@router.get("/library/characters")
async def characters():
    return {"items": get_library().list("characters")}


@router.post("/library/characters/design")
async def design_character(body: DesignBody):
    lib = get_library()
    inspiration = ""
    if body.face_ids:
        faces = {f.id: f for f in lib.faces()}
        inspiration = " | ".join(faces[i].description for i in body.face_ids if i in faces and faces[i].description)
    c = None
    if body.use_llm:
        llm = await get_registry().llm()
        if llm is not None:
            try:
                c = await IM.llm_character(llm, body.brief, inspiration)
            except Exception:
                c = None
    if c is None:
        c = IM.design_character(body.brief, seed=body.seed, imagination=body.imagination)
        if inspiration:
            c.identity_prompt += f", subtle features inspired by: {inspiration[:300]}"
    if body.face_ids:
        faces = {f.id: f for f in lib.faces()}
        c.inspiration = [faces[i].credit for i in body.face_ids if i in faces]
    lib.save("characters", c)
    return c.model_dump()


@router.post("/library/characters")
async def create_character(c: Character):
    return get_library().save("characters", c).model_dump()


@router.get("/library/characters/{cid}")
async def get_character(cid: str):
    return get_library().get("characters", cid).model_dump()


@router.put("/library/characters/{cid}")
async def update_character(cid: str, c: Character):
    c.id = cid
    return get_library().save("characters", c).model_dump()


@router.delete("/library/characters/{cid}")
async def delete_character(cid: str):
    get_library().delete("characters", cid)
    return {"ok": True}


@router.get("/library/characters/{cid}/turnaround")
async def turnaround(cid: str):
    c = get_library().get("characters", cid)
    return {"views": IM.character_turnaround_prompts(c)}  # type: ignore[arg-type]


# ------------------------------------------------------------------ localizaciones
@router.get("/library/locations")
async def locations():
    return {"items": get_library().list("locations")}


@router.post("/library/locations/design")
async def design_location(body: DesignBody):
    lo = IM.design_location(body.brief, seed=body.seed, imagination=body.imagination)
    return get_library().save("locations", lo).model_dump()


@router.post("/library/locations")
async def create_location(lo: Location):
    return get_library().save("locations", lo).model_dump()


@router.put("/library/locations/{lid}")
async def update_location(lid: str, lo: Location):
    lo.id = lid
    return get_library().save("locations", lo).model_dump()


@router.delete("/library/locations/{lid}")
async def delete_location(lid: str):
    get_library().delete("locations", lid)
    return {"ok": True}


# ------------------------------------------------------------------ imágenes de personajes/localizaciones
@router.post("/library/{kind}/{item_id}/images")
async def add_image(kind: str, item_id: str, file: UploadFile | None = File(None), project_id: str | None = Form(None),
                    media_id: str | None = Form(None), hero: bool = Form(False)):
    if kind not in ("characters", "locations"):
        raise HTTPException(400, "Tipo inválido")
    lib = get_library()
    if file is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "x.png").suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            src = Path(tmp.name)
        name = lib.add_image(kind, item_id, src, as_hero=hero)  # type: ignore[arg-type]
        src.unlink(missing_ok=True)
    elif project_id and media_id:
        store = get_store()
        m = store.get(project_id).media_by_id(media_id)
        if m is None or m.kind != "image":
            raise HTTPException(400, "El medio debe ser una imagen")
        name = lib.add_image(kind, item_id, store.resolve(project_id, m.path), as_hero=hero)  # type: ignore[arg-type]
    else:
        raise HTTPException(400, "Envía un archivo o un medio del proyecto")
    return {"name": name, "item": lib.get(kind, item_id).model_dump()}  # type: ignore[arg-type]


@router.get("/library/{kind}/{item_id}/images/{name}")
async def get_image(kind: str, item_id: str, name: str):
    if kind not in ("characters", "locations"):
        raise HTTPException(400, "Tipo inválido")
    p = get_library().file(kind, item_id, name)  # type: ignore[arg-type]
    if not p.exists():
        raise HTTPException(404, "Imagen no encontrada")
    return FileResponse(p)


@router.post("/library/{kind}/{item_id}/to-project/{pid}")
async def to_project(kind: str, item_id: str, pid: str):
    """Añade las imágenes de referencia de un personaje/localización como medios del proyecto."""
    lib = get_library()
    item = lib.get(kind, item_id)  # type: ignore[arg-type]
    store = get_store()
    added = []
    async with project_lock(pid):
        p = store.get(pid)
        for name in item.reference_images:
            src = lib.file(kind, item_id, name)  # type: ignore[arg-type]
            dst = unique_name(store.subdir(pid, "media"), f"{item.name}_{name}")
            shutil.copy2(src, dst)
            m = await asyncio.to_thread(register_media, store, p, dst, name=f"{item.name} · ref", source="import", tags=[kind, item.id])
            m.ai_generated = True
            added.append(m.model_dump())
        if kind == "characters" and item.id not in p.characters:
            p.characters.append(item.id)
        if kind == "locations" and item.id not in p.locations:
            p.locations.append(item.id)
        store.save(p)
    return {"media": added}


# ------------------------------------------------------------------ rostros de inspiración
@router.get("/faces/search")
async def faces_search(q: str, providers: str = "", licenses: str = "", page: int = 1):
    res = await face_search.search_faces(q, [x for x in providers.split(",") if x] or None, [x for x in licenses.split(",") if x] or None, page)
    res["notice"] = face_usage_notice()
    return res


class FaceImport(BaseModel):
    result: dict
    describe: bool = True


@router.post("/faces/import")
async def faces_import(body: FaceImport):
    r = face_search.FaceResult.model_validate(body.result)
    r.attribution = r.attribution or ""
    r = face_search._apply_license(r)  # las licencias se recalculan en el servidor
    if not r.commercial_ok or not r.modification_ok:
        raise HTTPException(400, "Esta licencia no permite uso comercial y obras derivadas: elige otra imagen")
    data = await face_search.download(r.url)
    lib = get_library()
    face = FaceRef(file="", credit=Credit(title=r.title, creator=r.creator, license=r.license, license_url=r.license_url,
                                          source_url=r.landing_url or r.url, provider=r.provider, attribution=r.attribution))
    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((2048, 2048))
    face.file = f"{face.id}.jpg"
    img.save(lib.faces_dir / face.file, quality=92)
    th = img.copy()
    th.thumbnail((320, 320))
    face.thumb = f"{face.id}_t.jpg"
    th.save(lib.faces_dir / face.thumb, quality=85)
    if body.describe:
        vis = await get_registry().vision()
        if vis is not None:
            face.description = await IM.describe_face_features(vis, lib.faces_dir / face.file) or ""
    lib.add_face(face)
    return face.model_dump()


@router.post("/faces/upload")
async def faces_upload(file: UploadFile = File(...), consent_id: str = Form(""), description: str = Form("")):
    """Rostro propio (fotografía de la empresa o de un actor con cesión firmada)."""
    lib = get_library()
    from PIL import Image

    img = Image.open(io.BytesIO(await file.read())).convert("RGB")
    img.thumbnail((2048, 2048))
    face = FaceRef(file="", credit=Credit(title=file.filename or "", license="consent" if consent_id else "own", provider="upload"),
                   consent_id=consent_id or None, description=description)
    face.file = f"{face.id}.jpg"
    img.save(lib.faces_dir / face.file, quality=92)
    th = img.copy()
    th.thumbnail((320, 320))
    face.thumb = f"{face.id}_t.jpg"
    th.save(lib.faces_dir / face.thumb, quality=85)
    lib.add_face(face)
    return face.model_dump()


@router.get("/faces")
async def faces():
    return {"items": [f.model_dump() for f in get_library().faces()], "notice": face_usage_notice()}


@router.patch("/faces/{fid}")
async def update_face(fid: str, body: dict):
    lib = get_library()
    faces = lib.faces()
    for f in faces:
        if f.id == fid:
            if "description" in body:
                f.description = str(body["description"])
            if "tags" in body:
                f.tags = [str(t) for t in body["tags"]]
    lib.save_faces(faces)
    return {"ok": True}


@router.post("/faces/{fid}/describe")
async def describe_face(fid: str):
    lib = get_library()
    vis = await get_registry().vision()
    if vis is None:
        raise HTTPException(503, "Necesitas un modelo de visión (p. ej. ollama pull qwen2.5vl:7b)")
    faces = lib.faces()
    for f in faces:
        if f.id == fid:
            f.description = await IM.describe_face_features(vis, lib.faces_dir / f.file) or f.description
            lib.save_faces(faces)
            return f.model_dump()
    raise HTTPException(404, "Rostro no encontrado")


@router.get("/faces/{fid}/image")
async def face_image(fid: str, thumb: bool = False):
    lib = get_library()
    f = next((x for x in lib.faces() if x.id == fid), None)
    if f is None:
        raise HTTPException(404, "Rostro no encontrado")
    name = f.thumb if thumb and f.thumb else f.file
    return FileResponse(lib.faces_dir / name)


@router.delete("/faces/{fid}")
async def delete_face(fid: str):
    get_library().delete_face(fid)
    return {"ok": True}


# ------------------------------------------------------------------ consentimientos
@router.get("/consents")
async def consents():
    return {"items": [c.model_dump() for c in get_library().consents()]}


@router.post("/consents")
async def add_consent(person_name: str = Form(...), scope: str = Form(""), valid_until: str = Form(""), signed_on: str = Form(""),
                      notes: str = Form(""), document: UploadFile | None = File(None)):
    lib = get_library()
    c = Consent(person_name=person_name, scope=scope, valid_until=valid_until, signed_on=signed_on, notes=notes)
    if document is not None:
        name = f"{c.id}{Path(document.filename or 'doc.pdf').suffix.lower()}"
        with open(lib.consents_dir / name, "wb") as f:
            shutil.copyfileobj(document.file, f)
        c.document = name
    return lib.save_consent(c).model_dump()


@router.get("/consents/{cid}/document")
async def consent_doc(cid: str):
    lib = get_library()
    c = next((x for x in lib.consents() if x.id == cid), None)
    if c is None or not c.document:
        raise HTTPException(404, "Documento no encontrado")
    return FileResponse(lib.consents_dir / c.document)


@router.delete("/consents/{cid}")
async def delete_consent(cid: str):
    get_library().delete_consent(cid)
    return {"ok": True}

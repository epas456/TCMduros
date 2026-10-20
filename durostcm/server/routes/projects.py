"""Rutas de proyectos: CRUD, medios, archivos, render, storyboard e intercambio (EDL/FCPXML)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from ...ai.service import project_lock, schedule_proxy
from ...core.ffmpeg import run_ffmpeg
from ...core.interchange import export_edl, export_fcpxml, export_otio_json
from ...core.jobs import JobContext, get_jobs
from ...core.media import import_file, kind_for, needs_proxy, register_media, unique_name
from ...core.project import Storyboard
from ...core.render import RenderSettings, render_frame, render_project
from ...core.storage import get_store

router = APIRouter()


class NewProject(BaseModel):
    name: str = "Proyecto sin título"
    width: int = 1920
    height: int = 1080
    fps: float = 24


@router.get("/projects")
async def list_projects():
    return {"projects": await asyncio.to_thread(get_store().list)}


@router.post("/projects")
async def create_project(body: NewProject):
    p = get_store().create(body.name, width=body.width, height=body.height, fps=body.fps)
    return p.model_dump()


@router.get("/projects/{pid}")
async def get_project(pid: str):
    return get_store().get(pid).model_dump()


@router.put("/projects/{pid}")
async def save_project(pid: str, body: dict):
    async with project_lock(pid):
        p = await asyncio.to_thread(get_store().apply_client, pid, body)
    return {"ok": True, "rev": p.rev, "updated": p.updated}


@router.delete("/projects/{pid}")
async def delete_project(pid: str):
    get_store().delete(pid)
    return {"ok": True}


@router.post("/projects/{pid}/duplicate")
async def duplicate(pid: str, name: str | None = None):
    return get_store().duplicate(pid, name).model_dump()


@router.get("/projects/{pid}/history")
async def history(pid: str):
    return {"snapshots": get_store().history(pid)}


@router.post("/projects/{pid}/restore/{snap}")
async def restore(pid: str, snap: str):
    store = get_store()
    async with project_lock(pid):
        p = store.restore(pid, snap)
        p = store.bump(p)
    await get_jobs().broadcast({"type": "project_changed", "project_id": pid})
    return p.model_dump()


# ------------------------------------------------------------------ medios
@router.post("/projects/{pid}/media")
async def upload_media(pid: str, files: list[UploadFile] = File(...)):
    store = get_store()
    folder = store.subdir(pid, "media")
    added, errors = [], []
    for f in files:
        name = Path(f.filename or "archivo").name
        dst = unique_name(folder, name)
        with open(dst, "wb") as out:
            await asyncio.to_thread(shutil.copyfileobj, f.file, out, 1 << 20)
        try:
            async with project_lock(pid):
                p = store.get(pid)
                item = await asyncio.to_thread(register_media, store, p, dst, name=name, source="upload")
                store.save(p)
            added.append(item.model_dump())
            if needs_proxy(item):
                schedule_proxy(pid, item.id)
        except Exception as e:  # noqa: BLE001
            dst.unlink(missing_ok=True)
            errors.append({"file": name, "error": str(e)[:300]})
    return {"media": added, "errors": errors}


class ImportUrl(BaseModel):
    url: str
    name: str | None = None


@router.post("/projects/{pid}/media/url")
async def import_url(pid: str, body: ImportUrl):
    """Descarga un medio desde una URL directa (o una página compatible con yt-dlp, si está instalado).

    Usa sólo contenido sobre el que tengas derechos o licencia libre.
    """
    import shutil as _sh
    import tempfile
    from urllib.parse import urlparse

    import httpx

    url = body.url.strip()
    if urlparse(url).scheme not in ("http", "https"):
        raise HTTPException(400, "URL no válida")
    store = get_store()
    store.get(pid)

    async def job(ctx: JobContext):
        folder = store.subdir(pid, "media")
        tmpdir = Path(tempfile.mkdtemp(dir=store.subdir(pid, "cache")))
        try:
            path_name = Path(urlparse(url).path).name
            direct = kind_for(Path(path_name)) is not None
            if not direct and _sh.which("yt-dlp"):
                await ctx.progress(0.05, "Descargando con yt-dlp")
                proc = await asyncio.create_subprocess_exec(
                    "yt-dlp", "-f", "bv*[height<=2160]+ba/b", "--merge-output-format", "mp4", "-o", str(tmpdir / "%(title).80s.%(ext)s"), url,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _o, err = await proc.communicate()
                if proc.returncode != 0:
                    raise RuntimeError(err.decode("utf-8", "ignore")[-400:])
                files = [f for f in tmpdir.iterdir() if f.is_file()]
                if not files:
                    raise RuntimeError("yt-dlp no descargó nada")
                src = files[0]
            else:
                src = tmpdir / (path_name or "descarga.mp4")
                async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=300), follow_redirects=True) as c:
                    async with c.stream("GET", url) as r:
                        r.raise_for_status()
                        total = int(r.headers.get("content-length", 0))
                        got = 0
                        with open(src, "wb") as fh:
                            async for chunk in r.aiter_bytes(1 << 20):
                                ctx.check()
                                fh.write(chunk)
                                got += len(chunk)
                                if total:
                                    await ctx.progress(got / total * 0.95, f"{got / 2**20:.1f}/{total / 2**20:.1f} MB")
                if kind_for(src) is None:
                    ct = r.headers.get("content-type", "")
                    ext = {"video/mp4": ".mp4", "video/webm": ".webm", "image/jpeg": ".jpg", "image/png": ".png", "audio/mpeg": ".mp3", "audio/wav": ".wav"}.get(ct.split(";")[0], "")
                    if not ext:
                        raise ValueError("La URL no apunta a un vídeo, imagen o audio (instala yt-dlp para páginas web)")
                    src = src.rename(src.with_suffix(ext))
            dst = unique_name(folder, body.name or src.name)
            _sh.move(str(src), dst)
            async with project_lock(pid):
                p = store.get(pid)
                item = await asyncio.to_thread(register_media, store, p, dst, name=body.name or dst.name, source="import",
                                               credit=None, tags=["url"])
                store.save(p)
            await get_jobs().broadcast({"type": "media_added", "project_id": pid, "media": [item.model_dump()]})
            if needs_proxy(item):
                schedule_proxy(pid, item.id)
            return {"media": [item.model_dump()]}
        finally:
            _sh.rmtree(tmpdir, ignore_errors=True)

    j = get_jobs().submit("download", "Importar desde URL", job, project_id=pid, pool="io")
    return j.public()


class ImportPaths(BaseModel):
    paths: list[str]
    copy_files: bool = True


@router.post("/projects/{pid}/media/import")
async def import_paths(pid: str, body: ImportPaths):
    store = get_store()
    added, errors = [], []
    for raw in body.paths:
        src = Path(raw).expanduser()
        files = [x for x in src.rglob("*") if x.is_file() and kind_for(x)] if src.is_dir() else [src]
        for f in files:
            try:
                async with project_lock(pid):
                    p = store.get(pid)
                    item = await asyncio.to_thread(import_file, store, p, f, copy=body.copy_files)
                    store.save(p)
                added.append(item.model_dump())
                if needs_proxy(item):
                    schedule_proxy(pid, item.id)
            except Exception as e:  # noqa: BLE001
                errors.append({"file": str(f), "error": str(e)[:300]})
    return {"media": added, "errors": errors}


@router.delete("/projects/{pid}/media/{mid}")
async def delete_media(pid: str, mid: str, delete_file: bool = False):
    store = get_store()
    async with project_lock(pid):
        p = store.get(pid)
        m = p.media_by_id(mid)
        if m is None:
            raise HTTPException(404, "Medio no encontrado")
        used = any(c.media_id == mid for t in p.tracks for c in t.clips)
        p.media = [x for x in p.media if x.id != mid]
        if used:
            for t in p.tracks:
                t.clips = [c for c in t.clips if c.media_id != mid]
        if delete_file and not Path(m.path).is_absolute():
            for rel in (m.path, m.proxy, m.thumbnail, m.waveform):
                if rel:
                    store.resolve(pid, rel).unlink(missing_ok=True)
        if used:
            store.bump(p)
        else:
            store.save(p)
    if used:
        await get_jobs().broadcast({"type": "project_changed", "project_id": pid})
    return {"ok": True, "removed_clips": used}


@router.get("/projects/{pid}/files/{rel:path}")
async def project_file(pid: str, rel: str):
    p = get_store().resolve(pid, rel)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(p)


_webm_locks: dict[str, asyncio.Lock] = {}


@router.get("/projects/{pid}/media/{mid}/file")
async def media_file(pid: str, mid: str, proxy: bool = True, webm: bool = False):
    """Archivo de un medio. ``webm=true`` sirve un proxy VP9/Opus para navegadores sin H.264."""
    store = get_store()
    m = store.get(pid).media_by_id(mid)
    if m is None:
        raise HTTPException(404, "Medio no encontrado")
    if webm and m.kind in ("video", "audio"):
        dst = store.subdir(pid, "cache") / f"{m.id}_proxy.webm"
        async with _webm_locks.setdefault(f"{pid}/{mid}", asyncio.Lock()):
            if not dst.exists():
                src = store.resolve(pid, m.path)
                tmp = dst.with_suffix(".part.webm")
                if m.kind == "video":
                    args = ["-i", str(src), "-vf", "scale='min(960,iw)':-2", "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
                            "-row-mt", "1", "-crf", "38", "-b:v", "0", "-g", "12", "-c:a", "libopus", "-b:a", "96k", str(tmp)]
                else:
                    args = ["-i", str(src), "-vn", "-c:a", "libopus", "-b:a", "128k", str(tmp)]
                await run_ffmpeg(args, label="proxy-webm")
                tmp.replace(dst)
        return FileResponse(dst, media_type="video/webm" if m.kind == "video" else "audio/webm")
    rel = m.proxy if (proxy and m.proxy) else m.path
    path = store.resolve(pid, rel)
    if not path.exists():
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(path)


# ------------------------------------------------------------------ render
@router.post("/projects/{pid}/render")
async def render(pid: str, settings: RenderSettings):
    store = get_store()
    store.get(pid)

    async def job(ctx: JobContext):
        p = store.get(pid)
        return await render_project(store, p, settings, progress=ctx.progress, cancel_event=ctx.cancel_event, job_id=ctx.job.id)

    title = "Previsualización" if settings.preview else f"Exportar {settings.format}"
    j = get_jobs().submit("render", title, job, project_id=pid, pool="cpu")
    return j.public()


@router.get("/projects/{pid}/frame")
async def frame(pid: str, t: float = 0.0, h: int = 540):
    store = get_store()
    path = await render_frame(store, store.get(pid), t, max_h=max(90, min(2160, h)))
    data = path.read_bytes()
    path.unlink(missing_ok=True)
    return Response(content=data, media_type="image/jpeg")


@router.get("/projects/{pid}/renders")
async def renders(pid: str):
    store = get_store()
    d = store.subdir(pid, "renders")
    files = sorted((f for f in d.iterdir() if f.is_file()), key=lambda f: f.stat().st_mtime, reverse=True)
    return {"renders": [{"name": f.name, "path": store.relative(pid, f), "size_bytes": f.stat().st_size, "time": f.stat().st_mtime} for f in files]}


@router.delete("/projects/{pid}/renders/{name}")
async def delete_render(pid: str, name: str):
    store = get_store()
    f = store.resolve(pid, f"renders/{Path(name).name}")
    f.unlink(missing_ok=True)
    return {"ok": True}


@router.post("/projects/{pid}/renders/{name}/import")
async def import_render(pid: str, name: str):
    """Añade un render terminado como medio (para usarlo en otro montaje)."""
    store = get_store()
    f = store.resolve(pid, f"renders/{Path(name).name}")
    async with project_lock(pid):
        p = store.get(pid)
        item = await asyncio.to_thread(register_media, store, p, f, name=f.name, source="render")
        store.save(p)
    return item.model_dump()


# ------------------------------------------------------------------ storyboard
@router.put("/projects/{pid}/storyboard")
async def put_storyboard(pid: str, sb: Storyboard):
    store = get_store()
    async with project_lock(pid):
        p = store.get(pid)
        p.storyboard = sb
        store.save(p)
    return sb.model_dump()


@router.delete("/projects/{pid}/storyboard")
async def delete_storyboard(pid: str):
    store = get_store()
    async with project_lock(pid):
        p = store.get(pid)
        p.storyboard = None
        store.save(p)
    return {"ok": True}


# ------------------------------------------------------------------ intercambio
@router.get("/projects/{pid}/export/{fmt}")
async def export_interchange(pid: str, fmt: str):
    store = get_store()
    p = store.get(pid)
    if fmt == "edl":
        return Response(export_edl(p), media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{p.name}.edl"'})
    if fmt == "fcpxml":
        return Response(export_fcpxml(p, store), media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{p.name}.fcpxml"'})
    if fmt == "otio":
        return Response(export_otio_json(p, store), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{p.name}.otio"'})
    if fmt == "srt":
        from ...core.render import export_srt

        tmp = store.subdir(pid, "cache") / "export.srt"
        out = export_srt(p, tmp)
        if out is None:
            raise HTTPException(404, "No hay subtítulos en el proyecto")
        return FileResponse(out, filename=f"{p.name}.srt")
    raise HTTPException(400, "Formato no soportado (edl, fcpxml, otio, srt)")


@router.post("/projects/{pid}/upload-file")
async def upload_generic(pid: str, file: UploadFile = File(...), folder: str = Form("media")):
    """Sube un archivo auxiliar (p. ej. imagen de referencia) sin registrarlo como medio."""
    store = get_store()
    if folder not in ("media", "cache"):
        raise HTTPException(400, "Carpeta no permitida")
    dst = unique_name(store.subdir(pid, folder), Path(file.filename or "archivo").name)
    with open(dst, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"path": store.relative(pid, dst)}

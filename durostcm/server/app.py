"""Aplicación FastAPI de durosTCM: API REST + WebSocket + interfaz web."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import APP_NAME, __version__
from ..ai.base import EngineUnavailable
from ..config import get_config
from ..core.jobs import get_jobs
from ..core.storage import Conflict, ProjectNotFound
from .routes import ai as ai_routes
from .routes import library as library_routes
from .routes import projects as project_routes
from .routes import system as system_routes

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app() -> FastAPI:
    app = FastAPI(title=APP_NAME, version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def auth(request: Request, call_next):
        token = get_config().settings.auth_token
        if token and request.url.path.startswith("/api/") and request.url.path not in ("/api/health",):
            given = request.headers.get("x-durostcm-token") or request.query_params.get("token")
            if given != token:
                return JSONResponse({"detail": "Token requerido"}, status_code=401)
        return await call_next(request)

    @app.exception_handler(ProjectNotFound)
    async def _nf(_r, e):
        return JSONResponse({"detail": f"No encontrado: {e}"}, status_code=404)

    @app.exception_handler(KeyError)
    async def _ke(_r, e):
        return JSONResponse({"detail": f"No encontrado: {e}"}, status_code=404)

    @app.exception_handler(Conflict)
    async def _cf(_r, e: Conflict):
        return JSONResponse({"detail": str(e), "project": e.current.model_dump()}, status_code=409)

    @app.exception_handler(EngineUnavailable)
    async def _eu(_r, e):
        return JSONResponse({"detail": str(e)}, status_code=503)

    @app.exception_handler(PermissionError)
    async def _pe(_r, e):
        return JSONResponse({"detail": str(e) or "Prohibido"}, status_code=403)

    @app.exception_handler(ValueError)
    async def _ve(_r, e):
        return JSONResponse({"detail": str(e)}, status_code=400)

    @app.exception_handler(FileNotFoundError)
    async def _fnf(_r, e):
        return JSONResponse({"detail": f"Archivo no encontrado: {e}"}, status_code=404)

    app.include_router(system_routes.router, prefix="/api")
    app.include_router(project_routes.router, prefix="/api")
    app.include_router(ai_routes.router, prefix="/api")
    app.include_router(library_routes.router, prefix="/api")

    @app.websocket("/api/ws")
    async def ws(websocket: WebSocket):
        token = get_config().settings.auth_token
        if token and websocket.query_params.get("token") != token:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        jobs = get_jobs()
        q = jobs.subscribe()
        try:
            await websocket.send_json({"type": "hello", "app": APP_NAME, "version": __version__})

            async def pump():
                while True:
                    msg = await q.get()
                    await websocket.send_json(msg)

            async def recv():
                while True:
                    await websocket.receive_text()

            await asyncio.gather(pump(), recv())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            jobs.unsubscribe(q)

    if (WEB_DIR / "index.html").exists():
        assets = WEB_DIR / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "No encontrado"}, status_code=404)
            candidate = (WEB_DIR / full_path).resolve()
            if full_path and candidate.is_file() and WEB_DIR in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(WEB_DIR / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        async def no_ui():
            return HTMLResponse(
                f"<h1>{APP_NAME} {__version__}</h1><p>La API funciona. Compila la interfaz con "
                "<code>npm --prefix frontend install && npm --prefix frontend run build</code>.</p>"
                "<p><a href='/api/docs'>Documentación de la API</a></p>"
            )

    return app

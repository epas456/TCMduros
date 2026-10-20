"""Línea de comandos de durosTCM.

    durostcm serve [--host 127.0.0.1] [--port 7777] [--no-browser]
    durostcm doctor
    durostcm render <id_proyecto> [--format mp4_h264] [--width 3840 --height 2160] [--quality high]
    durostcm projects
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import time
import webbrowser

from . import APP_NAME, __version__
from .config import get_config


def _banner() -> None:
    print(
        r"""
     _                    _____ ____ __  __
  __| |_   _ _ __ ___  __|_   _/ ___|  \/  |
 / _` | | | | '__/ _ \/ __|| || |   | |\/| |
| (_| | |_| | | | (_) \__ \| || |___| |  | |
 \__,_|\__,_|_|  \___/|___/|_| \____|_|  |_|   """ + f"v{__version__}\n  Estudio de vídeo con IA local\n"
    )


def cmd_serve(args) -> None:
    import uvicorn

    from .server.app import create_app

    cfg = get_config()
    host = args.host or cfg.settings.host
    port = args.port or cfg.settings.port
    _banner()
    if host not in ("127.0.0.1", "localhost") and not cfg.settings.auth_token:
        print("⚠  Expones durosTCM en la red sin token. Define 'auth_token' en", cfg.config_file)
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}"
    print(f"  Datos:     {cfg.home}\n  Interfaz:  {url}\n  API:       {url}/api/docs\n")
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(url)), daemon=True).start()
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


def cmd_doctor(_args) -> None:
    from .ai.registry import get_registry
    from .core import hardware
    from .core.ffmpeg import ffmpeg_version, has_ffmpeg

    _banner()
    hw = hardware.detect()
    print(f"Sistema:   {hw['os']} · Python {hw['python']} · {hw['cores']} núcleos · {hw['ram_gb']} GB RAM")
    gpus = ", ".join(f"{g['name']} ({g.get('vram_gb')} GB)" for g in hw["gpus"]) or "ninguna"
    print(f"GPU:       {gpus}  →  {hardware.TIERS[hw['tier']]['label']}")
    print(f"FFmpeg:    {'✔ ' + ffmpeg_version() if has_ffmpeg() else '✘ NO ENCONTRADO (obligatorio)'}")
    print("\nMotores de IA:")

    async def run():
        reg = get_registry()
        for e in await reg.all_status(refresh=True):
            st = e["status"]
            print(f"  {'✔' if st['available'] else '·'} {e['name']:<38} {st['detail']}")
        caps = await reg.capabilities()
        print("\nCapacidades:")
        for k, v in caps.items():
            print(f"  {v['label']:<52} → {v['best'] or '—'}")

    asyncio.run(run())
    rec = hardware.recommendations(hw["tier"])
    print("\nRecomendado para tu equipo:")
    for k, v in rec.items():
        print(f"  {k:<6} {v}")


def cmd_projects(_args) -> None:
    from .core.storage import get_store

    for p in get_store().list():
        print(f"{p['id']}  {p['name']:<40} {p['width']}x{p['height']}@{p['fps']}  {time.strftime('%Y-%m-%d %H:%M', time.localtime(p['updated']))}")


def cmd_render(args) -> None:
    from .core.render import RenderSettings, render_project
    from .core.storage import get_store

    store = get_store()
    p = store.get(args.project)
    s = RenderSettings(format=args.format, width=args.width, height=args.height, fps=args.fps, quality=args.quality, loudness=args.loudness)

    async def prog(v, _l):
        bar = "█" * int(v * 30)
        print(f"\r  [{bar:<30}] {v * 100:5.1f}%", end="", flush=True)

    res = asyncio.run(render_project(store, p, s, progress=prog))
    print(f"\n✔ {store.resolve(p.id, res['path'])}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="durostcm", description=f"{APP_NAME} {__version__} — estudio de vídeo con IA local")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="Arranca el estudio (por defecto)")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.add_argument("--no-browser", action="store_true")
    sub.add_parser("doctor", help="Diagnóstico de hardware, FFmpeg y motores IA")
    sub.add_parser("projects", help="Lista los proyectos")
    r = sub.add_parser("render", help="Renderiza un proyecto desde la terminal")
    r.add_argument("project")
    r.add_argument("--format", default="mp4_h264")
    r.add_argument("--width", type=int)
    r.add_argument("--height", type=int)
    r.add_argument("--fps", type=float)
    r.add_argument("--quality", default="high", choices=["draft", "good", "high", "master"])
    r.add_argument("--loudness", type=float)
    args = ap.parse_args(argv)
    if args.cmd in (None, "serve"):
        if args.cmd is None:
            args = ap.parse_args(["serve", *(argv or sys.argv[1:])])
        cmd_serve(args)
    elif args.cmd == "doctor":
        cmd_doctor(args)
    elif args.cmd == "projects":
        cmd_projects(args)
    elif args.cmd == "render":
        cmd_render(args)


if __name__ == "__main__":
    main()

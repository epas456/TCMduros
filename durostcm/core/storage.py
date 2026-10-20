"""Persistencia de proyectos en disco (JSON atómico + historial de versiones)."""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

from ..config import AppConfig, get_config
from .project import Project, default_project, new_id

_HISTORY_KEEP = 30


class ProjectNotFound(KeyError):
    pass


class Conflict(Exception):
    def __init__(self, current: Project):
        super().__init__("El proyecto cambió en el servidor")
        self.current = current


class ProjectStore:
    def __init__(self, cfg: AppConfig | None = None):
        self.cfg = cfg or get_config()
        self._locks: dict[str, threading.Lock] = {}
        self._cache: dict[str, Project] = {}

    def _lock(self, pid: str) -> threading.Lock:
        return self._locks.setdefault(pid, threading.Lock())

    # ------------------------------------------------------------ rutas
    def project_dir(self, pid: str) -> Path:
        safe = "".join(ch for ch in pid if ch.isalnum() or ch in "_-")
        if not safe or safe != pid:
            raise ProjectNotFound(pid)
        return self.cfg.projects_dir / safe

    def subdir(self, pid: str, name: str) -> Path:
        d = self.project_dir(pid) / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def resolve(self, pid: str, rel: str) -> Path:
        """Ruta absoluta de un recurso del proyecto, sin permitir escapar de su carpeta."""
        p = Path(rel)
        if p.is_absolute():
            return p
        base = self.project_dir(pid).resolve()
        full = (base / p).resolve()
        if base not in full.parents and full != base:
            raise PermissionError("Ruta fuera del proyecto")
        return full

    def relative(self, pid: str, path: Path) -> str:
        base = self.project_dir(pid).resolve()
        try:
            return path.resolve().relative_to(base).as_posix()
        except ValueError:
            return str(path.resolve())

    # ------------------------------------------------------------ CRUD
    def list(self) -> list[dict]:
        out = []
        for d in sorted(self.cfg.projects_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            f = d / "project.json"
            if not f.exists():
                continue
            try:
                data = json.loads(f.read_text("utf-8"))
            except Exception:
                continue
            thumb = None
            for m in data.get("media", []):
                if m.get("thumbnail"):
                    thumb = m["thumbnail"]
                    break
            s = data.get("settings", {})
            out.append(
                {
                    "id": data.get("id", d.name),
                    "name": data.get("name", d.name),
                    "updated": data.get("updated", 0),
                    "created": data.get("created", 0),
                    "width": s.get("width"),
                    "height": s.get("height"),
                    "fps": s.get("fps"),
                    "media_count": len(data.get("media", [])),
                    "thumbnail": thumb,
                }
            )
        return out

    def create(self, name: str = "Proyecto sin título", **settings) -> Project:
        p = default_project(name, **settings)
        d = self.project_dir(p.id)
        for sub in ("media", "generated", "renders", "cache", ".history"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        self.save(p, history=False)
        return p

    def get(self, pid: str) -> Project:
        if pid in self._cache:
            return self._cache[pid]
        f = self.project_dir(pid) / "project.json"
        if not f.exists():
            raise ProjectNotFound(pid)
        p = Project.model_validate_json(f.read_text("utf-8"))
        self._cache[pid] = p
        return p

    def save(self, p: Project, history: bool = True) -> Project:
        with self._lock(p.id):
            d = self.project_dir(p.id)
            d.mkdir(parents=True, exist_ok=True)
            f = d / "project.json"
            if history and f.exists():
                h = d / ".history"
                h.mkdir(exist_ok=True)
                # como mucho una instantánea cada 60 s
                snaps = sorted(h.glob("*.json"))
                if not snaps or time.time() - snaps[-1].stat().st_mtime > 60:
                    shutil.copy2(f, h / f"{int(time.time() * 1000)}.json")
                    for old in snaps[: max(0, len(snaps) + 1 - _HISTORY_KEEP)]:
                        old.unlink(missing_ok=True)
            p.updated = time.time()
            tmp = f.with_suffix(".json.tmp")
            tmp.write_text(p.model_dump_json(indent=1), "utf-8")
            tmp.replace(f)
            self._cache[p.id] = p
            return p

    def apply_client(self, pid: str, data: dict) -> Project:
        """Aplica el autoguardado del editor.

        El editor es dueño de: nombre, ajustes, pistas, marcadores y notas (y de renombrar/etiquetar
        medios). El servidor es dueño de: medios (alta/baja), storyboard, créditos y biblias. Si un
        proceso del servidor cambió la línea de tiempo (``rev``) desde que el editor la cargó, se
        lanza ``Conflict`` para que el editor recargue.
        """
        with self._lock(pid):
            cur = self.get(pid)
            client_rev = int(data.get("rev", cur.rev))
            if client_rev != cur.rev:
                raise Conflict(cur)
            merged = cur.model_dump()
            for k in ("name", "settings", "tracks", "markers", "notes"):
                if k in data:
                    merged[k] = data[k]
            p = Project.model_validate(merged)
            patches = {m["id"]: m for m in data.get("media", []) if isinstance(m, dict) and "id" in m}
            for m in p.media:
                patch = patches.get(m.id)
                if patch:
                    if isinstance(patch.get("name"), str):
                        m.name = patch["name"]
                    if isinstance(patch.get("tags"), list):
                        m.tags = [str(t) for t in patch["tags"]]
        return self.save(p)

    def bump(self, p: Project) -> Project:
        """Guarda un cambio hecho por el servidor en la línea de tiempo."""
        p.rev += 1
        return self.save(p)

    def delete(self, pid: str) -> None:
        d = self.project_dir(pid)
        if d.exists():
            shutil.rmtree(d)
        self._cache.pop(pid, None)

    def duplicate(self, pid: str, name: str | None = None) -> Project:
        src = self.get(pid)
        nid = new_id("p_")
        shutil.copytree(
            self.project_dir(pid), self.project_dir(nid), ignore=shutil.ignore_patterns(".history", "renders")
        )
        p = src.model_copy(deep=True)
        p.id = nid
        p.name = name or f"{src.name} (copia)"
        p.created = time.time()
        return self.save(p, history=False)

    def history(self, pid: str) -> list[dict]:
        h = self.project_dir(pid) / ".history"
        if not h.exists():
            return []
        return [{"id": f.stem, "time": f.stat().st_mtime} for f in sorted(h.glob("*.json"), reverse=True)]

    def restore(self, pid: str, snap_id: str) -> Project:
        if not snap_id.isdigit():
            raise ProjectNotFound(snap_id)
        f = self.project_dir(pid) / ".history" / f"{snap_id}.json"
        if not f.exists():
            raise ProjectNotFound(snap_id)
        p = Project.model_validate_json(f.read_text("utf-8"))
        return self.save(p)


_store: ProjectStore | None = None


def get_store() -> ProjectStore:
    global _store
    if _store is None or _store.cfg is not get_config():
        _store = ProjectStore()
    return _store

"""Cola de trabajos asíncrona (render, generación IA, descargas...) con progreso en vivo."""

from __future__ import annotations

import asyncio
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

JobStatus = Literal["queued", "running", "done", "error", "cancelled"]
Pool = Literal["gpu", "cpu", "io"]


@dataclass
class Job:
    id: str
    kind: str
    title: str
    project_id: str | None = None
    pool: Pool = "cpu"
    status: JobStatus = "queued"
    progress: float = 0.0
    stage: str = ""
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    result: Any = None
    error: str | None = None
    logs: list[str] = field(default_factory=list)
    parent_id: str | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def public(self) -> dict:
        eta = None
        if self.status == "running" and self.started and self.progress > 0.02:
            elapsed = time.time() - self.started
            eta = max(0.0, elapsed / self.progress - elapsed)
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "project_id": self.project_id,
            "pool": self.pool,
            "status": self.status,
            "progress": round(self.progress, 4),
            "stage": self.stage,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "eta": eta,
            "result": self.result,
            "error": self.error,
            "logs": self.logs[-30:],
            "parent_id": self.parent_id,
        }


class JobContext:
    """Lo que recibe cada trabajo para informar de su avance y comprobar cancelación."""

    def __init__(self, manager: "JobManager", job: Job):
        self.manager = manager
        self.job = job

    @property
    def cancel_event(self) -> asyncio.Event:
        return self.job.cancel_event

    @property
    def cancelled(self) -> bool:
        return self.job.cancel_event.is_set()

    def check(self) -> None:
        if self.cancelled:
            raise asyncio.CancelledError()

    async def progress(self, value: float, stage: str | None = None) -> None:
        self.job.progress = min(1.0, max(0.0, value))
        if stage:
            self.job.stage = stage
        await self.manager.notify(self.job)

    def sub(self, start: float, end: float, prefix: str = "") -> Callable[[float, str], Awaitable[None]]:
        """Callback de progreso que mapea 0..1 al tramo [start, end] del trabajo."""

        async def cb(v: float, stage: str = "") -> None:
            await self.progress(start + (end - start) * v, f"{prefix}{stage}" if prefix or stage else None)

        return cb

    def log(self, msg: str) -> None:
        self.job.logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        if len(self.job.logs) > 300:
            del self.job.logs[:100]


JobFn = Callable[[JobContext], Awaitable[Any]]


class JobManager:
    def __init__(self, gpu_slots: int = 1, cpu_slots: int = 2, io_slots: int = 4, keep: int = 300):
        self.jobs: dict[str, Job] = {}
        self._sem = {"gpu": asyncio.Semaphore(gpu_slots), "cpu": asyncio.Semaphore(cpu_slots), "io": asyncio.Semaphore(io_slots)}
        self._tasks: dict[str, asyncio.Task] = {}
        self._listeners: set[asyncio.Queue] = set()
        self._keep = keep
        self._on_done: list[Callable[[Job], Awaitable[None] | None]] = []

    # ------------------------------------------------------------ suscripciones (WebSocket)
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._listeners.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._listeners.discard(q)

    async def notify(self, job: Job) -> None:
        data = {"type": "job", "job": job.public()}
        for q in list(self._listeners):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass

    async def broadcast(self, payload: dict) -> None:
        for q in list(self._listeners):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def on_done(self, cb: Callable[[Job], Awaitable[None] | None]) -> None:
        self._on_done.append(cb)

    # ------------------------------------------------------------ API
    def submit(
        self,
        kind: str,
        title: str,
        fn: JobFn,
        *,
        project_id: str | None = None,
        pool: Pool = "cpu",
        parent_id: str | None = None,
    ) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, title=title, project_id=project_id, pool=pool, parent_id=parent_id)
        self.jobs[job.id] = job
        self._gc()
        self._tasks[job.id] = asyncio.create_task(self._run(job, fn))
        asyncio.create_task(self.notify(job))
        return job

    async def run_inline(self, kind: str, title: str, fn: JobFn, *, project_id: str | None = None, parent: JobContext | None = None, pool: Pool = "cpu") -> Any:
        """Ejecuta un sub-trabajo y espera su resultado (usado por los pipelines)."""
        job = self.submit(kind, title, fn, project_id=project_id, pool=pool, parent_id=parent.job.id if parent else None)
        if parent is not None:
            # propagar cancelación del padre
            async def link():
                await parent.cancel_event.wait()
                job.cancel_event.set()

            linker = asyncio.create_task(link())
        try:
            await self._tasks[job.id]
        finally:
            if parent is not None:
                linker.cancel()
        if job.status == "error":
            raise RuntimeError(job.error or "Error en sub-trabajo")
        if job.status == "cancelled":
            raise asyncio.CancelledError()
        return job.result

    async def _run(self, job: Job, fn: JobFn) -> None:
        ctx = JobContext(self, job)
        try:
            async with self._sem[job.pool]:
                if job.cancel_event.is_set():
                    raise asyncio.CancelledError()
                job.status = "running"
                job.started = time.time()
                await self.notify(job)
                job.result = await fn(ctx)
                job.status = "done"
                job.progress = 1.0
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.stage = "Cancelado"
        except Exception as e:  # noqa: BLE001
            job.status = "error"
            job.error = f"{type(e).__name__}: {e}"
            ctx.log(traceback.format_exc()[-3000:])
        finally:
            job.finished = time.time()
            await self.notify(job)
            for cb in self._on_done:
                try:
                    r = cb(job)
                    if asyncio.iscoroutine(r):
                        await r
                except Exception:  # noqa: BLE001
                    pass

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def list(self, project_id: str | None = None) -> list[dict]:
        jobs = sorted(self.jobs.values(), key=lambda j: j.created, reverse=True)
        return [j.public() for j in jobs if project_id is None or j.project_id == project_id]

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.status in ("done", "error", "cancelled"):
            return False
        job.cancel_event.set()
        # cancelar hijos
        for j in self.jobs.values():
            if j.parent_id == job_id:
                j.cancel_event.set()
        task = self._tasks.get(job_id)
        if task and job.status == "queued":
            task.cancel()
        return True

    def clear_finished(self) -> int:
        ids = [k for k, j in self.jobs.items() if j.status in ("done", "error", "cancelled")]
        for k in ids:
            self.jobs.pop(k, None)
            self._tasks.pop(k, None)
        return len(ids)

    def _gc(self) -> None:
        if len(self.jobs) <= self._keep:
            return
        done = sorted((j for j in self.jobs.values() if j.status in ("done", "error", "cancelled")), key=lambda j: j.created)
        for j in done[: len(self.jobs) - self._keep]:
            self.jobs.pop(j.id, None)
            self._tasks.pop(j.id, None)


_manager: JobManager | None = None


def get_jobs() -> JobManager:
    global _manager
    if _manager is None:
        from ..config import get_config

        _manager = JobManager(gpu_slots=max(1, get_config().settings.max_parallel_jobs))
    return _manager


def reset_jobs() -> None:
    global _manager
    _manager = None

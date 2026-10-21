"""Process-wide Ray Jobs runtime: one event loop thread and a cached executor.

The httpx client inside the executor is bound to one event loop, and the
executor's stop/delete cleanups must outlive the request that started them,
so both live on a dedicated daemon loop thread rather than on uvicorn's loop
or a GPU-pool thread. Pool threads call ``run_sync``; async handlers call
``run_async``. The executor is rebuilt when the connection settings change.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import hashlib
import logging
import queue
import threading
from typing import Any, Callable, Dict, Optional, Tuple

from services.ray_jobs.client import RayJobsClient
from services.ray_jobs.executor import ExecutorRetired, RayJobResult, RayJobsExecutor, RayTask

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_loop: Optional[asyncio.AbstractEventLoop] = None
_thread: Optional[threading.Thread] = None
_executor: Optional[RayJobsExecutor] = None
_fingerprint: Optional[Tuple[Any, ...]] = None
_closed = False


class RuntimeClosed(RuntimeError):
    """The backend is shutting down; no new Ray jobs are started."""


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    with _lock:
        if _closed:
            raise RuntimeClosed("the backend is shutting down; not starting a Ray job")
        if _loop is None or not _thread or not _thread.is_alive():
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, name="ray-jobs-loop", daemon=True)
            thread.start()
            _loop, _thread = loop, thread
        return _loop


def _build(cfg, auth) -> RayJobsExecutor:
    client = RayJobsClient(cfg.dashboard_url, auth)
    return RayJobsExecutor(client, cache_dir=cfg.cache_dir or None, python=cfg.python,
                           keep_failed_jobs=cfg.keep_failed_jobs)


def reopen_for_tests() -> None:
    """Allow use after ``shutdown`` (test helper)."""
    global _closed
    with _lock:
        _closed = False


def executor_for(cfg) -> RayJobsExecutor:
    """The executor for these settings, rebuilt when the connection changes."""
    from services.ray_jobs import settings as ray_settings  # noqa: PLC0415

    global _executor, _fingerprint
    auth = ray_settings.auth()
    secret = hashlib.sha256(repr(sorted(auth.headers().items())).encode()).hexdigest()
    fingerprint = (cfg.dashboard_url, secret, cfg.cache_dir, cfg.python, cfg.keep_failed_jobs)
    loop = _ensure_loop()
    with _lock:
        if _executor is not None and fingerprint == _fingerprint:
            return _executor
        old, new = _executor, _build(cfg, auth)
        _executor, _fingerprint = new, fingerprint
        if old is not None:
            old.retired = True  # refuses new runs at once; in-flight ones finish
    if old is not None:
        asyncio.run_coroutine_threadsafe(_retire(old), loop)
    return new


async def _retire(executor: RayJobsExecutor) -> None:
    # Runs started before a settings change keep this executor's client until
    # they finish; closing it under them would fail healthy generations.
    try:
        await executor.wait_idle(timeout=6 * 3600)
    finally:
        await executor.client.aclose()


def check_cluster(cfg, timeout: float = 15.0) -> Tuple[bool, str]:
    """Blocking reachability check of the configured cluster. Never raises."""
    async def probe() -> Tuple[bool, str]:
        client = executor_for(cfg).client
        version = (await client.version()).get("ray_version")
        mode = await client.authentication_mode()
        note = " — cluster authentication is DISABLED" if mode == "disabled" else ""
        return True, f"Runs on the Ray cluster (Ray {version}){note}"

    try:
        return asyncio.run_coroutine_threadsafe(probe(), _ensure_loop()).result(timeout)
    except Exception as exc:
        return False, f"Ray cluster unreachable: {type(exc).__name__}: {exc}"


def run_async(coro) -> "asyncio.Future":
    """Await ``coro`` (which uses the runtime's client) from another loop."""
    return asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro, _ensure_loop()))


def run_sync(
    cfg,
    task: RayTask,
    *,
    timeout: Optional[float],
    idle_timeout: Optional[float] = None,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancelled: Optional[threading.Event] = None,
) -> RayJobResult:
    """Run ``task`` on the executor for ``cfg`` from a blocking thread.

    Progress events are delivered on the CALLING thread (the GPU-pool
    heartbeat is keyed by thread). Setting ``cancelled`` stops the job and
    returns once the stop has been sent (bounded).
    """
    for _ in range(3):
        try:
            return _run_sync_once(executor_for(cfg), task, timeout=timeout, idle_timeout=idle_timeout,
                                  on_event=on_event, cancelled=cancelled)
        except ExecutorRetired:
            continue  # settings changed between lookup and submit: use the new executor
    raise RuntimeError("Ray settings keep changing; try again")


def _run_sync_once(executor, task, *, timeout, idle_timeout, on_event, cancelled) -> RayJobResult:
    loop = _ensure_loop()
    events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    started = threading.Event()
    holder: Dict[str, Any] = {}

    async def runner():
        holder["task"] = asyncio.current_task()
        started.set()
        return await executor.run(task, timeout=timeout, idle_timeout=idle_timeout, on_progress=events.put_nowait)

    future = asyncio.run_coroutine_threadsafe(runner(), loop)

    def deliver() -> None:
        while on_event is not None:
            try:
                event = events.get_nowait()
            except queue.Empty:
                return
            try:
                on_event(event)
            except Exception:
                logger.debug("ray progress handler failed", exc_info=True)

    while True:
        try:
            result = future.result(timeout=0.5)
            deliver()
            return result
        except concurrent.futures.TimeoutError:
            deliver()
        except concurrent.futures.CancelledError as exc:  # runtime shut down under us
            raise RuntimeClosed("the backend is shutting down") from exc
        if cancelled is not None and cancelled.is_set():
            # Cancel the asyncio task (not the concurrent future, which would
            # report "cancelled" at once): the executor then sends the job's
            # stop before unwinding, and we wait for that.
            if started.wait(5) and "task" in holder:
                loop.call_soon_threadsafe(holder["task"].cancel)
            else:
                future.cancel()
            try:
                future.result(timeout=30)
            except BaseException:
                pass
            raise RuntimeError("Inference request was cancelled")


async def _stop_everything(executors) -> None:
    # Cancelling an in-flight run makes the executor send its job's stop;
    # cleanups (stop watchers, deletes) get a short chance to finish.
    me = asyncio.current_task()
    cleanups = {t for ex in executors for t in ex._cleanups}
    running = [t for t in asyncio.all_tasks() if t is not me and t not in cleanups]
    for task in running:
        task.cancel()
    await asyncio.gather(*running, return_exceptions=True)
    for ex in executors:
        # Bounded: a delete still in its grace is swept on the next start.
        await ex.wait_idle(timeout=5)
        await ex.client.aclose()


def shutdown(timeout: float = 15.0) -> None:
    """Wait briefly for outstanding job cleanups, then stop the loop thread."""
    global _executor, _loop, _thread, _fingerprint, _closed
    with _lock:
        executor, loop, thread = _executor, _loop, _thread
        _executor = _loop = _thread = _fingerprint = None
        _closed = True
    if loop is None:
        return
    executors = [executor] if executor is not None else []
    future = asyncio.run_coroutine_threadsafe(_stop_everything(executors), loop)
    try:
        future.result(timeout)
    except Exception:
        logger.warning("Ray job cleanups did not finish before shutdown", exc_info=True)
        future.cancel()
        with contextlib.suppress(Exception):
            future.result(2)
    loop.call_soon_threadsafe(loop.stop)
    if thread is not None:
        thread.join(timeout=5)

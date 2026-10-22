"""Run one engine's Ray job from a blocking thread (TTS, ASR and every other
model family share this): heartbeats into the guarded worker's budget,
request cancellation, and errors mapped to RuntimeError like a sidecar's."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def run_engine_job(engine_id: str, ray_cfg, task, *, timeout: float, idle_timeout: Optional[float] = None,
                   on_progress: Optional[Callable[[Dict[str, Any]], None]] = None, cancelled=None):
    from services.inference_cancellation import current_cancellation
    from services.model_manager import (
        report_generate_progress, report_model_load_activity, running_on_guarded_worker,
    )
    from services.ray_jobs import runtime
    from services.ray_jobs.client import RayJobsError
    from services.ray_jobs.executor import RayJobFailed

    from services.inference_cancellation import current_cancellation as _scope
    # Only a guarded job (the GPU pool or the Ray lane, inside its scope) has a
    # budget to extend; a raw lane caller would leave stale heartbeats (#1379).
    on_pool = running_on_guarded_worker() and _scope() is not None

    def on_event(event: dict) -> None:
        # Installs, downloads and model loads extend the execution budget
        # like a local sidecar's cold-load frames; generation heartbeats don't.
        stage = str(event.get("stage", ""))
        if on_pool and (stage == "installing" or (stage.startswith("engine:") and stage != "engine:generating")):
            report_model_load_activity()
        elif on_pool and stage in ("item_done", "engine:translating", "engine:separating"):
            # Real units of work. "engine:generating" is a timer heartbeat and
            # proves nothing about synthesis (#2435).
            report_generate_progress()
        if on_progress is not None:
            on_progress(event)

    if cancelled is None:  # the guarded job's request scope, if any
        scope = current_cancellation()
        cancelled = scope.cancelled if scope is not None else None
    try:
        return runtime.run_sync(ray_cfg, task, timeout=timeout, idle_timeout=idle_timeout, on_event=on_event,
                                cancelled=cancelled)
    except RayJobFailed as exc:
        raise RuntimeError(f"{engine_id} sidecar {exc.stage} error: {exc}") from exc
    except RayJobsError as exc:
        raise RuntimeError(f"{engine_id} Ray cluster error ({exc.kind}): {exc}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"{engine_id} Ray job timed out: {exc or f'no result within {timeout:.0f}s'}") from exc


def engine_task(engine_id: str, ray_cfg, op: str, params: dict, inputs: Optional[dict] = None,
                env: Optional[dict] = None):
    """A RayTask for ``engine_id`` with its recipe and the configured resources."""
    from services.ray_jobs.engines import install_recipe, ray_engine
    from services.ray_jobs.executor import RayTask

    engine = ray_engine(engine_id)
    return RayTask(
        op=op, engine=engine_id, params=params, inputs=inputs or {}, install=install_recipe(engine_id),
        env={**(dict(engine.env) if engine else {}), **(env or {})},
        num_gpus=ray_cfg.gpu_request(bool(engine and engine.gpu)), num_cpus=ray_cfg.num_cpus,
    )

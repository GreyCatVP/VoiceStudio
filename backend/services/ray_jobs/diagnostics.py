"""Connection test and job listing for the Ray settings page.

Each call opens its own short-lived client on the caller's event loop; the
generation path uses ``runtime`` instead. Never raises: failures come back as
``{"ok": False, "kind": ...}`` with a scrubbed message.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from services.ray_jobs.client import RayJobsClient, RayJobsError
from services.ray_jobs.executor import RayJobFailed, RayJobsExecutor, RayTask

PROBE_TIMEOUT_S = 180.0
_SUBMISSION_ID = re.compile(r"^vs-[a-z0-9-]{1,80}$")


def _scrub(message: str) -> str:
    try:
        from core.scrub import scrub_text  # noqa: PLC0415

        return scrub_text(message)[:500]
    except Exception:
        return message[:500]


def valid_submission_id(sid: str) -> bool:
    return bool(_SUBMISSION_ID.match(sid or ""))


async def test_connection(cfg, auth, *, run_probe: bool = True) -> Dict[str, Any]:
    if not cfg.dashboard_url:
        return {"ok": False, "kind": "not_configured", "message": "Set the Ray dashboard URL first."}
    started = time.monotonic()
    out: Dict[str, Any] = {"ok": False, "warnings": []}
    async with RayJobsClient(cfg.dashboard_url, auth, timeout=20) as client:
        try:
            out["ray_version"] = (await client.version()).get("ray_version")
            mode = await client.authentication_mode()
            out["authentication_mode"] = mode
            if mode == "disabled":
                # Anyone who can reach the dashboard can run code on the cluster.
                out["warnings"].append("cluster_auth_disabled")
            meta = await client.cluster_metadata()
            out["cluster_python"] = meta.get("pythonVersion")
            out["cluster_status"] = (await client.cluster_status())[:4000]
            if run_probe:
                executor = RayJobsExecutor(client, cache_dir=cfg.cache_dir or None, python=cfg.python,
                                           keep_failed_jobs=False)
                result = await executor.run(RayTask(op="probe"), timeout=PROBE_TIMEOUT_S)
                await executor.drain(timeout=30)
                out["node"] = result.result.get("node")
            out["ok"] = True
            out["kind"] = "ok"
        except RayJobsError as exc:
            out.update(kind=exc.kind, message=_scrub(str(exc)))
        except RayJobFailed as exc:
            out.update(kind="job_failed", message=_scrub(str(exc)))
        except TimeoutError:
            out.update(kind="timeout", message=f"The probe job did not finish within {PROBE_TIMEOUT_S:.0f}s.")
        except Exception as exc:  # never let a probe crash the settings page
            out.update(kind="error", message=_scrub(f"{type(exc).__name__}: {exc}"))
    out["latency_ms"] = int((time.monotonic() - started) * 1000)
    return out


def _job_row(job: Dict[str, Any]) -> Dict[str, Any]:
    meta = job.get("metadata") or {}
    return {
        "submission_id": job.get("submission_id"),
        "status": job.get("status"),
        "engine": meta.get("engine"),
        "op": meta.get("op"),
        "start_time": job.get("start_time"),
        "end_time": job.get("end_time"),
        "message": _scrub(str(job.get("message") or ""))[:300],
    }


async def list_jobs(cfg, auth, limit: int = 30) -> Dict[str, Any]:
    if not cfg.dashboard_url:
        return {"ok": False, "kind": "not_configured", "jobs": []}
    try:
        async with RayJobsClient(cfg.dashboard_url, auth, timeout=20) as client:
            jobs: List[Dict[str, Any]] = [
                j for j in await client.list_jobs()
                if (j.get("metadata") or {}).get("app") == "voicestudio"
            ]
    except RayJobsError as exc:
        return {"ok": False, "kind": exc.kind, "message": _scrub(str(exc)), "jobs": []}
    jobs.sort(key=lambda j: j.get("start_time") or 0, reverse=True)
    return {"ok": True, "jobs": [_job_row(j) for j in jobs[:limit]]}


async def stop_job(cfg, auth, submission_id: str) -> Dict[str, Any]:
    if not valid_submission_id(submission_id):
        return {"ok": False, "kind": "invalid", "message": "Not a VoiceStudio job id."}
    try:
        async with RayJobsClient(cfg.dashboard_url, auth, timeout=20) as client:
            info = await client.job_info(submission_id)
            if (info.get("metadata") or {}).get("app") != "voicestudio":
                return {"ok": False, "kind": "invalid", "message": "Not a VoiceStudio job."}
            return {"ok": True, "stopped": await client.stop_job(submission_id)}
    except RayJobsError as exc:
        return {"ok": False, "kind": exc.kind, "message": _scrub(str(exc))}

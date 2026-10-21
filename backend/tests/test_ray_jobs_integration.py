"""Ray Jobs executor against a real Ray head (opt-in).

Runs only when VS_RAY_TEST_URL points at a dashboard, e.g.

    VS_RAY_TEST_URL=http://127.0.0.1:8265 VS_RAY_TEST_TOKEN=... pytest backend/tests/test_ray_jobs_integration.py

The process-teardown check additionally needs the head on this machine.
"""
import asyncio
import os
import re
import time
from urllib.parse import urlparse

import pytest

from services.ray_jobs import RayAuth, RayJobsClient, RayJobsExecutor, RayTask

URL = os.environ.get("VS_RAY_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="VS_RAY_TEST_URL not set")


def _client():
    return RayJobsClient(URL, RayAuth(ray_token=os.environ.get("VS_RAY_TEST_TOKEN") or None))


def test_cluster_is_reachable_and_authenticated():
    async def go():
        async with _client() as c:
            return await c.version(), await c.cluster_metadata()

    version, meta = asyncio.run(go())
    assert version["ray_version"] and meta["pythonVersion"]


def test_probe_job_describes_the_node():
    async def go():
        async with _client() as c:
            return await RayJobsExecutor(c, poll_interval=0.5).run(RayTask(op="probe"), timeout=180)

    res = asyncio.run(go())
    assert res.result["node"]["python"]


def test_echo_synthesis_round_trip_through_a_real_job():
    async def go():
        async with _client() as c:
            ex = RayJobsExecutor(c, poll_interval=0.5)
            stages = []
            res = await ex.run(RayTask(op="synthesize", engine="_echo", params={"text": "hi", "sample_rate": 22050}),
                               timeout=180, on_progress=lambda e: stages.append(e["stage"]))
            jobs = {j.get("submission_id") for j in await c.list_jobs()}
            return res, stages, jobs

    res, stages, jobs = asyncio.run(go())
    assert res.result["op"] == "audio" and res.result["n_samples"] == 22050
    assert "engine_ready" in stages
    assert res.submission_id not in jobs  # deleted after success


@pytest.mark.skipif(not URL or urlparse(URL or "").hostname not in {"127.0.0.1", "localhost"},
                    reason="needs the Ray head on this machine to inspect processes")
def test_cancel_stops_the_job_and_kills_the_engine_process():
    async def go():
        async with _client() as c:
            ex = RayJobsExecutor(c, poll_interval=0.5, keep_failed_jobs=False)
            task = asyncio.create_task(ex.run(RayTask(op="_hold", engine="_echo", test_mode=True,
                                                      params={"seconds": 300})))
            pid = None
            deadline = time.monotonic() + 120
            while pid is None and time.monotonic() < deadline:
                await asyncio.sleep(1)
                for job in await c.list_jobs():
                    sid = job.get("submission_id") or ""
                    if sid.startswith("vs-echo-") and job.get("status") == "RUNNING":
                        m = re.search(r"holding sidecar pid (\d+)", await c.job_logs(sid))
                        if m:
                            pid = int(m.group(1))
            assert pid, "engine sidecar never started"
            assert os.path.exists(f"/proc/{pid}")
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await ex.drain(timeout=60)
            return pid

    pid = asyncio.run(go())
    deadline = time.monotonic() + 30
    while os.path.exists(f"/proc/{pid}") and time.monotonic() < deadline:
        time.sleep(0.5)
    assert not os.path.exists(f"/proc/{pid}"), f"engine pid {pid} survived the job stop"

"""Ray Jobs executor: log protocol, job package, worker and REST flow (model-free)."""
import asyncio
import io
import json
import os
import random
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx
import pytest

from ray_worker import vs_ray_protocol as proto
from services.ray_jobs import RayAuth, RayJobFailed, RayJobsClient, RayJobsError, RayJobsExecutor, RayTask
from services.ray_jobs.package import build_package


# -- protocol ---------------------------------------------------------------

def _log_for(result, *, prefix="", noise=True):
    lines = []
    if noise:
        lines.append("Loading model... 42%")
    out = io.StringIO()
    proto.emit_progress(out, "load", 0.5, "half")
    lines += out.getvalue().splitlines()
    lines += proto.encode_result(result)
    return "\n".join(prefix + line for line in lines)


def test_protocol_round_trip_survives_noise_and_prefixes():
    audio = bytes(range(256)) * 1000
    result = {"op": "audio", "audio_pcm_b64": proto.b64_bytes(audio), "sample_rate": 24000}
    parsed = proto.parse_log(_log_for(result, prefix="2026-10-21 05:00:00 INFO "))
    assert parsed.progress == [{"stage": "load", "message": "half", "fraction": 0.5}]
    assert proto.unb64_bytes(parsed.result["audio_pcm_b64"]) == audio


def test_protocol_large_result_spans_many_chunks():
    blob = proto.b64_bytes(random.Random(0).randbytes(3 * 1024 * 1024))  # incompressible
    lines = proto.encode_result({"x": blob})
    assert sum(1 for line in lines if " R " in line) > 10
    assert proto.parse_log("\n".join(lines)).result == {"x": blob}


def test_protocol_rejects_missing_chunk_and_bad_checksum():
    lines = proto.encode_result({"x": "y" * 200000})
    chunk_lines = [i for i, line in enumerate(lines) if f"{proto.MARK} R " in line]
    dropped = [line for i, line in enumerate(lines) if i != chunk_lines[0]]
    with pytest.raises(proto.ProtocolError, match="missing chunks"):
        proto.parse_log("\n".join(dropped))
    tampered = list(lines)
    tampered[-1] = f"{proto.MARK} RESULT_END {'0' * 64}"
    with pytest.raises(proto.ProtocolError, match="checksum"):
        proto.parse_log("\n".join(tampered))


def test_protocol_truncated_log_is_an_error_not_a_silent_none():
    lines = proto.encode_result({"x": 1})
    with pytest.raises(proto.ProtocolError, match="RESULT_END"):
        proto.parse_log("\n".join(lines[:-1]))


def test_protocol_enforces_size_limits_including_zip_bombs(monkeypatch):
    with pytest.raises(proto.ProtocolError, match="limit"):
        proto.encode_result({"x": proto.b64_bytes(bytes(range(256)) * 400)}, max_bytes=1000)
    monkeypatch.setattr(proto, "MAX_INFLATED_BYTES", 10_000)
    bomb = proto.encode_result({"x": "0" * 1_000_000})  # compresses to ~1 KB
    with pytest.raises(proto.ProtocolError, match="inflates"):
        proto.parse_log("\n".join(bomb))


def test_protocol_errors_are_collected():
    out = io.StringIO()
    proto.emit_error(out, "engine", "CUDA out of memory")
    parsed = proto.parse_log(out.getvalue())
    assert parsed.errors == [{"stage": "engine", "message": "CUDA out of memory"}]
    assert parsed.result is None


# -- package ----------------------------------------------------------------

def test_package_is_content_addressed_and_deterministic():
    task = {"v": 1, "op": "synthesize", "engine": "_echo", "params": {"text": "hi"}}
    uri1, data1, _ = build_package(task, {"ref.wav": b"RIFF"})
    uri2, data2, task_out = build_package(task, {"ref.wav": b"RIFF"})
    assert uri1 == uri2 and data1 == data2
    assert uri1.startswith("gcs://_ray_pkg_") and uri1.endswith(".zip")
    assert task_out["inputs"] == {"ref": "inputs/ref.wav"}  # param name -> file (extension kept)
    names = set(zipfile.ZipFile(io.BytesIO(data1)).namelist())
    assert {"vs_ray_worker.py", "vs_ray_protocol.py", "engines/_echo/main.py",
            "inputs/ref.wav", "task.json"} <= names
    assert build_package(task, {"ref.wav": b"other"})[0] != uri1


@pytest.mark.parametrize("name", ["../x", "a/b", "", ".."])
def test_package_rejects_unsafe_input_names(name):
    with pytest.raises(ValueError):
        build_package({"v": 1, "op": "synthesize", "engine": "_echo"}, {name: b""})


def test_package_rejects_engines_not_ported_to_ray():
    with pytest.raises(ValueError, match="cannot run on Ray"):
        build_package({"v": 1, "op": "synthesize", "engine": "indextts"}, {})


# -- worker (runs the real worker + echo sidecar as subprocesses) -----------

def _run_worker(tmp_path, task, inputs=None, *, override=None):
    _, data, _ = build_package(task, inputs or {})
    zipfile.ZipFile(io.BytesIO(data)).extractall(tmp_path)
    if override:  # simulate a task the package builder would refuse
        packed = json.loads((tmp_path / "task.json").read_text())
        (tmp_path / "task.json").write_text(json.dumps({**packed, **override}))
    proc = subprocess.run(
        [sys.executable, "vs_ray_worker.py", "--task", "task.json"],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
        env={"PATH": "/usr/bin:/bin", "VS_RAY_CACHE": str(tmp_path / "cache")},
    )
    return proc, proto.parse_log(proc.stdout)


def test_worker_runs_echo_engine_end_to_end(tmp_path):
    proc, parsed = _run_worker(tmp_path, {"v": 1, "op": "synthesize", "engine": "_echo",
                                          "params": {"text": "hello", "sample_rate": 16000}})
    assert proc.returncode == 0, proc.stderr
    assert parsed.result["op"] == "audio" and parsed.result["n_samples"] == 16000
    assert [p["stage"] for p in parsed.progress] == ["start", "engine_start", "engine_ready", "engine_done"]


def test_worker_probe_reports_node(tmp_path):
    proc, parsed = _run_worker(tmp_path, {"v": 1, "op": "probe"})
    assert proc.returncode == 0, proc.stderr
    assert parsed.result["node"]["python"].count(".") == 2


def test_worker_reports_engine_errors_and_fails_the_job(tmp_path):
    proc, parsed = _run_worker(tmp_path, {"v": 1, "op": "synthesize", "engine": "_echo"},
                               override={"engine": "nope", "entry": "engines/nope/main.py"})
    assert proc.returncode == 1 and parsed.result is None
    assert parsed.errors[-1] == {"stage": "engine", "message": "engine 'nope' is not available in this package"}


def test_worker_refuses_an_entry_outside_the_engines_dir(tmp_path):
    proc, parsed = _run_worker(tmp_path, {"v": 1, "op": "synthesize", "engine": "_echo"},
                               override={"entry": "vs_ray_worker.py"})
    assert proc.returncode == 1 and "not available" in parsed.errors[-1]["message"]


def test_worker_rejects_inputs_outside_the_package(tmp_path):
    proc, parsed = _run_worker(tmp_path, {"v": 1, "op": "synthesize", "engine": "_echo"},
                               override={"inputs": {"ref": "../../etc/passwd"}})
    assert proc.returncode == 1 and "outside the package" in parsed.errors[-1]["message"]


def test_worker_refuses_test_hooks_outside_test_mode(tmp_path):
    proc, parsed = _run_worker(tmp_path, {"v": 1, "op": "_hold", "engine": "_echo"})
    assert proc.returncode == 1 and "test-only" in parsed.errors[-1]["message"]


def test_worker_cache_lock_is_exclusive(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(proto.__file__).parent))
    import vs_ray_worker as worker

    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path))
    with worker.cache_lock("engine-x"):
        with pytest.raises(worker.TaskError, match="timed out"):
            with worker.cache_lock("engine-x", timeout=0.6):
                pass
    with worker.cache_lock("engine-x", timeout=0.6):
        pass


# -- protocol hardening (the cluster's log is untrusted) ---------------------

@pytest.mark.parametrize("line", [
    '@@VSRAY1 RESULT_BEGIN {"sha2',                       # cut mid-write
    "@@VSRAY1 RESULT_BEGIN [1]",                          # not an object
    '@@VSRAY1 RESULT_BEGIN {"sha256":"' + "a" * 64 + '","size":10,"chunks":30000000}',
    '@@VSRAY1 RESULT_BEGIN {"sha256":"zz","size":10,"chunks":1}',
    '@@VSRAY1 RESULT_BEGIN {"sha256":"' + "a" * 64 + '","size":10,"chunks":1}\n@@VSRAY1 R x y',
    '@@VSRAY1 RESULT_BEGIN {"sha256":"' + "a" * 64 + '","size":10,"chunks":1}\n@@VSRAY1 R 5 abc',
    '@@VSRAY1 RESULT_BEGIN {"sha256":"' + "a" * 64 + '","size":10,"chunks":1}\n@@VSRAY1 R 0 !!!\n@@VSRAY1 RESULT_END ' + "a" * 64,
])
def test_parse_log_turns_every_malformed_result_into_protocol_error(line):
    with pytest.raises(proto.ProtocolError):
        proto.parse_log(line)


def test_parse_events_keeps_only_well_formed_flat_events():
    log = "\n".join([
        "@@VSRAY1 PROGRESS 5",
        "@@VSRAY1 PROGRESS " + "[" * 200000,
        '@@VSRAY1 PROGRESS {"stage":"x","nested":{"a":1}}',
        "@@VSRAY1 ERROR [1]",
    ])
    parsed = proto.parse_events(log)
    assert parsed.progress == [{"stage": "x"}]
    assert parsed.errors == [{"stage": "unknown", "message": "[1]"}]


# -- executor over a mocked dashboard ---------------------------------------

class FakeDashboard:
    def __init__(self, *, final_status="SUCCEEDED", log=None, hang=False, pending_until_stop_polls=None,
                 info_failures=0, info_failure_status=502, submit_delay=0.0, log_bytes=None):
        self.final_status, self.log, self.hang = final_status, log, hang
        self.pending_until_stop_polls = pending_until_stop_polls
        self.info_failures, self.info_failure_status = info_failures, info_failure_status
        self.submit_delay, self.log_bytes = submit_delay, log_bytes
        self.calls, self.packages, self.jobs = [], set(), {}
        self.stopped = self.deleted = False
        self.polls_after_stop = 0
        self.headers = None

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        self.headers = request.headers
        path = request.url.path
        if path.startswith("/api/packages/"):
            name = path.rsplit("/", 1)[1]
            if request.method == "GET":
                return httpx.Response(200 if name in self.packages else 404)
            self.packages.add(name)
            return httpx.Response(200)
        if path == "/api/jobs/" and request.method == "POST":
            body = json.loads(request.content)
            self.jobs[body["submission_id"]] = body
            if self.submit_delay:
                await asyncio.sleep(self.submit_delay)
            return httpx.Response(200, json={"submission_id": body["submission_id"]})
        if path.endswith("/stop"):
            self.stopped = True
            return httpx.Response(200, json={"stopped": True})
        if path.endswith("/logs"):
            if self.log_bytes is not None:
                return httpx.Response(200, content=self.log_bytes)
            return httpx.Response(200, json={"logs": self.log or ""})
        if request.method == "DELETE":
            self.deleted = True
            return httpx.Response(200, json={"deleted": True})
        if path.startswith("/api/jobs/"):
            if self.info_failures:
                self.info_failures -= 1
                return httpx.Response(self.info_failure_status, text="bad gateway")
            if self.stopped:
                if self.pending_until_stop_polls is not None and self.polls_after_stop < self.pending_until_stop_polls:
                    self.polls_after_stop += 1
                    return httpx.Response(200, json={"status": "PENDING"})
                return httpx.Response(200, json={"status": "STOPPED"})
            if self.pending_until_stop_polls is not None:
                return httpx.Response(200, json={"status": "PENDING"})
            status = "RUNNING" if self.hang else self.final_status
            return httpx.Response(200, json={"status": status, "message": "driver exited"})
        return httpx.Response(404)


def _executor(fake, auth=RayAuth(), **kw):
    client = RayJobsClient("https://ray.example", auth, transport=httpx.MockTransport(fake.handler))
    opts = dict(poll_interval=0.01, progress_interval=0.0, stop_grace=1, delete_grace=0, cache_dir="/cache/vs")
    opts.update(kw)
    return RayJobsExecutor(client, **opts)


async def _drain(ex):
    while ex._cleanups:
        await asyncio.gather(*list(ex._cleanups))


def _run(ex, *args, **kw):
    async def go():
        try:
            return await ex.run(*args, **kw)
        finally:
            await _drain(ex)
    return asyncio.run(go())


def test_executor_success_uploads_once_submits_and_cleans_up():
    fake = FakeDashboard(log=_log_for({"op": "audio", "n_samples": 1}))
    ex = _executor(fake, RayAuth(ray_token="tok"))
    seen = []
    res = _run(ex, RayTask(op="synthesize", engine="_echo", num_gpus=0.25), on_progress=seen.append)
    assert res.result == {"op": "audio", "n_samples": 1}
    assert res.progress and res.progress[0]["stage"] == "load"
    (job,) = fake.jobs.values()
    # default: python3 if the image has it, else python (a KServe pod has no `python`)
    assert job["entrypoint"] == '"$(command -v python3 || command -v python)" vs_ray_worker.py --task task.json'
    assert job["entrypoint_num_gpus"] == 0.25
    assert job["runtime_env"]["working_dir"].startswith("gcs://_ray_pkg_")
    assert job["runtime_env"]["env_vars"]["VS_RAY_CACHE"] == "/cache/vs"
    assert fake.headers["authorization"] == "Bearer tok"
    assert fake.deleted
    puts = sum(1 for m, _ in fake.calls if m == "PUT")
    _run(ex, RayTask(op="synthesize", engine="_echo", num_gpus=0.25))
    assert sum(1 for m, _ in fake.calls if m == "PUT") == puts == 1


def test_executor_retries_a_transient_package_upload_failure(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _no_sleep(asyncio.sleep))
    fake = FakeDashboard(log=_log_for({"ok": 1}))
    real, failures = fake.handler, [524]

    async def flaky(request):
        if request.method == "PUT" and failures:  # a proxy timing out on a large upload
            return httpx.Response(failures.pop(), text="origin timeout")
        return await real(request)

    fake.handler = flaky
    assert _run(_executor(fake), RayTask(op="probe")).result == {"ok": 1}
    assert not failures and len(fake.jobs) == 1


def _no_sleep(real_sleep):
    async def sleep(delay, *a, **kw):
        return await real_sleep(0)
    return sleep


def test_executor_timeout_is_forwarded_to_the_worker_as_a_deadline():
    fake = FakeDashboard(log=_log_for({"ok": 1}))
    _run(_executor(fake), RayTask(op="probe"), timeout=60)
    (job,) = fake.jobs.values()
    assert float(job["runtime_env"]["env_vars"]["VS_RAY_DEADLINE"]) > 0


def test_executor_failed_job_raises_with_worker_error_and_keeps_job():
    out = io.StringIO()
    proto.emit_error(out, "engine", "CUDA out of memory")
    fake = FakeDashboard(final_status="FAILED", log=out.getvalue())
    with pytest.raises(RayJobFailed, match="CUDA out of memory") as info:
        _run(_executor(fake), RayTask(op="synthesize", engine="_echo"))
    assert info.value.status == "FAILED" and info.value.stage == "engine"
    assert not fake.deleted  # kept for debugging in the dashboard


def test_executor_killed_mid_result_reports_the_job_status_not_a_parse_error():
    lines = proto.encode_result({"x": "y"})
    fake = FakeDashboard(final_status="STOPPED", log="\n".join(lines[:-1]))
    with pytest.raises(RayJobFailed) as info:
        _run(_executor(fake), RayTask(op="synthesize", engine="_echo"))
    assert info.value.status == "STOPPED"


def test_executor_unreadable_result_of_a_succeeded_job_is_a_job_failure():
    fake = FakeDashboard(log="@@VSRAY1 RESULT_BEGIN [1]")
    with pytest.raises(RayJobFailed) as info:
        _run(_executor(fake), RayTask(op="synthesize", engine="_echo"))
    assert info.value.stage == "result"


def test_executor_rides_out_transient_dashboard_errors():
    fake = FakeDashboard(log=_log_for({"ok": 1}), info_failures=3)
    assert _run(_executor(fake), RayTask(op="probe")).result == {"ok": 1}
    assert not fake.stopped


def test_executor_stops_the_job_when_the_dashboard_keeps_failing():
    fake = FakeDashboard(hang=True, info_failures=1000, info_failure_status=500)
    with pytest.raises(RayJobsError):
        _run(_executor(fake, max_transient_errors=2, pending_watch=1), RayTask(op="probe"))
    assert fake.stopped


def test_executor_stops_the_job_on_a_non_transient_error():
    fake = FakeDashboard(hang=True, log_bytes=b"not json")
    with pytest.raises(RayJobsError):
        _run(_executor(fake), RayTask(op="probe"), on_progress=lambda e: None)
    assert fake.stopped


def test_executor_survives_a_failing_progress_callback():
    fake = FakeDashboard(log=_log_for({"ok": 1}))

    def boom(event):
        raise RuntimeError("ui went away")

    assert _run(_executor(fake), RayTask(op="probe"), on_progress=boom).result == {"ok": 1}


def test_executor_timeout_stops_the_job():
    fake = FakeDashboard(hang=True, log="")
    with pytest.raises(TimeoutError):
        _run(_executor(fake), RayTask(op="synthesize", engine="_echo"), timeout=0.1)
    assert fake.stopped


def test_executor_cancel_stops_the_job():
    fake = FakeDashboard(hang=True, log="")
    ex = _executor(fake)

    async def go():
        t = asyncio.create_task(ex.run(RayTask(op="synthesize", engine="_echo")))
        await asyncio.sleep(0.1)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        await _drain(ex)

    asyncio.run(go())
    assert fake.stopped


def test_executor_cancel_during_submit_still_stops_the_accepted_job():
    fake = FakeDashboard(hang=True, submit_delay=1.0)
    ex = _executor(fake)

    async def go():
        t = asyncio.create_task(ex.run(RayTask(op="probe")))
        await asyncio.sleep(0.3)  # POST accepted by the head, response not back yet
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        await _drain(ex)

    asyncio.run(go())
    assert fake.jobs and fake.stopped


def test_executor_keeps_watching_a_cancelled_pending_job_until_it_ends():
    fake = FakeDashboard(pending_until_stop_polls=4)
    ex = _executor(fake, keep_failed_jobs=False, stop_grace=0.1, pending_watch=30)
    with pytest.raises(TimeoutError):
        _run(ex, RayTask(op="probe"), timeout=0.2)
    assert fake.stopped and fake.polls_after_stop == 4 and fake.deleted


def test_job_logs_refuses_oversized_bodies():
    fake = FakeDashboard(log_bytes=b'{"logs":"' + b"x" * 5000 + b'"}')
    client = RayJobsClient("https://ray.example", transport=httpx.MockTransport(fake.handler))
    with pytest.raises(RayJobsError) as info:
        asyncio.run(client.job_logs("vs-1", max_bytes=1000))
    assert info.value.kind == "protocol"


@pytest.mark.parametrize("key", ["HF_TOKEN", "OMNIVOICE_DESKTOP_DRAIN_FD", "CUDA_VISIBLE_DEVICES", "AWS_SECRET_ACCESS_KEY"])
def test_executor_never_ships_secrets_or_desktop_markers(key):
    with pytest.raises(ValueError, match="refusing"):
        RayTask(op="synthesize", engine="_echo", env={key: "x"}).payload()


def test_auth_headers_cover_ray_token_and_cloudflare_access():
    h = RayAuth(ray_token="t", cf_access_client_id="id", cf_access_client_secret="s").headers()
    assert h == {"Authorization": "Bearer t", "CF-Access-Client-Id": "id", "CF-Access-Client-Secret": "s"}
    assert RayAuth(cf_access_client_id="id").headers() == {}


def test_auth_strips_pasted_newlines_and_never_echoes_bad_tokens():
    assert RayAuth(ray_token="tok\n").headers() == {"Authorization": "Bearer tok"}
    with pytest.raises(ValueError) as info:
        RayAuth(ray_token="SUPERSECRET bad")
    assert "SUPERSECRET" not in str(info.value)


def test_client_redacts_secrets_from_error_messages():
    transport = httpx.MockTransport(lambda r: httpx.Response(500, text="echo tok-123 back"))
    client = RayJobsClient("https://ray.example", RayAuth(ray_token="tok-123"), transport=transport)
    with pytest.raises(RayJobsError) as info:
        asyncio.run(client.version())
    assert "tok-123" not in str(info.value) and "[redacted]" in str(info.value)


@pytest.mark.parametrize("status,kind", [(401, "auth"), (302, "auth"), (404, "not_found"), (500, "http")])
def test_client_maps_http_failures_to_stable_kinds(status, kind):
    transport = httpx.MockTransport(lambda r: httpx.Response(status, headers={"location": "https://login"}))
    client = RayJobsClient("https://ray.example", transport=transport)
    with pytest.raises(RayJobsError) as info:
        asyncio.run(client.version())
    assert info.value.kind == kind


# -- worker hardening -------------------------------------------------------

def _worker_module():
    sys.path.insert(0, str(Path(proto.__file__).parent))
    import vs_ray_worker
    return vs_ray_worker


def test_worker_does_not_hand_cluster_credentials_to_engines(monkeypatch):
    worker = _worker_module()
    monkeypatch.setenv("RAY_AUTH_TOKEN", "x")
    monkeypatch.setenv("HF_TOKEN", "y")
    monkeypatch.setenv("VS_KEEP", "1")
    env = worker._engine_env({"env": {"ENGINE_DIR": "/e"}})
    assert "RAY_AUTH_TOKEN" not in env and "HF_TOKEN" not in env
    assert env["VS_KEEP"] == "1" and env["ENGINE_DIR"] == "/e"


def test_worker_escapes_non_utf8_engine_output():
    worker = _worker_module()
    out = io.StringIO()
    worker._pump_text(io.BytesIO(b"loading \xff weights\n"), out)
    assert out.getvalue() == "loading \\xff weights\n"
    out.getvalue().encode("utf-8")


def test_worker_refuses_to_start_an_engine_after_the_deadline(tmp_path):
    _, data, _ = build_package({"v": 1, "op": "synthesize", "engine": "_echo"}, {})
    zipfile.ZipFile(io.BytesIO(data)).extractall(tmp_path)
    proc = subprocess.run([sys.executable, "vs_ray_worker.py", "--task", "task.json"], cwd=tmp_path,
                          capture_output=True, text=True, timeout=60,
                          env={"PATH": "/usr/bin:/bin", "VS_RAY_DEADLINE": "1", "VS_RAY_LOG_DIR": str(tmp_path)})
    parsed = proto.parse_log(proc.stdout)
    assert proc.returncode == 1 and parsed.errors[-1]["stage"] == "deadline"


def test_worker_prunes_only_its_own_old_job_logs(tmp_path, monkeypatch):
    worker = _worker_module()
    monkeypatch.setenv("VS_RAY_LOG_DIR", str(tmp_path))
    old, fresh, foreign = (tmp_path / n for n in ("job-driver-vs-echo-1.log", "job-driver-vs-echo-2.log", "job-driver-other.log"))
    for p in (old, fresh, foreign):
        p.write_text("x")
    import os as _os
    _os.utime(old, (1, 1))
    _os.utime(foreign, (1, 1))
    assert worker.prune_old_job_logs() == 1
    assert not old.exists() and fresh.exists() and foreign.exists()


def test_executor_sends_the_stop_before_the_cancellation_returns():
    # The loop may end right after the caller sees CancelledError (app
    # shutdown); the stop request must already be on the wire by then.
    fake = FakeDashboard(hang=True, log="")

    async def go():
        t = asyncio.create_task(_executor(fake).run(RayTask(op="probe")))
        await asyncio.sleep(0.1)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        assert fake.stopped  # no drain()

    asyncio.run(go())



# -- real engines: install recipes, cluster-side venv install, progress frames

def test_install_recipes_come_from_the_sidecar_specs():
    from services.ray_jobs.engines import install_recipe

    assert install_recipe("_echo") is None
    st = install_recipe("supertonic3")
    assert st["install_args"] == ["supertonic==1.3.1"] and st["venv_args"] == ["--python", "3.11"]
    assert st["cuda_args"] == st["cpu_args"] == [] and st["probe_code"] == "import supertonic"
    vox = install_recipe("voxcpm2")
    assert "torch==2.11.0+cu128" in vox["cuda_args"] and "torch==2.11.0+cpu" in vox["cpu_args"]
    assert "https://download.pytorch.org/whl/cu128" in vox["cuda_args"]
    assert len(vox["key"]) == 16 and vox["key"] != st["key"]


def test_package_ships_the_engine_directory_and_entry():
    _, data, task = build_package({"v": 1, "op": "synthesize", "engine": "voxcpm2"}, {"ref_audio.wav": b"RIFF"})
    names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
    assert "engines/voxcpm2_subprocess/main.py" in names
    assert task["entry"] == "engines/voxcpm2_subprocess/main.py"
    assert task["inputs"] == {"ref_audio": "inputs/ref_audio.wav"}
    _, data, task = build_package({"v": 1, "op": "synthesize", "engine": "supertonic3"}, {})
    assert {"engines/supertonic3/sidecar.py", "engines/supertonic3/constants.py"} <= set(zipfile.ZipFile(io.BytesIO(data)).namelist())


FAKE_UV = """#!/bin/sh
echo "$@" >> "$FAKE_UV_LOG"
if [ "$1" = venv ]; then
  for a in "$@"; do case "$a" in /*) dir="$a";; esac; done
  mkdir -p "$dir/bin" && ln -sf "$(command -v python3)" "$dir/bin/python"
fi
exit 0
"""


def _fake_uv(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(FAKE_UV)
    uv.chmod(0o755)
    log = tmp_path / "uv.log"
    monkeypatch.setenv("FAKE_UV_LOG", str(log))
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    return log


def test_worker_installs_an_engine_venv_once_per_recipe(tmp_path, monkeypatch):
    worker = _worker_module()
    log = _fake_uv(tmp_path, monkeypatch)
    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path / "cache"))
    recipe = {"key": "0123456789abcdef", "venv_args": ["--python", "3.11"], "install_args": ["pkg==1"],
              "cuda_args": ["--cuda"], "cpu_args": ["--cpu"], "probe_code": "import json"}
    monkeypatch.setattr(worker, "has_nvidia", lambda: True)
    py = worker.ensure_engine_venv("eng", recipe)
    assert py.endswith("engines/eng/0123456789abcdef-cuda/.venv/bin/python")
    calls = log.read_text().splitlines()
    assert calls[0].startswith("venv --clear") and "--python 3.11" in calls[0]
    assert calls[1].startswith("pip install --python") and calls[1].endswith("pkg==1 --cuda")
    assert worker.ensure_engine_venv("eng", recipe) == py  # cached: no second install
    assert len(log.read_text().splitlines()) == 2


def test_worker_install_failure_is_reported_and_not_cached(tmp_path, monkeypatch):
    worker = _worker_module()
    _fake_uv(tmp_path, monkeypatch)
    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path / "cache"))
    recipe = {"key": "0123456789abcdef", "install_args": [], "probe_code": "raise SystemExit(3)"}
    with pytest.raises(worker.TaskError, match="exit code 3"):
        worker.ensure_engine_venv("eng", recipe)
    assert not list((tmp_path / "cache/engines/eng").glob("*/.installed"))


@pytest.mark.parametrize("recipe", [{"key": "../x"}, {"key": "zz"}])
def test_worker_rejects_malformed_recipes(tmp_path, monkeypatch, recipe):
    worker = _worker_module()
    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path))
    with pytest.raises(worker.TaskError, match="invalid install recipe"):
        worker.ensure_engine_venv("eng", recipe)


PROGRESS_ENGINE = r"""import json, struct, sys
out = sys.stdout.buffer
def send(o):
    b = json.dumps(o).encode(); out.write(struct.pack("!I", len(b)) + b); out.flush()
def recv():
    h = sys.stdin.buffer.read(4)
    if len(h) < 4: return None
    return json.loads(sys.stdin.buffer.read(struct.unpack("!I", h)[0]))
send({"op": "ready", "engine": "prog"})
while True:
    m = recv()
    if m is None or m["op"] == "shutdown": break
    send({"op": "progress", "stage": "loading", "percent": 50})
    send({"op": "progress", "stage": "generating"})
    sys.stderr.buffer.write(b"weights \xff ok\n"); sys.stderr.flush()
    send({"op": "audio", "audio_pcm_b64": "AAA=", "sample_rate": 8000})
"""


def test_worker_relays_engine_progress_frames_and_returns_the_audio(tmp_path, monkeypatch):
    from services.ray_jobs import engines, package

    eng_dir = tmp_path / "engines" / "prog"
    eng_dir.mkdir(parents=True)
    (eng_dir / "main.py").write_text(PROGRESS_ENGINE)
    monkeypatch.setattr(package, "ENGINES_DIR", tmp_path / "engines")
    monkeypatch.setitem(engines.RAY_ENGINES, "prog", engines.RayEngine("prog", "prog", ("main.py",), "main.py", gpu=False))
    work = tmp_path / "job"
    proc, parsed = _run_worker(work, {"v": 1, "op": "synthesize", "engine": "prog", "params": {"text": "x"}})
    assert proc.returncode == 0, proc.stderr
    assert parsed.result == {"op": "audio", "audio_pcm_b64": "AAA=", "sample_rate": 8000}
    stages = [p["stage"] for p in parsed.progress]
    assert "engine:loading" in stages and "engine:generating" in stages
    assert {"stage": "engine:loading", "message": "", "fraction": 0.5} in parsed.progress
    assert "weights \\xff ok" in proc.stderr


def test_retiring_an_executor_waits_for_its_in_flight_runs():
    # A settings change rebuilds the executor; runs already in flight on the
    # old one must finish on its still-open client.
    from services.ray_jobs import runtime

    fake = FakeDashboard(hang=True, log="")
    ex = _executor(fake)

    async def go():
        run = asyncio.create_task(ex.run(RayTask(op="probe")))
        await asyncio.sleep(0.1)
        retire = asyncio.create_task(runtime._retire(ex))
        await asyncio.sleep(0.2)
        assert not retire.done() and not ex.client._http.is_closed
        fake.hang = False
        fake.log = _log_for({"ok": 1})
        assert (await run).result == {"ok": 1}
        await asyncio.wait_for(retire, 5)
        assert ex.client._http.is_closed

    asyncio.run(go())



def test_worker_keeps_cpu_and_cuda_venvs_apart(tmp_path, monkeypatch):
    worker = _worker_module()
    _fake_uv(tmp_path, monkeypatch)
    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path / "cache"))
    recipe = {"key": "0123456789abcdef", "install_args": ["pkg"], "cuda_args": ["--cuda"], "cpu_args": ["--cpu"]}
    monkeypatch.setattr(worker, "has_nvidia", lambda: False)
    cpu = worker.ensure_engine_venv("eng", recipe)
    monkeypatch.setattr(worker, "has_nvidia", lambda: True)
    assert worker.ensure_engine_venv("eng", recipe) != cpu


def test_worker_install_does_not_hand_cluster_credentials_to_package_code(tmp_path, monkeypatch):
    worker = _worker_module()
    log = _fake_uv(tmp_path, monkeypatch)
    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("RAY_AUTH_TOKEN", "sekrit")
    probe = "import os; open(os.environ['FAKE_UV_LOG'], 'a').write('TOKEN=' + str('RAY_AUTH_TOKEN' in os.environ))"
    worker.ensure_engine_venv("eng", {"key": "0123456789abcdef", "install_args": [], "probe_code": probe})
    assert "TOKEN=False" in log.read_text()


def test_worker_heartbeats_while_an_install_step_runs(tmp_path, monkeypatch, capsys):
    worker = _worker_module()
    monkeypatch.setattr(worker.subprocess.Popen, "wait", _slow_wait(), raising=True)
    worker._run_logged([sys.executable, "-c", "pass"], dict(os.environ), 60, "install")
    beats = [e for e in proto.parse_events(capsys.readouterr().out).progress if e["stage"] == "installing"]
    assert beats  # the backend's silence deadline sees liveness


def _slow_wait():
    real = subprocess.Popen.wait
    calls = {"n": 0}

    def wait(self, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return real(self)

    return wait


@pytest.mark.parametrize("out,rc", [("No devices were found", 6), ("", 9)])
def test_has_nvidia_needs_a_listed_gpu(monkeypatch, tmp_path, out, rc):
    worker = _worker_module()
    smi = tmp_path / "nvidia-smi"
    smi.write_text(f"#!/bin/sh\necho '{out}'\nexit {rc}\n")
    smi.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    monkeypatch.setattr(worker, "_HAS_NVIDIA", None)
    assert worker.has_nvidia() is False


def test_probe_tolerates_unparseable_gpu_fields(monkeypatch, tmp_path):
    worker = _worker_module()
    smi = tmp_path / "nvidia-smi"
    smi.write_text('#!/bin/sh\nif [ "$1" = -L ]; then echo "GPU 0: A100 (UUID: x)"; else echo "NVIDIA A100, 81920, [N/A], [N/A]"; fi\n')
    smi.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(worker, "_HAS_NVIDIA", None)
    info = worker.probe()
    assert info["gpus"] == [{"name": "NVIDIA A100", "total_mb": 81920, "used_mb": None, "free_mb": None}]


def test_idle_timeout_is_rearmed_by_progress_and_stops_a_silent_job():
    out = io.StringIO()
    proto.emit_progress(out, "engine:loading", 0.1)
    fake = FakeDashboard(hang=True, log=out.getvalue())
    with pytest.raises(TimeoutError, match="no progress"):
        _run(_executor(fake), RayTask(op="probe"), idle_timeout=0.3)
    assert fake.stopped


def test_pending_time_does_not_count_against_the_silence_deadline():
    fake = FakeDashboard(pending_until_stop_polls=0)
    with pytest.raises(TimeoutError) as info:
        _run(_executor(fake), RayTask(op="probe"), idle_timeout=0.05, timeout=0.5)
    assert "no progress" not in str(info.value)  # the hard cap fired, not the idle deadline


def test_a_retired_executor_refuses_new_runs():
    from services.ray_jobs.executor import ExecutorRetired

    fake = FakeDashboard(log=_log_for({"ok": 1}))
    ex = _executor(fake)
    ex.retired = True
    with pytest.raises(ExecutorRetired):
        _run(ex, RayTask(op="probe"))
    assert not fake.jobs


def test_runtime_refuses_new_jobs_after_shutdown():
    from services.ray_jobs import runtime

    runtime.shutdown()
    try:
        with pytest.raises(runtime.RuntimeClosed):
            runtime._ensure_loop()
    finally:
        runtime.reopen_for_tests()


def test_sweep_deletes_old_finished_app_jobs_and_writebacks_but_keeps_failures():
    from services.ray_jobs.client import RayJobsClient

    now = __import__("time").time() * 1000
    jobs = [
        {"submission_id": "vs-a-1", "status": "SUCCEEDED", "end_time": now - 600_000, "metadata": {"app": "voicestudio"}},
        {"submission_id": "vs-a-2", "status": "FAILED", "end_time": now - 600_000, "metadata": {"app": "voicestudio"}},
        {"submission_id": "vs-a-3", "status": "FAILED", "end_time": now - 600_000, "metadata": None},  # Ray write-back
        {"submission_id": "vs-a-4", "status": "SUCCEEDED", "end_time": now - 5_000, "metadata": {"app": "voicestudio"}},
        {"submission_id": "vs-a-5", "status": "RUNNING", "end_time": None, "metadata": {"app": "voicestudio"}},
        {"submission_id": "other-1", "status": "SUCCEEDED", "end_time": now - 600_000, "metadata": {}},
    ]
    deleted = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=jobs)
        deleted.append(request.url.path.rsplit("/", 1)[1])
        return httpx.Response(200, json={"deleted": True})

    ex = RayJobsExecutor(RayJobsClient("https://ray.example", transport=httpx.MockTransport(handler)))
    assert asyncio.run(ex.sweep_finished()) == 2
    assert deleted == ["vs-a-1", "vs-a-3"]


def test_worker_batch_runs_many_items_on_one_engine_process(tmp_path, monkeypatch):
    from services.ray_jobs import engines, package

    eng_dir = tmp_path / "engines" / "prog"
    eng_dir.mkdir(parents=True)
    (eng_dir / "main.py").write_text(PROGRESS_ENGINE)
    monkeypatch.setattr(package, "ENGINES_DIR", tmp_path / "engines")
    monkeypatch.setitem(engines.RAY_ENGINES, "prog", engines.RayEngine("prog", "prog", ("main.py",), "main.py", gpu=False))
    task = {"v": 1, "op": "batch", "engine": "prog",
            "params": {"call": "synthesize", "items": [{"text": "a", "ref_audio": "@ref_audio__0"}, {"text": "b"}]}}
    proc, parsed = _run_worker(tmp_path / "job", task, {"ref_audio__0.wav": b"RIFF"})
    assert proc.returncode == 0, proc.stderr
    assert parsed.result["op"] == "batch" and len(parsed.result["results"]) == 2
    assert all(r["op"] == "audio" for r in parsed.result["results"])
    done = [p for p in parsed.progress if p["stage"] == "item_done"]
    assert [d["message"] for d in done] == ["1/2", "2/2"]
    # the engine started once for both items
    assert sum(1 for p in parsed.progress if p["stage"] == "engine_start") == 1


def test_worker_batch_refuses_unknown_input_references(tmp_path):
    task = {"v": 1, "op": "batch", "engine": "_echo",
            "params": {"call": "synthesize", "items": [{"text": "a", "ref_audio": "@nope"}]}}
    proc, parsed = _run_worker(tmp_path, task)
    assert proc.returncode == 1 and "missing input" in parsed.errors[-1]["message"]


# -- source-checkout engines: archive fetch, extras, pins, weights ------------

def _tarball(path, top, files, extra_members=()):
    import tarfile as _tf
    with _tf.open(path, "w:gz") as tf:
        for name, data in files.items():
            info = _tf.TarInfo(f"{top}/{name}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        for member in extra_members:
            tf.addfile(member)
    return path


def _local_sources(worker, monkeypatch):
    monkeypatch.setattr(worker, "_SOURCE_HOSTS", ("file://",))


def test_archive_extraction_drops_links_and_strips_the_top_dir(tmp_path, monkeypatch):
    import tarfile as _tf
    worker = _worker_module()
    _local_sources(worker, monkeypatch)
    link = _tf.TarInfo("top/data")
    link.type, link.linkname = _tf.SYMTYPE, "/etc"
    arc = _tarball(tmp_path / "a.tgz", "top", {"pkg/__init__.py": b"x=1"}, [link])
    dest = tmp_path / "dest"
    worker._download_and_extract(arc.as_uri(), dest, tmp_path / "scratch")
    assert (dest / "pkg/__init__.py").read_bytes() == b"x=1"
    assert not (dest / "data").exists()  # the absolute symlink was not extracted


def test_archive_members_cannot_escape(tmp_path, monkeypatch):
    worker = _worker_module()
    _local_sources(worker, monkeypatch)
    arc = _tarball(tmp_path / "evil.tgz", "top", {"../../escape.txt": b"no"})
    with pytest.raises(worker.TaskError, match="escapes"):
        worker._download_and_extract(arc.as_uri(), tmp_path / "dest", tmp_path / "scratch")
    assert not (tmp_path / "escape.txt").exists()


def test_sources_only_come_from_github(tmp_path):
    worker = _worker_module()
    with pytest.raises(worker.TaskError, match="refusing"):
        worker._download_and_extract("https://evil.example/x.tgz", tmp_path / "d", tmp_path)


def test_sources_and_nested_extras_are_fetched_in_order_once(tmp_path, monkeypatch):
    worker = _worker_module()
    _local_sources(worker, monkeypatch)
    main = _tarball(tmp_path / "m.tgz", "m", {"setup.py": b"", "third_party/.keep": b""})
    pyworld = _tarball(tmp_path / "p.tgz", "p", {"pyworld/__init__.py": b""})
    world = _tarball(tmp_path / "w.tgz", "w", {"src/dio.cpp": b""})
    extras = [{"path": "third_party/PyWorld", "tarball_url": pyworld.as_uri(), "revision": "r2", "required_path": "pyworld/__init__.py"},
              {"path": "third_party/PyWorld/lib/World", "tarball_url": world.as_uri(), "revision": "r3", "required_path": "src/dio.cpp"}]
    source = {"tarball_url": main.as_uri(), "revision": "r1", "required_path": "setup.py", "dirname": "M"}
    checkout = tmp_path / "src" / "M"
    worker._fetch_sources(tmp_path / "src", checkout, source, extras)
    assert (checkout / "third_party/PyWorld/pyworld/__init__.py").exists()
    assert (checkout / "third_party/PyWorld/lib/World/src/dio.cpp").exists()
    fetched = []
    monkeypatch.setattr(worker, "_download_and_extract", lambda *a: fetched.append(a))
    worker._fetch_sources(tmp_path / "src", checkout, source, extras)
    assert fetched == []  # revision markers make it a no-op


def test_dots_pin_rewrite_matches_the_local_installer(tmp_path):
    from engines.dots_tts.install import compatible_constraints
    from services.ray_jobs.engines import install_recipe

    worker = _worker_module()
    (tmp_path / "constraints").mkdir()
    (tmp_path / "constraints/recommended.txt").write_text("gradio==6.17.0\ntransformers==4.57.0  # pin\ntorch==2.7.0\n")
    recipe = install_recipe("dots-tts")
    worker._apply_pin_rewrites(tmp_path, recipe["pin_rewrites"])
    local = compatible_constraints(tmp_path / "constraints/recommended.txt").read_text()
    assert (tmp_path / "constraints/.voicestudio-compatible.txt").read_text() == local
    assert recipe["install_args"][-1].endswith("constraints/.voicestudio-compatible.txt")


def test_cosyvoice_recipe_inlines_the_app_shipped_requirements():
    from services.ray_jobs.engines import install_recipe

    recipe = install_recipe("cosyvoice")
    assert recipe["install_args"][:2] == ["-r", "{files}/cosyvoice_subprocess-requirements.txt"]
    assert "transformers" in recipe["files"]["cosyvoice_subprocess-requirements.txt"]
    assert [e["path"] for e in recipe["extra_sources"]] == [
        "third_party/Matcha-TTS", "third_party/PyWorld", "third_party/PyWorld/lib/World"]
    assert recipe["weights"]["repo_id"] == "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"
    assert recipe["env_var"] == "OMNIVOICE_COSYVOICE_DIR"


def test_source_engine_installs_editable_from_the_node_checkout(tmp_path, monkeypatch):
    worker = _worker_module()
    log = _fake_uv(tmp_path, monkeypatch)
    _local_sources(worker, monkeypatch)
    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(worker, "has_nvidia", lambda: False)
    arc = _tarball(tmp_path / "s.tgz", "repo-abc", {"pyproject.toml": b"[project]\nname='x'\n"})
    recipe = {"key": "0123456789abcdef", "install_args": ["-e", "{checkout}", "-c", "{checkout_uri}/c.txt"],
              "probe_code": "import sys; sys.path.insert(0, {checkout_repr})",
              "source": {"tarball_url": arc.as_uri(), "revision": "abc", "required_path": "pyproject.toml", "dirname": "Repo"},
              "env_var": "OMNIVOICE_X_DIR"}
    python, checkout = worker.ensure_engine("eng", recipe)
    assert checkout.endswith("engines/eng/0123456789abcdef/src/Repo")
    pip = [l for l in log.read_text().splitlines() if l.startswith("pip install")][0]
    assert f"-e {checkout}" in pip and f"file://{checkout}/c.txt" in pip


def test_weights_floor_and_marker(tmp_path):
    worker = _worker_module()
    wdir = tmp_path / "checkpoints"
    wdir.mkdir()
    weights = {"repo_id": "o/r", "revision": "rev", "subdir": "checkpoints", "config_names": ["config.yaml"]}
    assert not worker._weights_ok(tmp_path, weights)
    (wdir / "config.yaml").write_text("x")
    (wdir / "model.bin").write_bytes(b"\0" * (5 * 1024 * 1024))
    (wdir / worker._WEIGHTS_MARKER).write_text("o/r\nrev\n1\n")
    assert worker._weights_ok(tmp_path, weights)
    (wdir / worker._WEIGHTS_MARKER).write_text("o/r\nother\n1\n")
    assert not worker._weights_ok(tmp_path, weights)


@pytest.mark.parametrize("name", ["PATH", "LD_PRELOAD", "OMNIVOICE_X; rm"])
def test_recipe_env_var_must_be_an_omnivoice_dir_name(name):
    worker = _worker_module()
    with pytest.raises(worker.TaskError):
        worker._safe_env_name(name)


def test_target_installs_go_into_site_packages_for_the_matching_variant(tmp_path, monkeypatch):
    worker = _worker_module()
    log = _fake_uv(tmp_path, monkeypatch)
    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(worker, "has_nvidia", lambda: True)
    recipe = {"key": "0123456789abcdef", "install_args": ["fw"],
              "target_installs": [{"site_rel": "cudnn8_compat", "args": ["nvidia-cudnn-cu12==8.9.7.29"], "variants": ["cuda"]}]}
    worker.ensure_engine("asr", recipe)
    lines = log.read_text().splitlines()
    target = [l for l in lines if "--target" in l]
    assert target and target[0].endswith("cudnn8_compat nvidia-cudnn-cu12==8.9.7.29")
    # not on a CPU node
    log.write_text("")
    monkeypatch.setattr(worker, "has_nvidia", lambda: False)
    worker.ensure_engine("asr", recipe)
    assert not [l for l in log.read_text().splitlines() if "--target" in l]


def test_jobs_the_cluster_can_never_schedule_are_refused_up_front():
    from services.ray_jobs.client import RayJobsClient

    def handler(request):
        if request.url.path == "/nodes":
            return httpx.Response(200, json={"data": {"summary": [{"raylet": {"state": "ALIVE", "resourcesTotal": {"CPU": 4.0, "node:x": 1.0}}}]}})
        return httpx.Response(500)

    ex = RayJobsExecutor(RayJobsClient("https://ray.example", transport=httpx.MockTransport(handler)))
    with pytest.raises(RayJobFailed, match="No Ray node has 0.1 GPU") as info:
        asyncio.run(ex.run(RayTask(op="synthesize", engine="_echo", num_gpus=0.1)))
    assert info.value.stage == "placement"


def test_a_configured_cluster_python_is_used_verbatim():
    fake = FakeDashboard(log=_log_for({"ok": 1}))
    _run(_executor(fake, python="/opt/conda/bin/python3"), RayTask(op="probe"))
    (job,) = fake.jobs.values()
    assert job["entrypoint"] == "/opt/conda/bin/python3 vs_ray_worker.py --task task.json"


def test_run_sync_reraises_a_job_timeout_instead_of_spinning():
    # concurrent.futures.TimeoutError IS TimeoutError on 3.11+: a job's own
    # timeout used to look like "not done yet" and loop forever.
    from services.ray_jobs import runtime

    class TimingOut:
        retired = False

        async def run(self, task, **kw):
            raise TimeoutError("Ray job vs-x made no progress for 600s")

    import threading as _t
    result = {}

    def call():
        try:
            runtime._run_sync_once(TimingOut(), RayTask(op="probe"), timeout=1, idle_timeout=None,
                                   on_event=None, cancelled=None)
        except TimeoutError as exc:
            result["exc"] = exc

    th = _t.Thread(target=call, daemon=True)
    th.start()
    th.join(10)
    assert not th.is_alive() and "no progress" in str(result["exc"])


def test_worker_batch_stops_before_the_result_cap_and_says_so(tmp_path, monkeypatch):
    worker = _worker_module()
    monkeypatch.setattr(worker, "BATCH_RESULT_BUDGET", 10)

    class Engine:
        class proc:
            @staticmethod
            def poll():
                return None

        def call(self, msg):
            return {"op": "audio", "audio_pcm_b64": "A" * 40}

    out = worker._run_batch(Engine(), {"call": "synthesize", "items": [{"text": "a"}, {"text": "b"}, {"text": "c"}]}, {})
    assert out["truncated"] is True and len(out["results"]) == 1


def test_a_failed_rebuild_never_keeps_an_old_installed_marker(tmp_path, monkeypatch):
    worker = _worker_module()
    _fake_uv(tmp_path, monkeypatch)
    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(worker, "has_nvidia", lambda: False)
    root = tmp_path / "cache/engines/eng/0123456789abcdef-cpu"
    root.mkdir(parents=True)
    (root / ".installed").write_text("old")  # python missing -> rebuild
    with pytest.raises(worker.TaskError):
        worker.ensure_engine("eng", {"key": "0123456789abcdef", "install_args": [], "probe_code": "raise SystemExit(2)"})
    assert not (root / ".installed").exists()


def test_install_env_points_hugging_face_at_the_cluster_cache(monkeypatch, tmp_path):
    worker = _worker_module()
    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path))
    monkeypatch.setenv("RAY_AUTH_TOKEN", "x")
    env = worker._install_env()
    assert env["HF_HOME"] == str(tmp_path / "hf") and env["HF_HUB_DISABLE_IMPLICIT_TOKEN"] == "1"
    assert "RAY_AUTH_TOKEN" not in env


def test_placement_checks_single_nodes_not_cluster_totals():
    from services.ray_jobs.client import RayJobsClient

    nodes = [{"raylet": {"state": "ALIVE", "resourcesTotal": {"CPU": 4.0, "GPU": 1.0}}}] * 2

    def handler(request):
        if request.url.path == "/nodes":
            return httpx.Response(200, json={"data": {"summary": nodes}})
        return httpx.Response(500)

    ex = RayJobsExecutor(RayJobsClient("https://ray.example", transport=httpx.MockTransport(handler)))
    with pytest.raises(RayJobFailed, match="No Ray node"):
        asyncio.run(ex._check_placement(RayTask(op="x", engine="voxcpm2", num_cpus=6.0, num_gpus=2.0)))
    asyncio.run(ex._check_placement(RayTask(op="x", engine="voxcpm2", num_cpus=4.0, num_gpus=1.0)))  # fits one node


@pytest.mark.parametrize("payload", [{"data": {"summary": []}}, {"data": None}, {"weird": 1}])
def test_placement_is_skipped_when_resources_are_unknown(payload):
    from services.ray_jobs.client import RayJobsClient

    ex = RayJobsExecutor(RayJobsClient("https://ray.example", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json=payload))))
    asyncio.run(ex._check_placement(RayTask(op="x", engine="voxcpm2", num_gpus=1.0)))  # no refusal


def test_worker_accepts_the_new_model_ops():
    worker = _worker_module()
    assert {"translate", "diarize", "separate"} <= worker.ENGINE_OPS


def test_batch_budget_counts_every_field_not_only_audio(monkeypatch):
    worker = _worker_module()
    monkeypatch.setattr(worker, "BATCH_RESULT_BUDGET", 50)

    class Engine:
        class proc:
            @staticmethod
            def poll():
                return None

        def call(self, msg):
            return {"op": "separated", "vocals_b64": "V" * 40, "bed_b64": "B" * 40}

    out = worker._run_batch(Engine(), {"call": "separate", "items": [{"audio_path": "a"}, {"audio_path": "b"}]}, {})
    assert out["truncated"] is True and len(out["results"]) == 1


def test_install_env_prefers_uv_managed_python(monkeypatch, tmp_path):
    worker = _worker_module()
    monkeypatch.setenv("VS_RAY_CACHE", str(tmp_path))
    assert worker._install_env()["UV_PYTHON_PREFERENCE"] == "only-managed"
    monkeypatch.setenv("VS_RAY_PYTHON_PREFERENCE", "managed")  # a cluster without internet to python-build-standalone
    assert worker._install_env()["UV_PYTHON_PREFERENCE"] == "managed"

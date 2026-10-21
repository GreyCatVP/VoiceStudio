"""Minimal async client for the Ray dashboard Jobs REST API.

VoiceStudio does not depend on the ``ray`` package: the backend runs Python
3.11 while a cluster may run another version, and Ray Client requires them to
match. The dashboard's HTTPS API has no such constraint, so this module talks
to it directly with httpx (same endpoints as ``ray.job_submission``).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

import httpx

TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "STOPPED"})
# A legitimate log holds at most one result (~4/3 of MAX_RESULT_BYTES as
# base64) plus engine chatter; anything bigger is refused, not buffered.
MAX_LOG_BYTES = 80 * 1024 * 1024
_PRINTABLE = re.compile(r"^[\x21-\x7e]+$")


class RayJobsError(RuntimeError):
    """A dashboard request failed. ``kind`` is stable for UI mapping."""

    def __init__(self, kind: str, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.kind = kind  # auth | network | not_found | http | protocol
        self.status = status


@dataclass(frozen=True)
class RayAuth:
    """How to authenticate to the dashboard (any combination may be set)."""

    ray_token: Optional[str] = None  # RAY_AUTH_MODE=token on the head
    cf_access_client_id: Optional[str] = None  # Cloudflare Access service token
    cf_access_client_secret: Optional[str] = None

    def __post_init__(self) -> None:
        for field_name in ("ray_token", "cf_access_client_id", "cf_access_client_secret"):
            value = getattr(self, field_name)
            if value is None:
                continue
            value = value.strip()
            # Never echo the value: a pasted token may be a real secret.
            if value and not _PRINTABLE.match(value):
                raise ValueError(f"{field_name} contains characters that cannot be sent in an HTTP header")
            object.__setattr__(self, field_name, value or None)

    def secrets(self) -> tuple:
        return tuple(v for v in (self.ray_token, self.cf_access_client_secret) if v)

    def headers(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if self.ray_token:
            out["Authorization"] = f"Bearer {self.ray_token}"
        if self.cf_access_client_id and self.cf_access_client_secret:
            out["CF-Access-Client-Id"] = self.cf_access_client_id
            out["CF-Access-Client-Secret"] = self.cf_access_client_secret
        return out


class RayJobsClient:
    def __init__(
        self,
        base_url: str,
        auth: RayAuth = RayAuth(),
        *,
        timeout: float = 30.0,
        upload_timeout: float = 600.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._secrets = auth.secrets()
        self._upload_timeout = upload_timeout
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers=auth.headers(),
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "RayJobsClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def _request(self, method: str, path: str, *, ok=(200,), **kw: Any) -> httpx.Response:
        try:
            r = await self._http.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise RayJobsError("network", self._redact(f"{method} {path}: {type(exc).__name__}: {exc}")) from exc
        if r.status_code in ok:
            return r
        self._raise_for(r, method, path)

    def _raise_for(self, r: httpx.Response, method: str, path: str) -> None:
        if r.status_code in (401, 403):
            raise RayJobsError("auth", f"{method} {path}: unauthorized ({r.status_code})", r.status_code)
        if 300 <= r.status_code < 400:
            # Cloudflare Access answers an unauthenticated API call with a
            # redirect to its login page.
            raise RayJobsError("auth", f"{method} {path}: redirected to {r.headers.get('location')!r}", r.status_code)
        if r.status_code == 404:
            raise RayJobsError("not_found", f"{method} {path}: not found", 404)
        raise RayJobsError("http", self._redact(f"{method} {path}: HTTP {r.status_code}: {r.text[:300]}"), r.status_code)

    def _redact(self, message: str) -> str:
        for secret in self._secrets:
            message = message.replace(secret, "[redacted]")
        return message

    @staticmethod
    def _json(r: httpx.Response) -> Any:
        try:
            return r.json()
        except ValueError as exc:
            raise RayJobsError("protocol", f"expected JSON from {r.request.url.path}, got {r.text[:120]!r}") from exc

    # -- cluster -----------------------------------------------------------
    async def version(self) -> Dict[str, Any]:
        return self._json(await self._request("GET", "/api/version"))

    async def authentication_mode(self) -> str:
        return str(self._json(await self._request("GET", "/api/authentication_mode")).get("authentication_mode"))

    async def cluster_metadata(self) -> Dict[str, Any]:
        return self._json(await self._request("GET", "/api/v0/cluster_metadata")).get("data", {})

    async def cluster_status(self) -> str:
        data = self._json(await self._request("GET", "/api/cluster_status", params={"format": "1"}))
        return str(data.get("data", {}).get("clusterStatus", ""))

    async def node_resources(self) -> list:
        """Each alive node's total logical resources ({"CPU": .., "GPU": ..}).

        Malformed entries are skipped; an empty list means "unknown"."""
        data = self._json(await self._request("GET", "/nodes", params={"view": "summary"}))
        nodes = (data.get("data") or {}).get("summary") if isinstance(data, dict) and isinstance(data.get("data"), dict) else None
        out = []
        for node in nodes if isinstance(nodes, list) else []:
            raylet = node.get("raylet") if isinstance(node, dict) else None
            totals = raylet.get("resourcesTotal") if isinstance(raylet, dict) else None
            if not isinstance(totals, dict) or raylet.get("state") not in (None, "ALIVE"):
                continue
            out.append({str(k): float(v) for k, v in totals.items()
                        if isinstance(v, (int, float)) and not str(k).startswith("node:")})
        return out

    # -- packages ----------------------------------------------------------
    @staticmethod
    def _package_path(uri: str) -> str:
        protocol, sep, name = uri.partition("://")
        if not sep or protocol != "gcs" or "/" in name:
            raise ValueError(f"unsupported package URI {uri!r}")
        return f"/api/packages/{protocol}/{name}"

    async def package_exists(self, uri: str) -> bool:
        r = await self._request("GET", self._package_path(uri), ok=(200, 404))
        return r.status_code == 200

    async def upload_package(self, uri: str, data: bytes) -> None:
        await self._request("PUT", self._package_path(uri), content=data, timeout=self._upload_timeout)

    # -- jobs --------------------------------------------------------------
    async def submit_job(
        self,
        *,
        entrypoint: str,
        submission_id: str,
        runtime_env: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, str]] = None,
        entrypoint_num_cpus: Optional[float] = None,
        entrypoint_num_gpus: Optional[float] = None,
        entrypoint_memory: Optional[int] = None,
    ) -> str:
        body: Dict[str, Any] = {"entrypoint": entrypoint, "submission_id": submission_id}
        if runtime_env:
            body["runtime_env"] = dict(runtime_env)
        if metadata:
            body["metadata"] = dict(metadata)
        if entrypoint_num_cpus is not None:
            body["entrypoint_num_cpus"] = entrypoint_num_cpus
        if entrypoint_num_gpus is not None:
            body["entrypoint_num_gpus"] = entrypoint_num_gpus
        if entrypoint_memory is not None:
            body["entrypoint_memory"] = entrypoint_memory
        data = self._json(await self._request("POST", "/api/jobs/", json=body))
        return str(data.get("submission_id") or data.get("job_id") or submission_id)

    async def job_info(self, submission_id: str) -> Dict[str, Any]:
        return self._json(await self._request("GET", f"/api/jobs/{submission_id}"))

    async def job_logs(self, submission_id: str, max_bytes: int = MAX_LOG_BYTES) -> str:
        """The job's full driver log, refusing bodies over ``max_bytes``."""
        path = f"/api/jobs/{submission_id}/logs"
        try:
            async with self._http.stream("GET", path) as r:
                if r.status_code != 200:
                    await r.aread()
                    self._raise_for(r, "GET", path)
                body = bytearray()
                async for part in r.aiter_bytes():
                    body.extend(part)
                    if len(body) > max_bytes:
                        raise RayJobsError("protocol", f"GET {path}: log exceeds {max_bytes} bytes")
        except httpx.HTTPError as exc:
            raise RayJobsError("network", self._redact(f"GET {path}: {type(exc).__name__}: {exc}")) from exc
        try:
            logs = json.loads(bytes(body)).get("logs", "")
        except (ValueError, AttributeError) as exc:
            raise RayJobsError("protocol", f"GET {path}: response is not a logs object") from exc
        return logs if isinstance(logs, str) else ""

    async def stop_job(self, submission_id: str) -> bool:
        data = self._json(await self._request("POST", f"/api/jobs/{submission_id}/stop"))
        return bool(data.get("stopped"))

    async def delete_job(self, submission_id: str) -> bool:
        data = self._json(await self._request("DELETE", f"/api/jobs/{submission_id}"))
        return bool(data.get("deleted"))

    async def list_jobs(self) -> list:
        return list(self._json(await self._request("GET", "/api/jobs/")))

# Ray cluster execution (opt-in)

VoiceStudio can run selected TTS engines on a [Ray](https://www.ray.io/)
cluster instead of this machine. Each generation step is submitted as **one
Ray job** through the cluster dashboard's HTTPS Jobs API; when the job ends,
its process and the engine inside it exit, so the GPU memory is returned to
the cluster after every run. Nothing stays loaded between runs.

It is **off by default**. Engines you do not select keep running locally.

## Requirements

- A Ray head (tested with Ray 2.59) whose dashboard is reachable over HTTPS
  (plain HTTP is accepted only for `localhost`/loopback).
- **Authentication on the cluster.** A dashboard without authentication lets
  anyone who can reach it run code on the cluster. Enable one of:
  - Ray token authentication (`RAY_AUTH_MODE=token` on the head), and paste the
    token into Settings → Ray cluster; or
  - Cloudflare Access in front of the dashboard, with a service token (client
    ID + secret) entered in the same page.

  The connection test warns when the cluster reports authentication as
  disabled.
- Cluster nodes need internet access to PyPI, `download.pytorch.org` (CUDA
  wheels), GitHub (to fetch `uv` if it is not installed) and the Hugging Face
  endpoint (weights).
- The VoiceStudio backend does **not** need the `ray` package, and its Python
  version does not need to match the cluster's.

## Setup

1. Settings → **Ray cluster**.
2. Enter the dashboard URL (e.g. `https://ray.example.com`) and the token or
   Cloudflare Access credentials. Save.
3. **Test connection**. This submits a small probe job and shows the Ray and
   Python versions, the node's GPUs with free memory, and the cache disk.
4. Tick the engines to run on Ray, enable Ray execution, and save.

Available engines: **Supertonic-3** (CPU) and **VoxCPM2** (GPU). Engines that
need a source checkout or import backend code are not available on Ray yet.

## What happens on the cluster

- On first use after a node starts, the job installs the engine into a cache
  directory (default `~/.cache/voicestudio-ray` on the node; configurable):
  a `uv`-built virtual environment pinned exactly like the local installer,
  plus the model weights in a Hugging Face cache. A file lock keeps parallel
  jobs from installing the same engine twice. This first run can take many
  minutes (a CUDA PyTorch environment is several GB); later runs reuse it.
- If the node restarts with an ephemeral disk, the next run installs again.
- GPU engines request a fraction of a GPU (**GPU share per job**, default
  0.1). Ray treats this as bookkeeping, not a memory limit: if other software
  already uses the GPU, lower concurrency accordingly.
- Results (audio) come back through the job's log, checksummed and limited to
  50 MB per job. VoiceStudio deletes finished jobs; the worker prunes its old
  job logs (which contain result audio) after 6 hours.
- Cancelling a generation, or a deadline expiring, stops the job — including
  a job still waiting in the cluster's queue.

## Privacy

Text, reference audio and generated audio for Ray-routed engines are sent to
the cluster you configure. Your Hugging Face token and other secrets are never
sent to the cluster or passed to engine code there; engines whose weights are
gated behind a Hugging Face login are therefore not offered on Ray.

## Environment overrides

| Variable | Effect |
|---|---|
| `OMNIVOICE_RAY_DASHBOARD_URL` | Pins the dashboard URL (the field becomes read-only). |
| `OMNIVOICE_RAY_AUTH_TOKEN` | Pins the Ray auth token. |

## Troubleshooting

- **auth** — the token or Cloudflare Access credentials were rejected.
- **network** — the dashboard is unreachable from this machine.
- **job_failed** — the job ran but failed; the message carries the engine's
  error. Failed jobs are kept in the Ray dashboard for inspection unless
  "Keep failed jobs" is off.
- **timeout** — the probe job did not start in time, usually because the
  cluster has no free CPU for it.

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

Available engines:

- **Text to speech:** Supertonic-3 (CPU), VoxCPM2, MOSS-TTS-Nano, IndexTTS2,
  CosyVoice, Confucius4-TTS, MOSS-TTS v1.5 and dots.tts. Engines that install
  from a source checkout fetch the pinned GitHub archive on the cluster
  (CosyVoice and dots.tts build native code, so the node needs a C/C++
  toolchain; dots.tts also needs OpenFst headers).
- **Speech recognition:** Faster-Whisper (crash-isolated subprocess), used by
  dubbing. Select it as the ASR engine and choose a Hugging Face model, not a
  local folder: the cluster downloads the model on first use.

The in-process VoiceStudio (OmniVoice) engine and models that live inside the
backend (diarization, NLLB translation, source separation) still run locally.

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
  already uses the GPU, lower concurrency accordingly. A share of **0** runs
  GPU engines on CPU (for CPU-only clusters).
- Before submitting, VoiceStudio checks that some node can hold the job's
  GPU/CPU request and explains when none can (Ray would otherwise leave the
  job queued). On an autoscaling cluster whose GPU nodes start on demand, set
  `OMNIVOICE_RAY_SKIP_PLACEMENT_CHECK=1`.
- Long texts, audiobook chapters and dub segments are rendered many
  utterances per job (one model load); dubbing transcription sends pieces of
  up to 30 minutes at 16 kHz.
- The job runs `python3` (or `python` when that is all the image has); set
  **Cluster Python** to use a specific interpreter.
- Results (audio) come back through the job's log, checksummed and limited to
  50 MB per job. VoiceStudio deletes finished jobs; the worker prunes its old
  job logs (which contain result audio) after 6 hours. Finished jobs that a
  shutdown left behind are deleted by a later run.
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

# Remote GPU execution: Ray cluster or Modal (opt-in)

VoiceStudio can run selected engines on a remote GPU instead of this machine,
using one of two providers (Settings → **Remote GPU**):

- **Ray cluster** — your own [Ray](https://www.ray.io/) cluster (below).
- **Modal** — serverless GPUs in your own [Modal](https://modal.com) account
  (see [Modal](#modal)).

When no usable local GPU is found, the **GPU acceleration** check (first-run
setup and Settings → Performance → System check) offers the three choices:
keep using the CPU, set up a Ray cluster, or set up Modal.

## Ray cluster

VoiceStudio can run selected engines on a [Ray](https://www.ray.io/)
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
    token into Settings → Remote GPU; or
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

1. Settings → **Remote GPU**, provider **Ray cluster**.
2. Enter the dashboard URL (e.g. `https://ray.example.com`) and the token or
   Cloudflare Access credentials. Save.
3. **Test connection**. This submits a small probe job and shows the Ray and
   Python versions, the node's GPUs with free memory, and the cache disk.
4. Tick the engines to run on Ray, enable Ray execution, and save.

Available engines:

- **Text to speech:** VoiceStudio (OmniVoice), Supertonic-3 (CPU), VoxCPM2,
  MOSS-TTS-Nano, IndexTTS2, CosyVoice, Confucius4-TTS, MOSS-TTS v1.5,
  dots.tts and F5-TTS-THAI. Engines that install from a source checkout fetch
  the pinned GitHub archive on the cluster (CosyVoice and dots.tts build native
  code, so the node needs a C/C++ toolchain). F5-TTS-THAI (`f5-tts-thai`, about
  1.4 GB of weights) speaks Thai and English in a voice cloned from 2–8 s of
  reference audio; it has no local path, so it is available only while this
  engine is ticked ([details](engines/f5-tts-thai.md)).
- **Speech recognition:** Faster-Whisper (crash-isolated subprocess), used by
  dubbing. Select it as the ASR engine and choose a Hugging Face model, not a
  local folder. Word timings are refined on this machine with the same wav2vec2
  forced alignment WhisperX uses (`OMNIVOICE_RAY_ASR_ALIGN=0` turns it off).
  For Thai, choose **Typhoon Whisper Turbo** (Thai only; about 5% character
  error rate on Thai TV speech against about 13% for large-v3). It has no
  CTranslate2 build on Hugging Face, so the first job converts it once into
  the cluster cache (about a minute, another 1.6 GB) and later jobs load the
  converted copy. Thai word timings come back as whole words (PyThaiNLP word
  boundaries), for either model.
- **Translation:** NLLB or Typhoon Translate, when it is the dubbing
  translation provider. One job translates the whole dub. Typhoon Translate
  1.5 (`typhoon-translate`, about 8 GB of weights) translates English to Thai
  and Thai to English only, and turns the dub glossary into its translation
  rules; it has no local path, so the **Typhoon Translate** provider is
  available only while this engine is ticked.
- **Speaker diarization:** pyannote 3.1, in dubbing. The model is gated on
  Hugging Face, so the cluster never downloads it: each job carries the model
  files you installed (and accepted) on this machine, about 32 MB. Your
  Hugging Face token never leaves this computer. The recording is sent whole
  (speaker identity is global), as 16 kHz FLAC; only a recording too long for
  one job package (well over an hour) is sent as Opus instead.
- **Source separation:** Demucs (htdemucs), when a dub video is imported and
  for microphone clean-up. The track is processed in lossless two-minute
  windows with overlapping context, so the stems join without seams.

The audio.cpp Sortformer diarizer (a native binary), live dictation, voice
activity detection and the AudioSeal watermark stay on this machine: they are
small, CPU-bound or latency-critical.

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
  **Cluster Python** to use a specific interpreter. Engine environments use
  `uv`'s own Python builds (they include the headers native packages need),
  downloaded once into the cluster cache.
- Results (audio) come back through the job's log, checksummed and limited to
  50 MB per job. VoiceStudio deletes finished jobs; the worker prunes its old
  job logs (which contain result audio) after 6 hours. Finished jobs that a
  shutdown left behind are deleted by a later run.
- Cancelling a generation, or a deadline expiring, stops the job — including
  a job still waiting in the cluster's queue.

## Modal

With the **Modal** provider every run is one
[Modal Sandbox](https://modal.com/docs/guide/sandbox): a container with the
GPU type you choose, which runs the same job package and worker as a Ray job
and is terminated when the run ends — on success, failure, cancellation, a
deadline, or if VoiceStudio exits — so the GPU is released and billing stops.
Modal bills per second of container time on your account.

Setup:

1. Create a token in your Modal account (`modal token new`, or modal.com →
   Settings → API tokens).
2. Settings → **Remote GPU** → provider **Modal**; paste the token id
   (`ak-…`) and secret (`as-…`), pick a GPU type (default L4; "CPU only" runs
   GPU engines on CPU), save.
3. **Test connection** checks the token and starts one short sandbox on that
   GPU type, which reports the GPU and its memory.
4. Tick the engines to run remotely, enable remote execution, and save.

Details:

- The backend does not depend on the Modal SDK: on first use `uv` installs a
  pinned `modal` package and Python 3.12 into its cache, and a small driver
  (`backend/modal_driver/vs_modal_driver.py`) talks to Modal. The token is
  passed only to that driver process; it never enters the sandbox.
- Each engine runs in its own image: Debian with Python 3.12, build tools,
  ffmpeg, and that engine's environment, installed at image build time. Modal
  builds it on the engine's first run (a few minutes) and caches it; it is
  rebuilt only when the engine's install recipe or VoiceStudio's worker
  changes. An image build failure is detailed in the Modal dashboard's logs.
- Model weights downloaded at run time persist on a Modal Volume (default
  `voicestudio-cache`, a v2 volume, in an app named `voicestudio`). Changing
  the volume name starts from an empty cache.
- The same engines as on Ray are available, with the same 50 MB result limit
  per job. There is no job list in VoiceStudio for Modal; see the app's
  sandboxes in the Modal dashboard.

## Privacy

Text, reference audio and generated audio for remotely run engines are sent to
the Ray cluster you configure, or to Modal's cloud under your Modal account; for Ray-routed dubbing steps that includes the
source recording, its transcript and translations, and (for diarization) your
installed pyannote model files. Your Hugging Face token and other secrets are never
sent to the cluster or passed to engine code there; engines whose weights are
gated behind a Hugging Face login are therefore not offered on Ray.

## Environment overrides

| Variable | Effect |
|---|---|
| `OMNIVOICE_RAY_DASHBOARD_URL` | Pins the dashboard URL (the field becomes read-only). |
| `OMNIVOICE_RAY_AUTH_TOKEN` | Pins the Ray auth token. |
| `OMNIVOICE_MODAL_TOKEN_ID` + `OMNIVOICE_MODAL_TOKEN_SECRET` | Pin the Modal token (both must be set). |

## Troubleshooting

- **auth** — the token or Cloudflare Access credentials were rejected.
- **network** — the dashboard is unreachable from this machine.
- **job_failed** — the job ran but failed; the message carries the engine's
  error. Failed jobs are kept in the Ray dashboard for inspection unless
  "Keep failed jobs" is off.
- **timeout** — the probe job did not start in time, usually because the
  cluster has no free CPU for it.
- **auth** (Modal) — the token id or secret is wrong or was revoked.
- **job_failed** (Modal) — often a GPU type your Modal workspace cannot use, or
  an engine install error; the message carries the detail.
- **uv was not found** (Modal) — the Modal SDK is installed with `uv`; the
  desktop app ships it, source installs need `uv` on `PATH`.

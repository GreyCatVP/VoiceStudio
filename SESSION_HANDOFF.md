# Session handoff (this PC)

## Sidecar memory cap (2026-10-26)

The VoxCPM2 sidecar grew to 23 GB committed and filled P1's commit limit (other apps
failed with 0xc000012d). Commit a242eeb38 adds `OMNIVOICE_SIDECAR_MAX_MEMORY_MB`: the
reaper (every 30 s) recycles a sidecar at or above the cap, only between requests;
the next request respawns it. `Launch-VoiceStudio-LAN.ps1` (P1-local, untracked) sets
16384. It takes effect the next time the backend starts (logon task / crash restart);
the running backend was not restarted. Check: the log line "recycling sidecar using".
Tests: `tests/backend/services/test_sidecar_memory_cap.py` (runtime venv has no pytest;
use `pip install --target <dir> pytest` + `PYTHONPATH`).

## GPU 1 = voice (2026-10-16)

This PC has two NVIDIA cards (PCI-bus order): GPU 0 = RTX 5080 (ComfyUI, LoRA
training, big LLM), GPU 1 = RTX 5060 Ti 16 GB (always-on voice). VoiceStudio runs
on GPU 1.

- `Launch-VoiceStudio-Custom.bat` sets `CUDA_DEVICE_ORDER=PCI_BUS_ID` and
  `CUDA_VISIBLE_DEVICES=%VS_GPU%` (default `1`). Back to the 5080: `set VS_GPU=0`
  before running it. `set VS_GPU=auto` leaves the choice to the app setting below.
- The app's own Settings → CUDA adapter is also saved as the 5060 Ti (GPU UUID), so
  the installed app and a backend started by NeoGen land on GPU 1 too. Undo: set it
  back to Auto in Settings. An env var from the launcher wins over the setting.
- NeoGen (port 8741) can start the VoiceStudio backend itself; quitting VoiceStudio
  from the tray does not stop that backend.
- Verified 2026-10-16: torch 2.8.0+cu128 sees the 5060 Ti (sm_120); `/health` reports
  `cuda (NVIDIA GeForce RTX 5060 Ti)`; a Hindi voxcpm2 test (Hindi Documentary
  Narrator, 4.5 s of audio) took about 51 s cold, including the model load; VoiceStudio
  uses about 8.7 GB VRAM on GPU 1 with voxcpm2 loaded.

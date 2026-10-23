@echo off
title VoiceStudio (custom build)
rem Customised VoiceStudio: this folder's UI *and* backend, run with the Python
rem runtime the installed app already set up (no new downloads). Same voices,
rem history and models as the installed app.

if "%VS_PORT%"=="" set "VS_PORT=3900"
set "VS_PY=%APPDATA%\VoiceStudio\runtime\project\.venv\Scripts\python.exe"

if not exist "%VS_PY%" (
  echo VoiceStudio runtime not found. Install and open VoiceStudio once, then try again.
  pause
  exit /b 1
)

powershell -NoProfile -Command "try { Invoke-WebRequest http://127.0.0.1:%VS_PORT%/health -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 (
  echo The installed VoiceStudio is still running on port %VS_PORT%.
  echo Quit it ^(tray icon ^> Quit^), then run this launcher again.
  pause
  exit /b 1
)

rem GPU: since 2026-10-24 this PC (P1) has one NVIDIA card, the RTX 5060 Ti = GPU 0
rem (always-on voice). The RTX 5080 moved to the Ubuntu server P2 "deep" (ComfyUI).
rem Other index: "set VS_GPU=1" before running this file (or edit the line below).
rem "set VS_GPU=auto" leaves the choice to Settings -> CUDA adapter in the app.
if "%VS_GPU%"=="" set "VS_GPU=0"
if /i not "%VS_GPU%"=="auto" (
  set "CUDA_DEVICE_ORDER=PCI_BUS_ID"
  set "CUDA_VISIBLE_DEVICES=%VS_GPU%"
)

rem P1 (Core Ultra 5 245K): torch 2.11 in the VoxCPM2 sidecar crashes while building the model
rem when OMP_NUM_THREADS is unset; any explicit value fixes it (2026-10-24).
if "%OMP_NUM_THREADS%"=="" set "OMP_NUM_THREADS=8"

set "OMNIVOICE_PORT=%VS_PORT%"
set "OMNIVOICE_BACKEND_CMD=%VS_PY% -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port %VS_PORT%"

echo Starting customised VoiceStudio...
cd /d "%~dp0electron"
bun run dev

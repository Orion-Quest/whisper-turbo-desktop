# Whisper Turbo Desktop

Windows-only desktop GUI for local `openai/whisper` transcription and English translation.

The project now uses a two-stage release model:

- Users download a small bootstrap installer
- On first launch, the bootstrap downloads the runtime package and `ffmpeg`
- On first actual transcription, Whisper downloads the `turbo` model if it is not already cached

## Features

- Single-run workflow for one audio/video file
- Batch queue for multiple files with sequential processing
- Drag-and-drop import
- `Source Language` input plus `Output Language` selection
- `Output Language = Original` maps to Whisper `transcribe`
- `Output Language = English (Translate)` maps to Whisper `translate`
- Real progress display during transcription
- Runtime model download on first use
- History view with double-click open for output file or folder
- Output preview for `txt`, `srt`, `vtt`, `json`, and `tsv`
- Runtime checks for managed `ffmpeg`, `whisper`, `torch`, `CUDA`, and model cache state

## Runtime Download Strategy

### First Launch

The installed bootstrap launcher downloads:

- the packaged runtime payload
- the managed `ffmpeg` payload

into the local application install directory.

### First Transcription

Whisper downloads the `turbo` model into:

- `%USERPROFILE%\\.cache\\whisper`

if the model is not already cached.

## Runtime Requirements

### End Users

- Windows 10/11
- Internet access on first launch
- Internet access on first transcription if the model is not cached

### Development

- Python `3.11.x`
- `openai-whisper`
- `PySide6`
- `ffmpeg` available in `PATH`

## Development Install

```powershell
python --version
python -m pip install -U pip
python -m pip install -r requirements.txt
```

If you want CUDA-enabled PyTorch:

```powershell
python -m pip install torch --index-url https://download.pytorch.org/whl/cu128
```

## Run In Development

```powershell
python main.py
```

Optional editable install:

```powershell
python -m pip install -e .
whisper-turbo-desktop
```

## How To Use

### Single Run

1. Choose or drop one media file.
2. Set `Source Language` if you want to skip auto-detection.
3. Choose `Output Language`.
4. Click `Run Current`.
5. If the model is not cached yet, Whisper will download it automatically.
6. Double-click an output file to open it.

### Batch Queue

1. Click `Queue Current` to enqueue the current file with the current settings.
2. Or click `Queue Files` to add multiple files at once.
3. Click `Start Queue`.
4. Use the `Queue` tab to inspect per-task state.
5. Double-click a completed queue item to open its output file or output folder.

### History

- Completed, failed, and cancelled runs are written to:
  - `%APPDATA%\\WhisperTurboDesktop\\history.json`
- Double-click a history item to open the first available output file.
- If the output file is missing, the app opens the recorded output folder instead.

## Build And Distribution

This repository now produces four release asset types:

- bootstrap installer
- runtime ZIP asset or runtime ZIP parts
- `ffmpeg` ZIP asset
- release manifest plus checksums

Build flow:

```powershell
$env:WTD_PYTHON='E:\Users\mc_leafwave\anaconda3\envs\my_11\python.exe'
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

Generated outputs are placed under `release/`.

## Repository Layout

```text
src/whisper_turbo_desktop/   Runtime application source
src/whisper_turbo_bootstrap/ Bootstrap launcher source
scripts/                     Build scripts
packaging/                   PyInstaller specs and installer script
docs/                        Release and rollout notes
```

## Known Constraints

- First launch requires network access because runtime and `ffmpeg` are downloaded at that time
- First transcription may still require network access if the model is not cached
- Torch remains the main size driver in the runtime package
- Large runtime ZIPs may be split into parts for GitHub Releases

# Whisper Turbo Desktop

Windows-only desktop GUI for local `openai/whisper` transcription and English translation.

The app uses the bundled Whisper `turbo` model directly through the Python API, so the packaged release does not depend on a separately installed Python runtime or an external Whisper CLI.

## Features

- Single-run workflow for one audio/video file
- Batch queue for multiple files with sequential processing
- Drag-and-drop import
- `Source Language` input plus `Output Language` selection
- `Output Language = Original` maps to Whisper `transcribe`
- `Output Language = English (Translate)` maps to Whisper `translate`
- Real progress from the embedded Whisper runtime
- History view with double-click open for output file or folder
- Output preview for `txt`, `srt`, `vtt`, `json`, and `tsv`
- Runtime checks for bundled `ffmpeg`, `whisper`, `torch`, and `CUDA`
- Portable release bundles `ffmpeg.exe`, the `large-v3-turbo.pt` model, default config, and a fallback font

## Runtime Requirements

- Windows 10/11
- Python `3.11.x`
- Recommended: CUDA-enabled `torch`
- Required: `openai-whisper`, `PySide6`

## Install

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
5. Double-click an output file to open it.

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

## Output Language Notes

- `Original` keeps the spoken language and uses Whisper `transcribe`
- `English (Translate)` requests English output and uses Whisper `translate`
- Official Whisper does not provide arbitrary target-language translation
- For non-English to Chinese or other target languages, you need a second translation step after Whisper

## Build And Distribution

This repository includes a Windows packaging flow based on PyInstaller.

- Build dependencies are listed in [requirements-build.txt](requirements-build.txt)
- The PyInstaller spec is in [packaging/whisper_turbo_desktop.spec](packaging/whisper_turbo_desktop.spec)
- The build script is [scripts/build_windows.ps1](scripts/build_windows.ps1)
- Packaging notes are in [packaging/BUILD.md](packaging/BUILD.md)

Typical build flow:

```powershell
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

## GitHub Release Download

Recommended README download link pattern after you publish a release:

```markdown
[Download Windows Portable Build](https://github.com/<OWNER>/<REPO>/releases/latest)
```

Important:

- The current portable payload is about `6.17 GB` with the bundled `turbo` model and bundled `ffmpeg.exe`
- A single GitHub release asset is usually not a practical delivery format for this payload size
- For truly one-click end-user delivery, use one of these:
  - external object storage/CDN for the portable folder or archive
  - a bootstrap installer that downloads the payload during setup
  - a multi-part installer/release strategy

The build script resolves these bundled assets automatically:

- `large-v3-turbo.pt` from `%USERPROFILE%\.cache\whisper`
- `ffmpeg.exe` from `WTD_FFMPEG_PATH`, Scoop, or the current `ffmpeg` command
- `assets/config/default_settings.json`
- `assets/fonts/DejaVuSans.ttf`

Release outputs:

- Portable app folder: `release/WhisperTurboDesktop-windows-x64-portable`
- Optional ZIP: `release/WhisperTurboDesktop-windows-x64-portable.zip` when the payload is 2 GB or smaller

## Repository Layout

```text
src/whisper_turbo_desktop/   Application source
scripts/                     Dev and build scripts
packaging/                   PyInstaller spec and packaging docs
docs/                        Release and handoff docs
```

## Known Constraints

- `turbo` is optimized for speed; `medium` or `large-v3` is usually safer for translation quality
- Packaging a Whisper + Torch desktop app with the bundled `turbo` model creates a very large Windows bundle
- PyInstaller builds can take significant time and disk space
- A GitHub single-file release asset may be impractical for this payload size; use the portable folder directly, external storage, or a multi-part/installer strategy

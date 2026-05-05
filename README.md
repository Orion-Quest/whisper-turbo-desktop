# Whisper Turbo Desktop

Windows desktop app for local `openai/whisper` transcription, Whisper English translation, and optional OpenAI-compatible subtitle translation to other languages.

## What It Does

Whisper Turbo Desktop turns audio or video files into text and subtitle files through a desktop workflow. The normal Whisper output stays local, and an optional API translation step can create translated subtitle sidecars when you want subtitles in another language.

Typical output files include `txt`, `srt`, `vtt`, `json`, and `tsv`. Optional API subtitle translation adds:

- `<name>.translated.srt`
- `<name>.translated.vtt`
- `<name>.translated.txt`

## Quick Links

- [Download latest Windows installer](https://github.com/Orion-Quest/whisper-turbo-desktop/releases)
- [Quick Start](#quick-start)
- [Download And Install](#download-and-install)
- [How To Use The App](#how-to-use-the-app)
- [Optional API Subtitle Translation](#optional-api-subtitle-translation)
- [Batch Queue](#batch-queue)
- [History](#history)
- [Build And Distribution](#build-and-distribution)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)

## Typical Uses

- Foreign language learning: create original-language subtitles, translated subtitles, listening practice material, and review text for vocabulary or shadowing.
- Subtitle production: generate draft `srt`/`vtt` files for videos, courses, clips, podcasts, and social media edits.
- Local transcription: convert meetings, lectures, interviews, voice notes, or recordings into searchable text.
- Bilingual study material: keep Whisper's original transcript while adding a translated sidecar for comparison.
- Accessibility and content review: produce readable captions and text previews before editing or publishing media.

## Quick Start

1. Download `WhisperTurboDesktop-Bootstrap-Setup-<version>.exe` from the [GitHub Release page](https://github.com/Orion-Quest/whisper-turbo-desktop/releases).
2. Run the installer and launch `Whisper Turbo Desktop`.
3. Choose or drop one audio/video file.
4. Select an output folder and choose `Whisper Mode`.
5. Optional: configure API subtitle translation if you want translated subtitle sidecars.
6. Click `Run Current`.

The first launch downloads the packaged runtime and managed `ffmpeg`. The first transcription may also download Whisper's `turbo` model if it is not already cached.
After the managed runtime is installed, later launches start the desktop app directly without showing the bootstrap download window.

## Download And Install

For normal Windows use, download only the bootstrap installer from [GitHub Releases](https://github.com/Orion-Quest/whisper-turbo-desktop/releases):

- `WhisperTurboDesktop-Bootstrap-Setup-<version>.exe`

Run that installer, then launch `Whisper Turbo Desktop`. The bootstrap launcher downloads the matching runtime and managed `ffmpeg` payload automatically on first launch.

The runtime ZIP, runtime `.part###` files, `ffmpeg` ZIP, manifest, and checksums are release support assets used by the bootstrap launcher. If a runtime ZIP is split into parts, every generated part must stay uploaded under the same release tag because the manifest references them by exact filename, size, and SHA-256 hash.

## Features

- Single-run workflow for one audio/video file
- Batch queue for multiple files with sequential processing
- Drag-and-drop import with active drop feedback
- Editable `Spoken Language` and `Extra Subtitle Language` selectors with common language suggestions
- `Whisper Mode = Original` maps to Whisper `transcribe`
- `Whisper Mode = English (Translate)` maps to Whisper `translate`
- Optional OpenAI-compatible subtitle translation to non-English target languages
- Custom translation API key, endpoint, and model settings
- Selectable glass/light desktop themes with a gradient progress bar
- Stage-aware progress display for model loading, Whisper, output writing, and API subtitle translation
- Faster startup path: bootstrap UI is skipped when the installed runtime is current, diagnostics run on refresh, and Whisper/Torch load only when transcription starts
- Hidden Windows child-process consoles for launcher, diagnostics, and Whisper's internal `ffmpeg` audio decode step
- Runtime model download on first use
- History view with separated time/status/file fields and double-click open for output file or folder
- Output preview for `txt`, `srt`, `vtt`, `json`, and `tsv`
- Runtime checks for managed `ffmpeg`, `whisper`, `torch`, `CUDA`, and model cache state

## How Downloads Work

### First Launch

The installed bootstrap launcher downloads:

- the packaged runtime payload
- the managed `ffmpeg` payload

into the local application install directory.

If the launcher is run directly from a download folder, the runtime is installed under `%LOCALAPPDATA%\Programs\WhisperTurboDesktop` instead of beside the downloaded `.exe`. Completed downloads are cached and reused after size/hash validation; incomplete downloads are written as temporary `.download` files and are only promoted after the transfer finishes.

### First Transcription

Whisper downloads the `turbo` model into:

- `%USERPROFILE%\.cache\whisper`

if the model is not already cached.

## Runtime Requirements

### End Users

- Windows 10/11
- Internet access on first launch
- Internet access on first transcription if the model is not cached
- Internet access during optional subtitle translation when an OpenAI-compatible provider is configured

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

## How To Use The App

### Single Run

1. Choose or drop one media file.
2. Set `Spoken Language` if you want to skip auto-detection.
3. Choose `Whisper Mode`.
4. Optionally fill in `Optional API Subtitle Translation` if you want translated subtitle sidecars for study, review, or publishing.
5. Click `Run Current`.
6. If the model is not cached yet, Whisper will download it automatically.
7. Double-click an output file to open it.

### Desktop Layout

The left control rail is for setup and actions: input/output paths, Whisper mode, optional API subtitle translation, queue buttons, and progress. The right workspace is for diagnostics, output files, preview, logs, queue details, and history.

The top bar includes a clickable `Open Output Folder` chip with the current output path, a `Theme` selector with `Aurora Glass`, `Slate Glass`, `Graphite Prism`, and `Clean Light`, plus diagnostics refresh. The theme choice is saved with the rest of the app settings.

### Optional API Subtitle Translation

`Whisper Mode` keeps its existing behavior: `Original` transcribes in the spoken language, and `English (Translate)` uses Whisper's English translate mode.

To prepare the optional OpenAI-compatible subtitle translation path, fill in `Optional API Subtitle Translation`:

- `Extra Subtitle Language`: desired subtitle language, such as `Spanish` or `Japanese`; choose a suggestion or type a custom target
- `API Key for Subtitles`: provider key
- `API Endpoint`: OpenAI-compatible API root such as `https://api.openai.com/v1`, or a full `.../chat/completions` endpoint
- `API Translation Model`: translation model name, for example `gpt-4o-mini`

When configured, the app keeps the normal Whisper outputs and writes translated sidecar files next to them:

- `<name>.translated.srt`
- `<name>.translated.vtt`
- `<name>.translated.txt`

These values are saved with the rest of the app settings and applied to new runs and queued items. Leave `Extra Subtitle Language` empty to skip the optional translation step.

Long subtitle jobs are translated in batches and stitched back together by subtitle index. The app requests strict JSON from providers that support it and automatically retries without that JSON-mode parameter for OpenAI-compatible endpoints that reject it.
Transient TLS, timeout, and remote disconnect errors are retried with short backoff before showing a diagnostic message that points to endpoint, proxy/VPN, network, or provider status.
Model output is also validated for subtitle structure and obvious target-script mistakes. For Chinese, Japanese, and Korean targets, the app retries once when the model returns malformed JSON, source-language leftovers, mixed-script junk, invalid replacement characters, unexpected timestamps/URLs, overly literal contraction-drill translations, or phonetic output for garbled ASR text.
Likely low-confidence Whisper text is marked in the API payload so the provider can use surrounding context to repair the line; if the meaning is still unclear, the model is instructed to output a short target-language unclear-audio marker instead of inventing a literal translation.

### Batch Queue

1. Click `Add Current to Queue` to enqueue the current file with the current settings.
2. Or click `Add Files to Queue` to add multiple files at once.
3. Click `Run Queue`.
4. Use the `Queue` tab to inspect per-task state.
5. Double-click a completed queue item to open its output file or output folder.

### History

- Completed, failed, and cancelled runs are written to:
  - `%APPDATA%\WhisperTurboDesktop\history.json`
- History rows visually separate run time, completed/failed/cancelled status, duration, task/model, and input filename.
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

The Windows build verifies that the packaged managed `ffmpeg` payload contains a real runnable binary. This matters for Scoop installs because `scoop\shims\ffmpeg.exe` is only a shim; the build resolves the shim target, zips the real executable, extracts the generated ZIP, and runs `tools/ffmpeg/bin/ffmpeg.exe -version` before producing release metadata.

`SHA256SUMS.txt` is generated for public release assets only: the bootstrap installer, runtime archive or parts, managed `ffmpeg` ZIP, and release manifest. It is intended to verify files after users or release automation download those assets into a clean directory.

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
- Optional subtitle translation requires network access to the configured OpenAI-compatible endpoint
- Torch remains the main size driver in the runtime package
- Large runtime ZIPs may be split into parts for GitHub Releases

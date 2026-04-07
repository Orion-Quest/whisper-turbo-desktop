# Bootstrap Installer Plan

## Goal

Provide a small Windows installer that places only a bootstrap launcher on disk.

On first launch, the bootstrap launcher downloads:

- the runtime package
- the `ffmpeg` package

Then, on first actual transcription, Whisper downloads the model if it is not already cached.

## Public Release Assets

GitHub Releases is the single public hosting surface.

Per release, publish:

- `WhisperTurboDesktop-Bootstrap-Setup-<version>.exe`
- `WhisperTurboDesktop-runtime-<version>.zip`
  - or split parts if needed
- `ffmpeg-windows-x64-<version>.zip`
- `release-manifest-<version>.json`
- `SHA256SUMS.txt`

## Bootstrap Responsibilities

- read the bundled release manifest
- detect whether the correct runtime version is already installed
- detect whether managed `ffmpeg` is already installed
- download missing assets from GitHub Releases
- verify SHA256 checksums
- extract runtime and `ffmpeg` into the managed install root
- write `installed_manifest.json`
- launch the runtime app

## Install Layout

- install root:
  - `%LOCALAPPDATA%\\Programs\\WhisperTurboDesktop`
- bootstrap exe:
  - `%LOCALAPPDATA%\\Programs\\WhisperTurboDesktop\\WhisperTurboDesktop.exe`
- runtime app:
  - `%LOCALAPPDATA%\\Programs\\WhisperTurboDesktop\\runtime\\WhisperTurboDesktop.exe`
- managed `ffmpeg`:
  - `%LOCALAPPDATA%\\Programs\\WhisperTurboDesktop\\tools\\ffmpeg\\bin\\ffmpeg.exe`
- model cache:
  - `%USERPROFILE%\\.cache\\whisper`

## Failure Handling

- network failure:
  - fail fast with a clear error dialog
- checksum mismatch:
  - delete the downloaded file and abort
- insufficient disk space:
  - block installation before download starts
- extraction failure:
  - leave the old installation intact and abort

## Release Workflow

1. Build runtime payload.
2. Build bootstrap launcher.
3. Generate manifest and checksums.
4. Optionally compile the Inno Setup installer.
5. Upload assets to GitHub Releases under a version tag.

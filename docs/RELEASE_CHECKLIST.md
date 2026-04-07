# Release Checklist

## Before Build

- Confirm the runtime app launches with `python main.py`
- Confirm queue and history interactions still work
- Confirm `ffmpeg.exe` is available locally for packaging input

## Build

- Install build dependencies from `requirements-build.txt`
- Run `scripts/build_windows.ps1`
- Verify:
  - `release/release-manifest-<version>.json`
  - runtime ZIP or runtime parts
  - `ffmpeg` ZIP
  - bootstrap launcher folder
  - `SHA256SUMS.txt`
- If Inno Setup is installed, verify the bootstrap installer exists under `release/installer`

## Bootstrap Smoke Test

- Run the packaged bootstrap launcher on a clean machine or clean user profile
- Confirm it downloads the runtime payload
- Confirm it downloads the `ffmpeg` payload
- Confirm it verifies checksums before extraction
- Confirm it starts the runtime app after installation

## Runtime Smoke Test

- Run one single-file transcription
- Confirm the model downloads automatically if it is not already cached
- Queue at least two files and start the queue
- Double-click one history record and one output file
- Confirm output files are written to the configured output folder

## Ship

- Upload the bootstrap installer
- Upload runtime ZIP or runtime parts
- Upload `ffmpeg` ZIP
- Upload release manifest and checksums
- Release notes must clearly state:
  - bootstrap downloads runtime and `ffmpeg` on first launch
  - Whisper downloads the model on first transcription

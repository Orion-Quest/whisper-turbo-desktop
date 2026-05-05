# Release Checklist

## Before Build

- Confirm the runtime app launches with `python main.py`
- Confirm queue and history interactions still work
- Confirm `ffmpeg.exe` is available locally for packaging input
- Confirm the selected `ffmpeg.exe` is the real binary, not a Scoop shim:
  - do not use a path under `scoop\shims`
  - the binary should be larger than 10 MB
  - `ffmpeg.exe -version` must print `ffmpeg version ...`

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
- Extract the generated `ffmpeg` ZIP and run `tools/ffmpeg/bin/ffmpeg.exe -version`
- Confirm `SHA256SUMS.txt` contains only public release asset basenames, not internal bootstrap files
- Reassemble runtime parts, if split, and verify the merged runtime archive SHA-256 matches the manifest

## Bootstrap Smoke Test

- Run the packaged bootstrap launcher on a clean machine or clean user profile
- Confirm it downloads the runtime payload
- Confirm it downloads the `ffmpeg` payload
- Confirm it verifies checksums before extraction
- Confirm the installed managed `ffmpeg.exe` is runnable and matches the manifest size/hash/version
- Confirm it starts the runtime app after installation
- Confirm a normal second launch skips the bootstrap download window and opens the desktop app directly

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
- Download the public release assets to a clean temporary directory and verify `SHA256SUMS.txt`
- Extract the public `ffmpeg` ZIP and run the extracted `ffmpeg.exe -version`
- Release notes must clearly state:
  - end users should download the bootstrap installer
  - bootstrap downloads runtime and `ffmpeg` on first launch
  - Whisper downloads the model on first transcription
  - all runtime parts must be uploaded together when the runtime archive is split

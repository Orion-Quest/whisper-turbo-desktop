# Release Checklist

## Before Build

- Confirm the app launches with `python main.py`
- Confirm `large-v3-turbo.pt` exists under `%USERPROFILE%\.cache\whisper` or set `WTD_MODEL_PATH`
- Confirm `ffmpeg.exe` can be resolved or set `WTD_FFMPEG_PATH`
- Confirm queue and history interactions still work

## Build

- Install build dependencies from `requirements-build.txt`
- Run `scripts/build_windows.ps1`
- Verify the output exists under `dist/WhisperTurboDesktop`
- Verify `release/WhisperTurboDesktop-windows-x64-portable` exists

## Smoke Test

- Launch the packaged executable
- Run one single-file transcription
- Queue at least two files and start the queue
- Double-click one history record and one output file
- Confirm output files are written to the configured output folder
- Confirm bundled `ffmpeg.exe` and bundled model are present inside the release folder

## Ship

- Attach the packaged folder or ZIP
- Include build instructions and runtime prerequisites
- Note that the release includes a bundled model and bundled `ffmpeg.exe`
- If the portable ZIP is larger than your release target allows, publish the folder through external storage or use an installer/bootstrap strategy

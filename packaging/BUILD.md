# Windows Build Notes

This project now builds a bootstrap-based Windows release.

## Commands

```powershell
$env:WTD_PYTHON='E:\Users\mc_leafwave\anaconda3\envs\my_11\python.exe'
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

Optional environment overrides:

- `WTD_PYTHON`
- `WTD_FFMPEG_PATH`
- `WTD_RELEASE_REPO`
- `WTD_ISCC`

## Output

- `dist/WhisperTurboDesktop`
  - heavy runtime bundle
- `dist/WhisperTurboBootstrap`
  - bootstrap launcher build
- `release/`
  - runtime ZIP or runtime parts
  - `ffmpeg` ZIP
  - bootstrap launcher folder
  - release manifest
  - SHA256 checksums
  - optional Inno Setup installer

## Current Strategy

- Use `main.py` as the runtime GUI entrypoint
- Use `bootstrap_main.py` as the bootstrap entrypoint
- Bundle neither Whisper model nor `ffmpeg` inside the runtime release
- Download runtime payload and `ffmpeg` on first bootstrap launch
- Download Whisper model on first real transcription
- Resolve Scoop `ffmpeg` shims to the real executable before packaging
- Extract and run the generated `tools/ffmpeg/bin/ffmpeg.exe -version` before accepting release assets

## Notes

- GitHub Releases remains the single public hosting surface
- If the runtime ZIP exceeds GitHub single-asset limits, the build script splits it into ordered parts
- The installer packages only the bootstrap launcher and release manifest
- `SHA256SUMS.txt` contains only public release asset basenames so it can be verified in a clean download directory

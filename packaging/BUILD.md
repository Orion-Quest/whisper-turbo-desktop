# Windows Build Notes

This project uses PyInstaller to build a Windows desktop bundle with the Whisper `turbo` model and a bundled `ffmpeg.exe`.

## Commands

```powershell
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

## Output

- Default bundle output: `dist/WhisperTurboDesktop`
- Intermediate build files: `build/`
- Portable release folder: `release/WhisperTurboDesktop-windows-x64-portable`

## Current Strategy

- Use `main.py` as the GUI entrypoint
- Add `src/` to `pathex`
- Collect Whisper, Tiktoken, and Torch runtime assets
- Collect `large-v3-turbo.pt` into `models/`
- Collect `ffmpeg.exe` into `bin/`
- Collect default config and fallback font assets
- Produce a windowed directory-style bundle instead of one-file mode

## Notes

- Torch makes the bundle large
- The build script fails fast if it cannot find the bundled model or `ffmpeg.exe`
- The final portable payload can exceed GitHub's practical single-asset size
- For a polished installer, add a second step with Inno Setup or another installer tool

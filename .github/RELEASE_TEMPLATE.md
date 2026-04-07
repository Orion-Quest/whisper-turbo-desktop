## Whisper Turbo Desktop {{VERSION}}

Windows desktop app for local Whisper transcription and English translation.

### Release Assets

- `WhisperTurboDesktop-Bootstrap-Setup-{{VERSION}}.exe`
  - small installer
  - recommended for end users
- `WhisperTurboDesktop-runtime-{{VERSION}}.zip`
  - or split runtime parts if the archive exceeds GitHub single-asset limits
- `ffmpeg-windows-x64-<version>.zip`
  - managed ffmpeg payload downloaded by the bootstrap launcher
- `release-manifest-{{VERSION}}.json`
  - runtime metadata used by the bootstrap launcher
- `SHA256SUMS.txt`
  - checksums for all published files

### Runtime Model

- On first launch, the bootstrap launcher downloads:
  - the runtime payload
  - the managed `ffmpeg` payload
- On first actual transcription, Whisper downloads the `turbo` model if it is not already cached

### Installation

1. Download `WhisperTurboDesktop-Bootstrap-Setup-{{VERSION}}.exe`
2. Run the installer
3. Launch `Whisper Turbo Desktop`
4. On first launch, wait for the bootstrap launcher to download the runtime package and `ffmpeg`

### First Run Notes

- `Output Language = Original` keeps the spoken language
- `Output Language = English (Translate)` outputs English text
- The first transcription may still require network access if the Whisper model is not cached

### Checksums

```text
<paste SHA256SUMS here>
```

### Known Issues

- The runtime payload is still large because it includes Torch and the packaged runtime
- If the runtime ZIP exceeds GitHub single-asset limits, publish the generated part files together

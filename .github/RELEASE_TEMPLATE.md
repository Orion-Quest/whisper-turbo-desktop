## Whisper Turbo Desktop {{VERSION}}

Windows desktop app for local Whisper transcription, Whisper English translation, and optional OpenAI-compatible subtitle translation to non-English targets.

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
- If the runtime ZIP is split into parts, publish every generated `.part###` file under this same tag

### Installation

1. Download `WhisperTurboDesktop-Bootstrap-Setup-{{VERSION}}.exe`
2. Run the installer
3. Launch `Whisper Turbo Desktop`
4. On first launch, wait for the bootstrap launcher to download the runtime package and `ffmpeg`

### First Run Notes

- `Whisper Mode = Original` keeps the spoken language
- `Whisper Mode = English (Translate)` outputs English text
- Optional API subtitle translation writes `.translated.srt`, `.translated.vtt`, and `.translated.txt` sidecars
- OpenAI-compatible API endpoints can be configured with a custom key, endpoint, and model

### Notable Changes

- Improved desktop layout, selectable glass themes, and gradient progress feedback
- Added clearer output-folder affordance, history rows, and translation setup status
- Hardened bootstrap download caching, checksum validation, and direct-download install paths
- Improved API subtitle translation with strict JSON handling, transient network retries, target-script validation, low-confidence ASR guidance, and retries for obvious literal or phonetic bad model output
- The first transcription may still require network access if the Whisper model is not cached

### Checksums

```text
<paste SHA256SUMS here>
```

### Known Issues

- The runtime payload is still large because it includes Torch and the packaged runtime
- If the runtime ZIP exceeds GitHub single-asset limits, publish the generated part files together

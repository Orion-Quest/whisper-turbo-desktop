## Whisper Turbo Desktop {{VERSION}}

Windows desktop app for local Whisper transcription and English translation.

### Release Assets

- `WhisperTurboDesktop-Setup-{{VERSION}}.exe`
  - Inno Setup installer
  - recommended for end users
- `WhisperTurboDesktop-windows-x64-portable`
  - unpacked portable build
  - useful for internal deployment or manual packaging
- `SHA256SUMS.txt`
  - checksums for published files

### What's Included

- bundled Whisper `turbo` model
- bundled `ffmpeg.exe`
- bundled Python runtime and required libraries
- bundled default config and fallback font

### Installation

1. Download `WhisperTurboDesktop-Setup-{{VERSION}}.exe`
2. Run the installer
3. Launch `Whisper Turbo Desktop` from the Start Menu or desktop shortcut

### First Run Notes

- `Output Language = Original` keeps the spoken language
- `Output Language = English (Translate)` outputs English text
- GPU is used when available; CPU fallback remains available

### Upgrade Notes

- uninstalling the app does not remove user data under `%APPDATA%\WhisperTurboDesktop`
- if you are upgrading from an older build, close the app before installation

### Checksums

```text
<paste SHA256SUMS here>
```

### Known Issues

- the full payload is large because the Whisper model is bundled
- translation output is limited to English in the current release


# Bootstrap Installer Plan

## Goal

Provide a small Windows installer that users can download from GitHub Releases and run directly. The installer should:

- detect the local system and available disk space
- download the full portable payload or payload parts from a remote source
- verify integrity before install
- unpack the app into the chosen install directory
- create shortcuts and uninstall metadata
- support update checks and payload replacement without requiring the user to handle large archives manually

This is the practical delivery path when the full portable build is too large for a single GitHub release asset.

## Recommended Use Cases

- the bundled model and runtime make the full payload several GB
- the project needs a simple "Download -> Run Installer -> Launch App" experience
- you want to keep GitHub Releases as the public control plane, but host large payload files elsewhere
- you want future updates to reuse the same installer and manifest format

## Distribution Model

### Public Artifacts

- GitHub Releases:
  - `WhisperTurboDesktop-Bootstrap-Setup.exe`
  - release notes
  - checksums for installer and payload manifest
- external storage or CDN:
  - `WhisperTurboDesktop-windows-x64-portable.7z.001`
  - `WhisperTurboDesktop-windows-x64-portable.7z.002`
  - additional parts as needed
  - optional full folder archive for internal distribution
- manifest file:
  - `manifest.json`
  - contains version, file list, sizes, checksums, release channel, minimum disk space

## Core Flow

1. User downloads `WhisperTurboDesktop-Bootstrap-Setup.exe` from GitHub Releases.
2. Bootstrap installer starts and shows:
   - product name
   - target version
   - install path
   - required disk space
3. Installer downloads `manifest.json`.
4. Installer validates:
   - OS version
   - architecture
   - available disk space
   - write permissions for install directory
5. Installer downloads payload files from CDN/object storage.
6. Installer verifies checksums for every downloaded part.
7. Installer extracts payload to install directory.
8. Installer writes:
   - app files
   - uninstall entry
   - desktop shortcut
   - start menu shortcut
9. Installer optionally launches the app.

## Update Flow

1. App checks a lightweight update manifest URL on startup or through "Check for Updates".
2. If a newer version exists:
   - prompt user
   - download only the new payload package
   - stage replacement
   - close app
   - replace files
   - relaunch
3. Keep rollback strategy:
   - backup previous install folder
   - if replacement fails, restore previous version

## Component Structure

```text
bootstrap/
  installer/
    WhisperTurboDesktop-Bootstrap.iss
  payload/
    manifest.json
    checksums.txt
    WhisperTurboDesktop-windows-x64-portable.7z.001
    WhisperTurboDesktop-windows-x64-portable.7z.002
  docs/
    INSTALL.md
```

## Manifest Example

```json
{
  "app_id": "WhisperTurboDesktop",
  "version": "v0.1.0",
  "channel": "stable",
  "platform": "windows-x64",
  "min_disk_space_gb": 12,
  "entry_exe": "WhisperTurboDesktop.exe",
  "payload_parts": [
    {
      "name": "WhisperTurboDesktop-windows-x64-portable.7z.001",
      "url": "https://downloads.example.com/WhisperTurboDesktop/v0.1.0/WhisperTurboDesktop-windows-x64-portable.7z.001",
      "sha256": "<replace-me>",
      "size": 2147483648
    },
    {
      "name": "WhisperTurboDesktop-windows-x64-portable.7z.002",
      "url": "https://downloads.example.com/WhisperTurboDesktop/v0.1.0/WhisperTurboDesktop-windows-x64-portable.7z.002",
      "sha256": "<replace-me>",
      "size": 2147483648
    }
  ]
}
```

## Installation Strategy

- preferred installer engine: `Inno Setup`
- payload extraction helper:
  - embed `7za.exe` or another extraction tool
  - or ship a self-extracting payload
- install root default:
  - `{autopf}\WhisperTurboDesktop`
- user data stays outside install folder:
  - `%APPDATA%\WhisperTurboDesktop`

## Dependency Handling

- Python runtime:
  - already bundled in the portable payload
- Whisper model:
  - bundled inside payload
- `ffmpeg.exe`:
  - bundled inside payload
- GPU runtime:
  - rely on system NVIDIA driver and compatible CUDA support
  - if unavailable, app falls back to CPU
- fonts and config:
  - bundled inside payload

## Error Handling

- network failure:
  - show retry dialog
  - allow resume if partial parts exist
- checksum mismatch:
  - delete corrupted part
  - redownload only failed part
- insufficient disk space:
  - block install with exact required amount
- extraction failure:
  - keep temp files for diagnostics
  - allow cleanup and retry

## Release Workflow

1. Build portable payload locally.
2. Split or archive payload for remote hosting.
3. Generate SHA256 checksums.
4. Upload payload parts to CDN/object storage.
5. Publish bootstrap installer to GitHub Releases.
6. Publish release notes with:
   - bootstrap installer link
   - payload version
   - checksum file
   - known issues

## Practical Recommendation

For this project, use:

- GitHub Releases for:
  - bootstrap installer
  - release notes
  - checksums
- external storage for:
  - full payload archive or archive parts

This gives you a user-facing "one click installer" while avoiding GitHub asset size constraints.


$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$pythonExe = if ($env:WTD_PYTHON) { $env:WTD_PYTHON } else { "python" }

function Get-ProjectVersion {
    @'
import pathlib
import tomllib
payload = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))
print(payload["project"]["version"])
'@ | & $pythonExe -
}

function Resolve-GitHubRepo {
    if ($env:WTD_RELEASE_REPO) {
        return $env:WTD_RELEASE_REPO
    }

    $remoteUrl = git remote get-url origin
    if ($remoteUrl -match 'github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+)(?:\.git)?$') {
        return "$($Matches.owner)/$($Matches.repo)"
    }

    throw "Cannot resolve GitHub repository from origin remote. Set WTD_RELEASE_REPO=owner/repo."
}

function Resolve-FfmpegPath {
    if ($env:WTD_FFMPEG_PATH -and (Test-Path $env:WTD_FFMPEG_PATH)) {
        return Resolve-FfmpegExecutablePath $env:WTD_FFMPEG_PATH
    }

    $command = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($null -ne $command -and (Test-Path $command.Source)) {
        return Resolve-FfmpegExecutablePath $command.Source
    }

    throw "ffmpeg.exe not found. Install ffmpeg or set WTD_FFMPEG_PATH."
}

function Resolve-FfmpegExecutablePath([string]$candidatePath) {
    $resolvedPath = (Resolve-Path $candidatePath).Path
    $shimPath = [System.IO.Path]::ChangeExtension($resolvedPath, ".shim")
    if (Test-Path $shimPath) {
        $shimContent = Get-Content -Path $shimPath -Raw
        if ($shimContent -match '(?m)^\s*path\s*=\s*"(?<target>[^"]+)"\s*$') {
            $shimTarget = [Environment]::ExpandEnvironmentVariables($Matches.target)
            if (-not (Test-Path $shimTarget)) {
                throw "ffmpeg shim target does not exist: $shimTarget"
            }
            $resolvedPath = (Resolve-Path $shimTarget).Path
        } else {
            throw "Cannot resolve ffmpeg shim target from: $shimPath"
        }
    }

    $versionOutput = & $resolvedPath -version 2>&1 | Select-Object -First 1
    if ($LASTEXITCODE -ne 0 -or $versionOutput -notmatch '^ffmpeg version ') {
        throw "Resolved ffmpeg path is not a runnable ffmpeg binary: $resolvedPath"
    }

    return $resolvedPath
}

function Resolve-CondaTkDllPath([string]$pythonPath, [string]$dllName) {
    $pythonResolved = (Resolve-Path $pythonPath).Path
    $envRoot = Split-Path -Parent $pythonResolved
    $candidate = Join-Path $envRoot "Library\\bin\\$dllName"
    if (-not (Test-Path $candidate)) {
        throw "$dllName not found next to the selected Python env: $candidate"
    }
    return (Resolve-Path $candidate).Path
}

function Resolve-CondaBinDllPath([string]$pythonPath, [string]$dllName) {
    return Resolve-CondaTkDllPath $pythonPath $dllName
}

function Resolve-IsccPath {
    if ($env:WTD_ISCC -and (Test-Path $env:WTD_ISCC)) {
        return (Resolve-Path $env:WTD_ISCC).Path
    }

    $command = Get-Command iscc -ErrorAction SilentlyContinue
    if ($null -ne $command -and (Test-Path $command.Source)) {
        return (Resolve-Path $command.Source).Path
    }

    $candidates = @(
        (Join-Path $HOME "AppData\Local\Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    return $null
}

function Invoke-PythonScript([string]$script) {
    $script | & $pythonExe -
}

$version = (Get-ProjectVersion).Trim()
$tag = "v$version"
$repo = Resolve-GitHubRepo
$repoOwner, $repoName = $repo.Split("/")
$ffmpegPath = Resolve-FfmpegPath
$releaseRoot = Join-Path $projectRoot "release"
$runtimeDist = Join-Path $projectRoot "dist\WhisperTurboDesktop"
$bootstrapDist = Join-Path $projectRoot "dist\WhisperTurboBootstrap"
$bootstrapReleaseDir = Join-Path $releaseRoot "bootstrap"
$installerOutputDir = Join-Path $releaseRoot "installer"
$runtimeArchiveName = "WhisperTurboDesktop-runtime-$version.zip"
$runtimeArchivePath = Join-Path $releaseRoot $runtimeArchiveName

Write-Host "Using Python interpreter: $pythonExe"
Write-Host "Release version: $version"
Write-Host "GitHub repo: $repo"
Write-Host "Using ffmpeg: $ffmpegPath"

Write-Host "Installing build dependencies..."
& $pythonExe -m pip install -r requirements-build.txt

Write-Host "Cleaning previous build output..."
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
if (Test-Path release) { Remove-Item -Recurse -Force release }

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
New-Item -ItemType Directory -Force -Path $bootstrapReleaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $installerOutputDir | Out-Null

Write-Host "Building runtime payload..."
& $pythonExe -m PyInstaller --noconfirm packaging\whisper_turbo_desktop.spec
if ($LASTEXITCODE -ne 0) {
    throw "Runtime PyInstaller build failed with exit code $LASTEXITCODE"
}

Write-Host "Creating runtime archive..."
$runtimeZipScript = @"
from pathlib import Path
import zipfile

dist_root = Path(r"$runtimeDist")
archive_path = Path(r"$runtimeArchivePath")
with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
    for item in dist_root.rglob("*"):
        if item.is_file():
            archive.write(item, item.relative_to(dist_root))
"@
Invoke-PythonScript $runtimeZipScript

Write-Host "Creating ffmpeg archive..."
$ffmpegVersion = (& $ffmpegPath -version | Select-Object -First 1)
if ($ffmpegVersion -match '^ffmpeg version (?<ver>\S+)') {
    $ffmpegVersionValue = $Matches.ver
} else {
    $ffmpegVersionValue = "unknown"
}
$ffmpegExecutableItem = Get-Item $ffmpegPath
$ffmpegExecutableSize = [int64]$ffmpegExecutableItem.Length
$ffmpegExecutableSha256 = (Get-FileHash $ffmpegPath -Algorithm SHA256).Hash.ToLower()
$ffmpegVersionSafe = ($ffmpegVersionValue -replace '[^A-Za-z0-9._-]', '_')
$ffmpegArchiveName = "ffmpeg-windows-x64-$ffmpegVersionSafe.zip"
$ffmpegArchivePath = Join-Path $releaseRoot $ffmpegArchiveName
$ffmpegZipScript = @"
from pathlib import Path
import shutil
import tempfile
import zipfile

ffmpeg_path = Path(r"$ffmpegPath")
archive_path = Path(r"$ffmpegArchivePath")
with tempfile.TemporaryDirectory(prefix="wtd-ffmpeg-") as tmp:
    tmp_root = Path(tmp)
    target = tmp_root / "tools" / "ffmpeg" / "bin"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ffmpeg_path, target / "ffmpeg.exe")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for item in tmp_root.rglob("*"):
            if item.is_file():
                archive.write(item, item.relative_to(tmp_root))
"@
Invoke-PythonScript $ffmpegZipScript

Write-Host "Verifying ffmpeg archive..."
$verifyFfmpegZipScript = @"
from pathlib import Path
import hashlib
import subprocess
import tempfile
import zipfile

archive_path = Path(r"$ffmpegArchivePath")
expected_size = int("$ffmpegExecutableSize")
expected_sha256 = "$ffmpegExecutableSha256"
expected_version = "$ffmpegVersionValue"
minimum_real_binary_size = 10 * 1024 * 1024

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

with tempfile.TemporaryDirectory(prefix="wtd-verify-ffmpeg-") as tmp:
    extract_root = Path(tmp)
    with zipfile.ZipFile(archive_path, "r") as archive:
        archive.extractall(extract_root)
    ffmpeg_exe = extract_root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if not ffmpeg_exe.exists():
        raise SystemExit(f"ffmpeg archive is missing expected executable: {ffmpeg_exe}")
    actual_size = ffmpeg_exe.stat().st_size
    if actual_size < minimum_real_binary_size:
        raise SystemExit(f"ffmpeg archive contains an implausibly small executable: {actual_size} bytes")
    if actual_size != expected_size:
        raise SystemExit(f"ffmpeg executable size mismatch: expected {expected_size}, got {actual_size}")
    actual_sha256 = sha256(ffmpeg_exe)
    if actual_sha256 != expected_sha256:
        raise SystemExit(f"ffmpeg executable checksum mismatch: expected {expected_sha256}, got {actual_sha256}")
    completed = subprocess.run(
        [str(ffmpeg_exe), "-version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    first_line = (completed.stdout or completed.stderr).splitlines()[0] if (completed.stdout or completed.stderr) else ""
    if completed.returncode != 0 or not first_line.startswith("ffmpeg version "):
        raise SystemExit(f"extracted ffmpeg is not runnable: {first_line}")
    if expected_version and expected_version != "unknown" and f"ffmpeg version {expected_version}" not in first_line:
        raise SystemExit(f"extracted ffmpeg version mismatch: expected {expected_version}, got {first_line}")
"@
Invoke-PythonScript $verifyFfmpegZipScript

Write-Host "Splitting archives for GitHub Releases if needed..."
$splitThresholdBytes = 1900MB
$splitScript = @"
from pathlib import Path
import hashlib
import json

threshold = $splitThresholdBytes

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def split_archive(path_str: str):
    path = Path(path_str)
    archive_size = path.stat().st_size
    archive_sha = sha256(path)
    if archive_size <= threshold:
        return {
            "archive_name": path.name,
            "archive_sha256": archive_sha,
            "archive_size": archive_size,
            "parts": [{
                "name": path.name,
                "sha256": archive_sha,
                "size": archive_size,
            }],
        }

    parts = []
    part_index = 1
    with path.open("rb") as source:
        while True:
            chunk = source.read(threshold)
            if not chunk:
                break
            part_name = f"{path.name}.part{part_index:03d}"
            part_path = path.parent / part_name
            part_path.write_bytes(chunk)
            parts.append({
                "name": part_name,
                "sha256": sha256(part_path),
                "size": part_path.stat().st_size,
            })
            part_index += 1
    path.unlink()
    return {
        "archive_name": path.name,
        "archive_sha256": archive_sha,
        "archive_size": archive_size,
        "parts": parts,
    }

runtime_bundle = split_archive(r"$runtimeArchivePath")
ffmpeg_bundle = split_archive(r"$ffmpegArchivePath")
Path(r"$releaseRoot\bundle-metadata.json").write_text(
    json.dumps({
        "runtime_bundle": runtime_bundle,
        "ffmpeg_bundle": ffmpeg_bundle,
    }, indent=2),
    encoding="utf-8",
)
"@
Invoke-PythonScript $splitScript

$bundleMetadata = Get-Content "$releaseRoot\bundle-metadata.json" | ConvertFrom-Json
$runtimeBundle = $bundleMetadata.runtime_bundle
$ffmpegBundle = $bundleMetadata.ffmpeg_bundle
Remove-Item "$releaseRoot\bundle-metadata.json" -Force

$runtimePartsSize = [int64](($runtimeBundle.parts | Measure-Object -Property size -Sum).Sum)
$ffmpegPartsSize = [int64](($ffmpegBundle.parts | Measure-Object -Property size -Sum).Sum)
$downloadCacheBytes = $runtimePartsSize + $ffmpegPartsSize
$mergedArchiveBytes = [int64]($runtimeBundle.archive_size + $ffmpegBundle.archive_size)
$extractEstimateBytes = [int64]($runtimeBundle.archive_size + $ffmpegBundle.archive_size)
$upgradeBufferBytes = [int64]1073741824
$requiredDiskSpaceBytes = [int64]($downloadCacheBytes + $mergedArchiveBytes + $extractEstimateBytes + $upgradeBufferBytes)
$manifestPath = Join-Path $releaseRoot "release-manifest-$version.json"
$bootstrapManifestPath = Join-Path $bootstrapReleaseDir "release-manifest.json"

$manifestObject = [ordered]@{
    version = $version
    tag = $tag
    repo_owner = $repoOwner
    repo_name = $repoName
    required_disk_space_bytes = $requiredDiskSpaceBytes
    runtime_entry_relative_path = "runtime/WhisperTurboDesktop.exe"
    ffmpeg_relative_path = "tools/ffmpeg/bin/ffmpeg.exe"
    ffmpeg_executable_sha256 = $ffmpegExecutableSha256
    ffmpeg_executable_size = $ffmpegExecutableSize
    ffmpeg_executable_version = $ffmpegVersionValue
    runtime_bundle = $runtimeBundle
    ffmpeg_bundle = $ffmpegBundle
}

$manifestJson = $manifestObject | ConvertTo-Json -Depth 6
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, $utf8NoBom)
[System.IO.File]::WriteAllText($bootstrapManifestPath, $manifestJson, $utf8NoBom)

Write-Host "Building bootstrap launcher..."
& $pythonExe -m PyInstaller --noconfirm packaging\whisper_turbo_bootstrap.spec
if ($LASTEXITCODE -ne 0) {
    throw "Bootstrap PyInstaller build failed with exit code $LASTEXITCODE"
}

$bootstrapInternal = Join-Path $bootstrapDist "_internal"
$tclDll = Resolve-CondaTkDllPath $pythonExe "tcl86t.dll"
$tkDll = Resolve-CondaTkDllPath $pythonExe "tk86t.dll"
$zlib1Dll = Resolve-CondaBinDllPath $pythonExe "zlib1.dll"
Copy-Item $tclDll (Join-Path $bootstrapInternal "tcl86t.dll") -Force
Copy-Item $tkDll (Join-Path $bootstrapInternal "tk86t.dll") -Force
Copy-Item $zlib1Dll (Join-Path $bootstrapInternal "zlib1.dll") -Force

$bootstrapExeSource = Join-Path $bootstrapDist "WhisperTurboDesktop.exe"
Copy-Item -Path "$bootstrapDist\*" -Destination $bootstrapReleaseDir -Recurse -Force

$iscc = Resolve-IsccPath
if ($null -ne $iscc) {
    Write-Host "Building Inno Setup installer..."
    & $iscc "/DMyAppVersion=$version" "/DMySourceDir=$bootstrapReleaseDir" "/DMyOutputDir=$installerOutputDir" packaging\WhisperTurboDesktop.iss
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup build failed with exit code $LASTEXITCODE"
    }
} else {
    Write-Warning "ISCC.exe not found. Skipping installer build."
}

Write-Host "Generating SHA256SUMS..."
$hashFile = Join-Path $releaseRoot "SHA256SUMS.txt"
if (Test-Path $hashFile) { Remove-Item $hashFile -Force }
$publishAssetPaths = @()
if (Test-Path $installerOutputDir) {
    $publishAssetPaths += @(Get-ChildItem $installerOutputDir -File -Filter "*.exe" | ForEach-Object { $_.FullName })
}
foreach ($part in @($runtimeBundle.parts)) {
    $publishAssetPaths += (Join-Path $releaseRoot $part.name)
}
foreach ($part in @($ffmpegBundle.parts)) {
    $publishAssetPaths += (Join-Path $releaseRoot $part.name)
}
$publishAssetPaths += $manifestPath

$publishAssetPaths | Sort-Object -Unique | ForEach-Object {
    if (-not (Test-Path $_)) {
        throw "Expected release asset not found for checksums: $_"
    }
    $asset = Get-Item $_
    $hash = (Get-FileHash $asset.FullName -Algorithm SHA256).Hash.ToLower()
    Add-Content -Path $hashFile -Value "$hash  $($asset.Name)"
}

Write-Host "Release assets ready under: $releaseRoot"

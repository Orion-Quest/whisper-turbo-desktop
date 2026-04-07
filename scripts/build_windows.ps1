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
        return (Resolve-Path $env:WTD_FFMPEG_PATH).Path
    }

    $command = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($null -ne $command -and (Test-Path $command.Source)) {
        return (Resolve-Path $command.Source).Path
    }

    throw "ffmpeg.exe not found. Install ffmpeg or set WTD_FFMPEG_PATH."
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

$requiredDiskSpaceBytes = [int64]($runtimeBundle.archive_size + $ffmpegBundle.archive_size + 1073741824)
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
Get-ChildItem $releaseRoot -Recurse -File | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    $relative = Resolve-Path -Relative $_.FullName
    Add-Content -Path $hashFile -Value "$hash  $relative"
}

Write-Host "Release assets ready under: $releaseRoot"

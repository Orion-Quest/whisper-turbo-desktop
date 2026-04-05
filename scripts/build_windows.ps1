$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function Resolve-ModelPath {
    if ($env:WTD_MODEL_PATH -and (Test-Path $env:WTD_MODEL_PATH)) {
        return (Resolve-Path $env:WTD_MODEL_PATH).Path
    }

    $defaultModel = Join-Path $HOME ".cache\whisper\large-v3-turbo.pt"
    if (Test-Path $defaultModel) {
        return (Resolve-Path $defaultModel).Path
    }

    throw "Bundled model not found. Expected large-v3-turbo.pt under $HOME\.cache\whisper or set WTD_MODEL_PATH."
}

function Resolve-FfmpegPath {
    if ($env:WTD_FFMPEG_PATH -and (Test-Path $env:WTD_FFMPEG_PATH)) {
        return (Resolve-Path $env:WTD_FFMPEG_PATH).Path
    }

    $scoopPath = Join-Path $HOME "scoop\apps\ffmpeg\current\bin\ffmpeg.exe"
    if (Test-Path $scoopPath) {
        return (Resolve-Path $scoopPath).Path
    }

    $command = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($null -ne $command -and (Test-Path $command.Source)) {
        return (Resolve-Path $command.Source).Path
    }

    throw "ffmpeg.exe not found. Install ffmpeg or set WTD_FFMPEG_PATH."
}

$modelPath = Resolve-ModelPath
$ffmpegPath = Resolve-FfmpegPath

Write-Host "Using bundled model: $modelPath"
Write-Host "Using bundled ffmpeg: $ffmpegPath"

Write-Host "Installing build dependencies..."
python -m pip install -r requirements-build.txt

Write-Host "Cleaning previous build output..."
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
if (Test-Path release) { Remove-Item -Recurse -Force release }

$env:WTD_MODEL_PATH = $modelPath
$env:WTD_FFMPEG_PATH = $ffmpegPath

Write-Host "Building WhisperTurboDesktop with PyInstaller..."
python -m PyInstaller --noconfirm packaging\whisper_turbo_desktop.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$distRoot = Join-Path $projectRoot "dist\WhisperTurboDesktop"
if (-not (Test-Path $distRoot)) {
    throw "Expected dist output not found: $distRoot"
}

$releaseRoot = Join-Path $projectRoot "release"
$portableRoot = Join-Path $releaseRoot "WhisperTurboDesktop-windows-x64-portable"
$portableZip = Join-Path $releaseRoot "WhisperTurboDesktop-windows-x64-portable.zip"

New-Item -ItemType Directory -Force -Path $portableRoot | Out-Null
Copy-Item -Path "$distRoot\*" -Destination $portableRoot -Recurse -Force

$sizeBytes = (Get-ChildItem $portableRoot -Recurse -File | Measure-Object -Property Length -Sum).Sum
$sizeGb = [math]::Round($sizeBytes / 1GB, 2)
Write-Host "Portable folder size: $sizeGb GB"

if ($sizeBytes -le 2GB) {
    Write-Host "Creating ZIP release artifact..."
    Compress-Archive -Path "$portableRoot\*" -DestinationPath $portableZip -Force
    Write-Host "ZIP created: $portableZip"
} else {
    Write-Warning "Portable build exceeds 2 GB. GitHub single-asset release upload is not practical for this payload."
    Write-Warning "Use the portable folder directly or publish via external storage / multi-part release strategy."
}

Write-Host "Build completed. Portable folder: $portableRoot"

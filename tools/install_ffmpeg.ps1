$ErrorActionPreference = 'Stop'

$toolsDir = "C:\HomeStudio\tools"
$ffmpegDir = "C:\HomeStudio\tools\ffmpeg"
$zipPath = "C:\HomeStudio\tools\ffmpeg.zip"

if (-not (Test-Path $toolsDir)) {
    New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
}

if ((Test-Path "$ffmpegDir\bin\ffmpeg.exe") -and (Test-Path "$ffmpegDir\bin\ffprobe.exe")) {
    Write-Host "FFmpeg already installed at $ffmpegDir\bin\ffmpeg.exe"
    & "$ffmpegDir\bin\ffmpeg.exe" -version | Select-Object -First 1
    exit 0
}

Write-Host "Downloading FFmpeg portable build..."
$url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

try {
    # Try using curl.exe first for speed
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        curl.exe -L -o $zipPath $url
    } else {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
    }
} catch {
    Write-Host "Fallback download from github release..."
    $fallbackUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    curl.exe -L -o $zipPath $fallbackUrl
}

Write-Host "Extracting FFmpeg..."
$extractTemp = "C:\HomeStudio\tools\temp_ffmpeg"
if (Test-Path $extractTemp) { Remove-Item -Recurse -Force $extractTemp }
Expand-Archive -Path $zipPath -DestinationPath $extractTemp -Force

$extractedFolder = Get-ChildItem -Path $extractTemp | Where-Object { $_.PSIsContainer } | Select-Object -First 1

if ($extractedFolder) {
    if (Test-Path $ffmpegDir) { Remove-Item -Recurse -Force $ffmpegDir }
    Move-Item -Path $extractedFolder.FullName -Destination $ffmpegDir
}

Remove-Item -Recurse -Force $extractTemp -ErrorAction SilentlyContinue
Remove-Item -Force $zipPath -ErrorAction SilentlyContinue

Write-Host "Verifying FFmpeg..."
& "$ffmpegDir\bin\ffmpeg.exe" -version | Select-Object -First 1
& "$ffmpegDir\bin\ffprobe.exe" -version | Select-Object -First 1

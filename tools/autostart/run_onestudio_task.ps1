# Dedicated OneStudio launcher. Camera secret is machine-DPAPI encrypted with a restricted ACL.
param([ValidateSet('vision', 'api')][string]$Target = 'api', [switch]$Check)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Add-Type -AssemblyName System.Security
$bytes = [Security.Cryptography.ProtectedData]::Unprotect(
    [IO.File]::ReadAllBytes("$root\secrets\camera.machine.dpapi"),
    $null, [Security.Cryptography.DataProtectionScope]::LocalMachine)
try { $env:HOMESTUDIO_CAM_PASSWORD = [Text.Encoding]::UTF8.GetString($bytes).Trim() }
finally { [Array]::Clear($bytes, 0, $bytes.Length) }
if (-not $env:HOMESTUDIO_CAM_PASSWORD) { throw 'Camera credential is empty.' }
$python = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw 'HomeStudio virtual environment is missing.' }
$env:HOMESTUDIO_BASE_DIR = $root
$env:HOMESTUDIO_ORIGINAL_RECORDING = '1'
$env:HOMESTUDIO_API_HOST = '127.0.0.1'
$env:HOMESTUDIO_API_PORT = '8080'
$env:HOMESTUDIO_COOKIE_SECURE = '1'
$env:HOMESTUDIO_DEV_MAIL = '1'
$env:PYTHONUNBUFFERED = '1'
Set-Location $root
if ($Check) {
    & $python -c 'from software.backend.config import PipelineConfig; from pathlib import Path; c=PipelineConfig(); assert c.base_dir == Path.cwd(); assert Path(c.ffmpeg_bin).is_file(); assert Path(c.ffprobe_bin).is_file(); print(c.base_dir)'
    exit $LASTEXITCODE
}
New-Item -ItemType Directory -Force "$root\logs" | Out-Null
$ErrorActionPreference = 'Continue'
while ($true) {
    if ($Target -eq 'vision') { & $python "$root\software\main.py" --no-stdout 2>> "$root\logs\vision.task.log" }
    else { & $python -m software.backend.api 2>> "$root\logs\api.task.log" }
    Add-Content "$root\logs\$Target.task.log" "$(Get-Date -Format s) exited code $LASTEXITCODE; restarting in 10s"
    Start-Sleep -Seconds 10
}

param(
    [string]$Password,
    [string]$CameraIp = "192.168.0.31"
)

if (-not $Password) {
    $Password = $env:HOMESTUDIO_CAM_PASSWORD
}

$env:HOMESTUDIO_CAM_PASSWORD = $Password
$env:HOMESTUDIO_CAM_IP = $CameraIp
$env:PYTHONPATH = "C:\HomeStudio"

$pythonBin = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonBin) {
    $pythonBin = "C:\AlphaStudio\Python311\python.exe"
}

Write-Host "Running HomeStudio Live Pipeline via PowerShell ($pythonBin)..."
& $pythonBin "C:\HomeStudio\software\test_live_pipeline.py"

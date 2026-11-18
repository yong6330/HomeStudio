# Task Scheduler entry point. Decrypts the DPAPI camera secret into this process's environment only,
# then runs the target in the foreground, restarting it on exit (backoff 10s).  -Check only verifies decryption.
param([ValidateSet("vision", "api")][string]$Target = "vision", [switch]$Check)
$root = "C:\HomeStudio"
try {
    $sec = Get-Content "$root\secrets\camera.dpapi" -ErrorAction Stop | ConvertTo-SecureString -ErrorAction Stop
    $passwordPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try {
        $env:HOMESTUDIO_CAM_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPtr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPtr)
    }
    if (-not $env:HOMESTUDIO_CAM_PASSWORD) { throw "Camera secret is empty." }
} catch {
    if ($Check) { [Console]::Error.WriteLine("Camera secret check failed.") }
    throw
}
if ($Check) { "camera secret check ok"; exit 0 }
$env:HOMESTUDIO_CAM_USER = "grok"  # camera account used by the service (DPAPI holds its password)
$env:PYTHONUNBUFFERED = "1"
$env:HOMESTUDIO_ORIGINAL_RECORDING = "1"  # main packet recording; keep snapshot detection
# API binds to this PC's Tailscale IPv4 only (not the LAN), looked up at start so no address lives in Git.
# Falls back to 127.0.0.1 if Tailscale is not up within ~2 min. First-admin signup needs 127.0.0.1.
$ts = $null
for ($i = 0; $i -lt 24 -and -not $ts; $i++) {
    $ts = (& tailscale ip -4 2>$null | Select-Object -First 1)
    if (-not $ts) { Start-Sleep 5 }
}
$env:HOMESTUDIO_API_HOST = if ($ts) { $ts.Trim() } else { "127.0.0.1" }
$env:HOMESTUDIO_API_PORT = "8080"
$env:HOMESTUDIO_DEV_MAIL = "1"  # no mail sender yet: codes go to data\dev_mail.log (owner-only)
New-Item -ItemType Directory -Force "$root\logs" | Out-Null
Set-Location $root
while ($true) {
    if ($Target -eq "vision") { & python "$root\software\main.py" --no-stdout 2>> "$root\logs\vision.task.log" }
    else { & python -m software.backend.api 2>> "$root\logs\api.task.log" }
    Add-Content "$root\logs\$Target.task.log" "$(Get-Date -Format s) exited code $LASTEXITCODE; restarting in 10s"
    Start-Sleep 10
}

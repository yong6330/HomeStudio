# Store the camera password DPAPI-encrypted (Windows user "pc" + this machine only). No plaintext on disk.
#   Interactive:  powershell -File set_cam_secret.ps1
#   Piped:        <password on stdin> | powershell -File set_cam_secret.ps1 -FromStdin
param([switch]$FromStdin)
$dir = "C:\HomeStudio\secrets"
New-Item -ItemType Directory -Force $dir | Out-Null
if ($FromStdin) { $sec = ConvertTo-SecureString ([Console]::In.ReadLine()) -AsPlainText -Force }
else { $sec = Read-Host "Camera password" -AsSecureString }
$sec | ConvertFrom-SecureString | Set-Content -Encoding ASCII "$dir\camera.dpapi"
icacls $dir /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" | Out-Null
"saved $dir\camera.dpapi (DPAPI, user $env:USERNAME)"

# Enable autostart (takes effect at next logon; add -Now to start immediately).
param([switch]$Now)
Get-ScheduledTask -TaskPath "\HomeStudio\" | Enable-ScheduledTask | Select-Object TaskName, State
if ($Now) { Get-ScheduledTask -TaskPath "\HomeStudio\" | Start-ScheduledTask }

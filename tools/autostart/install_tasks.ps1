# Register HomeStudio Vision / API logon tasks for the current user, then leave them DISABLED.
# Logon (not boot) trigger: the DPAPI user key is only available once the user is logged on.
$run = "C:\HomeStudio\tools\autostart\run_task.ps1"
$user = "$env:COMPUTERNAME\$env:USERNAME"  # local account (USERDOMAIN reads WORKGROUP over ssh)
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
foreach ($t in @(@{n = "HomeStudio Vision"; a = "vision"; d = 30}, @{n = "HomeStudio API"; a = "api"; d = 40})) {
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $trigger.Delay = "PT$($t.d)S"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$run`" -Target $($t.a)"
    Register-ScheduledTask -TaskName $t.n -TaskPath "\HomeStudio\" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Disable-ScheduledTask -TaskName $t.n -TaskPath "\HomeStudio\" | Out-Null
}
Get-ScheduledTask -TaskPath "\HomeStudio\" | Select-Object TaskName, State

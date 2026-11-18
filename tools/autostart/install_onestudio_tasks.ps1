# Register only this application's boot tasks. Leave disabled until migration cutover.
#requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$run = Join-Path $PSScriptRoot 'run_onestudio_task.ps1'
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
foreach ($target in @('api', 'vision')) {
    $name = "HomeStudio $target"
    if (Get-ScheduledTask -TaskPath '\HomeStudio\' -TaskName $name -ErrorAction SilentlyContinue) {
        throw "Task already exists: $name. Inspect before replacing it."
    }
}
foreach ($target in @('api', 'vision')) {
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $trigger.Delay = 'PT30S'
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$run`" -Target $target"
    Register-ScheduledTask -TaskName "HomeStudio $target" -TaskPath '\HomeStudio\' `
        -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
    Disable-ScheduledTask -TaskName "HomeStudio $target" -TaskPath '\HomeStudio\' | Out-Null
}

# Stop and disable autostart (running service/API processes started by the tasks are ended).
Get-ScheduledTask -TaskPath "\HomeStudio\" | ForEach-Object { Stop-ScheduledTask -InputObject $_; Disable-ScheduledTask -InputObject $_ } | Select-Object TaskName, State
# Stopping the task ends run_task.ps1 only; end its python children too (HomeStudio service/API only).
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'HomeStudio\\software\\main\.py|software\.backend\.api' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; "stopped pid $($_.ProcessId)" }

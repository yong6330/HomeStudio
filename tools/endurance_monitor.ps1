# P2-07 endurance monitor: samples every N min, writes CSV to C:\HomeStudio\logs. No secrets used.
param([int]$Hours = 8, [int]$IntervalMin = 5)
$base = "C:\HomeStudio"; $logs = "$base\logs"; New-Item -ItemType Directory -Force $logs | Out-Null
$csv = "$logs\endurance_$(Get-Date -Format yyyyMMdd_HHmm).csv"
"timestamp,pid,alive,working_set_mb,private_mb,cpu_total_sec,cpu_pct_interval,handles,temp_buffer_files,snapshot_failures,frames_logged,events_db" | Out-File $csv -Encoding utf8
$end = (Get-Date).AddHours($Hours); $prevCpu = $null; $prevT = $null
$db = if (Test-Path "D:\HomeStudio\data\homestudio.db") { "D:\HomeStudio\data\homestudio.db" } else { "$base\data\homestudio.db" }
$tb = if (Test-Path "D:\HomeStudio\temp_buffer") { "D:\HomeStudio\temp_buffer" } else { "$base\temp_buffer" }
while ((Get-Date) -lt $end) {
  $now = Get-Date; $procId = (Get-Content "$logs\service.pid" -ErrorAction SilentlyContinue)
  $p = if ($procId) { Get-Process -Id $procId -ErrorAction SilentlyContinue } else { $null }
  $cpuPct = ""
  if ($p) { if ($prevCpu -ne $null) { $cpuPct = [math]::Round(100 * ($p.CPU - $prevCpu) / (($now - $prevT).TotalSeconds * [Environment]::ProcessorCount), 2) }; $prevCpu = $p.CPU; $prevT = $now }
  $tbCount = (Get-ChildItem $tb -File -ErrorAction SilentlyContinue | Measure-Object).Count
  $fails = (Select-String -Path "$logs\service.log" -Pattern "Snapshot fetch failed" -ErrorAction SilentlyContinue | Measure-Object).Count
  $last = Select-String -Path "$logs\service.log" -Pattern "(\d+) frames analyzed" -ErrorAction SilentlyContinue | Select-Object -Last 1
  $frames = if ($last) { $last.Matches[0].Groups[1].Value } else { "" }
  $events = & python -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('select count(*) from events').fetchone()[0])" $db 2>$null
  $row = @($now.ToString("s"), $procId, [bool]$p,
    $(if($p){[math]::Round($p.WorkingSet64/1MB,1)}), $(if($p){[math]::Round($p.PrivateMemorySize64/1MB,1)}),
    $(if($p){[math]::Round($p.CPU,1)}), $cpuPct, $(if($p){$p.HandleCount}), $tbCount, $fails, $frames, $events) -join ","
  $row | Out-File $csv -Append -Encoding utf8
  Start-Sleep -Seconds ($IntervalMin * 60)
}

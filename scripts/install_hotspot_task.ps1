param(
    [string]$PythonExe = "$env:USERPROFILE\.conda\envs\tradingagents\python.exe",
    [string]$TaskName = "TnT Nailong Hotspot Radar",
    [string]$RunAt = "19:30"
)

$ErrorActionPreference = "Stop"
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$scanScript = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "run_hotspot_scan.py"))

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}
if (-not (Test-Path -LiteralPath $scanScript)) {
    throw "Scan script not found: $scanScript"
}

$action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$scanScript`"" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $RunAt
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "A-share end-of-day hotspot research scan; no broker connection" `
    -Force

Write-Host "Registered task '$TaskName' at $RunAt on weekdays."

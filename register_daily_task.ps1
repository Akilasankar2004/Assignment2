param(
    [string]$Time = "08:00",
    [string]$TaskName = "Daily Sales Report"
)

$projectDir = $PSScriptRoot
$virtualEnvPython = Join-Path $projectDir ".venv\Scripts\python.exe"
if (Test-Path $virtualEnvPython) {
    $python = $virtualEnvPython
} else {
    $python = (Get-Command python -ErrorAction Stop).Source
}
$parsedTime = [DateTime]::ParseExact($Time, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "-m sales_report" `
    -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -Daily -At $parsedTime
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Generate the daily sales report from Excel files in $projectDir\data" `
    -Force | Out-Null

Write-Host "Registered '$TaskName' to run daily at $Time."
Write-Host "Ensure Ollama is running (or configure OpenRouter in .env) and add Excel files to data."

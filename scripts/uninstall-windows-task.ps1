[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$taskName = "Janio Bot"
$taskPath = "\JanioBot\"
$taskDescription = "Inicia o Janio Bot no login do Windows."
$runnerPath = Join-Path $PSScriptRoot "run-windows.ps1"
$task = Get-ScheduledTask `
    -TaskName $taskName `
    -TaskPath $taskPath `
    -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "A tarefa '$taskPath$taskName' não está instalada."
    exit 0
}

$actions = @($task.Actions)
$isJanioTask = (
    $task.Description -eq $taskDescription -and
    $actions.Count -eq 1 -and
    ([string]$actions[0].Arguments).Contains($runnerPath)
)
if (-not $isJanioTask) {
    throw "A tarefa encontrada não pertence a este projeto; nada foi removido."
}

Stop-ScheduledTask `
    -TaskName $taskName `
    -TaskPath $taskPath `
    -ErrorAction SilentlyContinue
Unregister-ScheduledTask `
    -TaskName $taskName `
    -TaskPath $taskPath `
    -Confirm:$false
Write-Host "Tarefa '$taskPath$taskName' removida."

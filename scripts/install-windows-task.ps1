[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$taskName = "Janio Bot"
$taskPath = "\JanioBot\"
$taskDescription = "Inicia o Janio Bot no login do Windows."
$projectRoot = Split-Path -Parent $PSScriptRoot
$runnerPath = Join-Path $PSScriptRoot "run-windows.ps1"
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$envPath = Join-Path $projectRoot ".env"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path -LiteralPath $runnerPath -PathType Leaf)) {
    throw "Script de inicialização não encontrado em $runnerPath."
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Ambiente virtual não encontrado. Execute a preparação do README primeiro."
}

if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    throw "Arquivo .env não encontrado. Configure o token do Discord primeiro."
}

$existingTask = Get-ScheduledTask `
    -TaskName $taskName `
    -TaskPath $taskPath `
    -ErrorAction SilentlyContinue
if ($null -ne $existingTask) {
    $existingActions = @($existingTask.Actions)
    $isJanioTask = (
        $existingTask.Description -eq $taskDescription -and
        $existingActions.Count -eq 1 -and
        ([string]$existingActions[0].Arguments).Contains($runnerPath)
    )
    if (-not $isJanioTask) {
        throw "Já existe uma tarefa diferente em $taskPath$taskName; nada foi alterado."
    }
}

$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runnerPath`""
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $arguments `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -TaskPath $taskPath `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description $taskDescription `
    -Force | Out-Null

Start-ScheduledTask -TaskName $taskName -TaskPath $taskPath
Start-Sleep -Seconds 2
$startedTask = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath
if ($startedTask.State -ne "Running") {
    $taskInfo = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath $taskPath
    throw (
        "A tarefa foi criada, mas o bot não continuou em execução. " +
        "Resultado: $($taskInfo.LastTaskResult). Consulte o log."
    )
}

Write-Host "Tarefa '$taskPath$taskName' instalada e iniciada."
Write-Host "Logs: $(Join-Path $projectRoot 'logs\janio-bot.log')"

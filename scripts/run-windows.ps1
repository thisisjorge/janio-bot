[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$envPath = Join-Path $projectRoot ".env"
$logDirectory = Join-Path $projectRoot "logs"
$logPath = Join-Path $logDirectory "janio-bot.log"
$rotatedLogPath = Join-Path $logDirectory "janio-bot.log.1"
$maxLogBytes = 5MB

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

try {
    if (
        (Test-Path -LiteralPath $logPath -PathType Leaf) -and
        (Get-Item -LiteralPath $logPath).Length -ge $maxLogBytes
    ) {
        Move-Item -LiteralPath $logPath -Destination $rotatedLogPath -Force
    }

    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "Ambiente virtual não encontrado em $pythonPath. Execute a preparação do README."
    }

    if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
        throw "Arquivo .env não encontrado. Copie .env.example para .env e configure o token."
    }

    Set-Location -LiteralPath $projectRoot
    & $pythonPath -m janio_bot *>> $logPath
    if ($LASTEXITCODE -ne 0) {
        throw "Janio Bot encerrou com o código $LASTEXITCODE."
    }
}
catch {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] $($_.Exception.Message)" | Add-Content -LiteralPath $logPath
    throw
}

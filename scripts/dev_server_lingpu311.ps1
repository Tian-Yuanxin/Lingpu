param(
    [string]$PythonPath = "D:\Anaconda\envs\lingpu311\python.exe"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path -LiteralPath (Join-Path $scriptDir "..")

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Python not found: $PythonPath"
}

$resolvedPythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$envRoot = Split-Path -Parent $resolvedPythonPath
$envPathParts = @(
    $envRoot,
    (Join-Path $envRoot "Scripts"),
    (Join-Path $envRoot "Library\bin"),
    (Join-Path $envRoot "Library\usr\bin")
)

$env:PYTHONIOENCODING = "utf-8"
$env:PATH = (($envPathParts + @($env:PATH)) -join [IO.Path]::PathSeparator)
$env:LINGPU_PYTHON_BIN = $resolvedPythonPath
$env:LINGPU_BASIC_PITCH_BIN = Join-Path $envRoot "Scripts\basic-pitch.exe"
$env:LINGPU_AUDIO_SEPARATOR_BIN = Join-Path $envRoot "Scripts\audio-separator.exe"

Set-Location -LiteralPath $repoRoot
Write-Host "Starting Lingpu at http://127.0.0.1:8000"
& $resolvedPythonPath "scripts\dev_server.py"

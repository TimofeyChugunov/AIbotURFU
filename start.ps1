$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$interpreter = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $interpreter)) {
    throw 'Сначала создайте .venv и установите requirements.txt по инструкции README.md.'
}
& $interpreter server.py

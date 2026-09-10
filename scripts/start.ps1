$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$projectPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Primero instala el entorno con uv sync --extra dev --frozen. Consulta README.md.'
}
& $projectPython -m app
exit $LASTEXITCODE

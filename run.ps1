# Lanceur du pipeline TikTok.
# Usage :
#   .\run.ps1 projets\mon-sujet
#   .\run.ps1 projets\mon-sujet --no-music
#   .\run.ps1 projets\mon-sujet --no-eleven
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Projet,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Extra
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Resoudre le vrai python (l'alias Microsoft Store est ignore)
$py = Get-Command python -ErrorAction SilentlyContinue |
      Where-Object { $_.Source -notmatch "WindowsApps" } |
      Select-Object -First 1 -ExpandProperty Source
if (-not $py) {
    $py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
}
if (-not (Test-Path $py)) {
    Write-Error "Python introuvable. Installe Python 3.12 ou ajuste run.ps1."
    exit 1
}

& $py -m pipeline $Projet @Extra

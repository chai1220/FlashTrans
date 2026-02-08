$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ProjectRoot

if ([string]::IsNullOrWhiteSpace($env:APP_VERSION)) {
  $env:APP_VERSION = "dev"
}

& (Join-Path $ProjectRoot "scripts\\build_portable.ps1")

$Iscc = $null
if (!( [string]::IsNullOrWhiteSpace($env:INNO_SETUP_ISCC) ) -and (Test-Path $env:INNO_SETUP_ISCC)) {
  $Iscc = $env:INNO_SETUP_ISCC
}

if ([string]::IsNullOrWhiteSpace($Iscc) -and !( [string]::IsNullOrWhiteSpace($env:INNO_SETUP_HOME) )) {
  $Candidate = Join-Path $env:INNO_SETUP_HOME "ISCC.exe"
  if (Test-Path $Candidate) { $Iscc = $Candidate }
}

if ([string]::IsNullOrWhiteSpace($Iscc)) {
  $Iscc = (Get-Command "iscc.exe" -ErrorAction SilentlyContinue).Source
}

if ([string]::IsNullOrWhiteSpace($Iscc)) {
  $Candidate = "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe"
  if (Test-Path $Candidate) { $Iscc = $Candidate }
}

if ([string]::IsNullOrWhiteSpace($Iscc)) {
  throw "Inno Setup compiler not found. Install Inno Setup 6 and ensure ISCC.exe is on PATH."
}

$OutputDir = Join-Path $ProjectRoot "Output"
$SetupPath = Join-Path $OutputDir ("FlashTrans-Setup-{0}.exe" -f $env:APP_VERSION)
Get-ChildItem -Path $OutputDir -Filter "FlashTrans-Setup-*.exe" -ErrorAction SilentlyContinue | Where-Object { $_.FullName -ne $SetupPath } | Remove-Item -Force -ErrorAction SilentlyContinue

& $Iscc (Join-Path $ProjectRoot "installer\\FlashTrans.iss")
Write-Host (Join-Path $ProjectRoot "Output")

$ErrorActionPreference = "Stop"

param(
  [string]$Flavor,
  [string]$Version
)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ProjectRoot

if (-not [string]::IsNullOrWhiteSpace($Flavor)) { $env:FLASHTRANS_FLAVOR = $Flavor }
if (-not [string]::IsNullOrWhiteSpace($Version)) { $env:APP_VERSION = $Version }
if ([string]::IsNullOrWhiteSpace($env:APP_VERSION)) { $env:APP_VERSION = "dev" }

& (Join-Path $ProjectRoot "scripts\\build_portable.ps1") -Flavor $env:FLASHTRANS_FLAVOR -Version $env:APP_VERSION

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
$Flavor = $env:FLASHTRANS_FLAVOR
if ([string]::IsNullOrWhiteSpace($Flavor)) { $Flavor = "opus" }
$Flavor = $Flavor.ToLower().Trim()
$AppName = "FlashTrans"
if ($Flavor -eq "nllb") { $AppName = "FlashTrans-NLLB" }
if ($Flavor -eq "qwen") { $AppName = "FlashTrans-Qwen" }

$SetupPath = Join-Path $OutputDir ("{0}-Setup-{1}.exe" -f $AppName, $env:APP_VERSION)
Get-ChildItem -Path $OutputDir -Filter "$AppName-Setup-*.exe" -ErrorAction SilentlyContinue | Where-Object { $_.FullName -ne $SetupPath } | Remove-Item -Force -ErrorAction SilentlyContinue

& $Iscc (Join-Path $ProjectRoot "installer\\FlashTrans.iss")
Write-Host (Join-Path $ProjectRoot "Output")

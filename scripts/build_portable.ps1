param(
  [string]$Flavor,
  [string]$Version
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ProjectRoot
$VenvPy = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"
$VenvPip = Join-Path $ProjectRoot ".venv\\Scripts\\pip.exe"

$CacheRoot = Join-Path $ProjectRoot ".cache"
$TmpRoot = Join-Path $ProjectRoot ".tmp"
if (!(Test-Path $CacheRoot)) { New-Item -ItemType Directory -Path $CacheRoot | Out-Null }
if (!(Test-Path $TmpRoot)) { New-Item -ItemType Directory -Path $TmpRoot | Out-Null }

$env:PIP_CACHE_DIR = (Join-Path $CacheRoot "pip")
$env:HF_HOME = (Join-Path $CacheRoot "huggingface")
$env:HF_HUB_CACHE = (Join-Path $CacheRoot "huggingface\\hub")
$env:TEMP = $TmpRoot
$env:TMP = $TmpRoot

if (!(Test-Path $VenvPy)) {
  py -3 -m venv (Join-Path $ProjectRoot ".venv")
}

& $VenvPy -m pip install -U pip
& $VenvPy -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
$FlavorForDeps = $Flavor
if ([string]::IsNullOrWhiteSpace($FlavorForDeps)) { $FlavorForDeps = $env:FLASHTRANS_FLAVOR }
if ($FlavorForDeps -and $FlavorForDeps.ToLower().Trim() -eq "qwen") {
  & $VenvPy -m pip install -r (Join-Path $ProjectRoot "requirements-qwen.txt")

  $ModelsDir = Join-Path $ProjectRoot "models"
  if (!(Test-Path $ModelsDir)) { New-Item -ItemType Directory -Path $ModelsDir | Out-Null }
  $QwenModel = Join-Path $ModelsDir "qwen3-1.7b-q4.gguf"
  if (!(Test-Path $QwenModel)) {
    if ($env:FLASHTRANS_SKIP_MODEL_DOWNLOAD -ne "1") {
      & $VenvPy -m pip install -r (Join-Path $ProjectRoot "requirements-download.txt")
      & $VenvPy (Join-Path $ProjectRoot "scripts\\download_models.py") --models-dir $ModelsDir --qwen
    }
  }
}
& $VenvPy -m pip install -U pyinstaller

$BuildDir = Join-Path $ProjectRoot "build"
$DistDir = Join-Path $ProjectRoot "dist"
$OutputDir = Join-Path $ProjectRoot "Output"
$AssetsDir = Join-Path $ProjectRoot "assets"
$IconPath = Join-Path $AssetsDir "icon.ico"

if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
if (!(Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir | Out-Null }
if (!(Test-Path $AssetsDir)) { New-Item -ItemType Directory -Path $AssetsDir | Out-Null }

& $VenvPy (Join-Path $ProjectRoot "scripts\\generate_icon.py") --out $IconPath
if (!(Test-Path $IconPath)) { throw "Icon generation failed: $IconPath" }

if (-not [string]::IsNullOrWhiteSpace($Flavor)) {
  $env:FLASHTRANS_FLAVOR = $Flavor
}
if (-not [string]::IsNullOrWhiteSpace($Version)) {
  $env:APP_VERSION = $Version
}

& $VenvPy -m PyInstaller -y (Join-Path $ProjectRoot "FlashTrans.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed (exit code: $LASTEXITCODE)." }

$Version = $env:APP_VERSION
if ([string]::IsNullOrWhiteSpace($Version)) { $Version = "dev" }

$Flavor = $env:FLASHTRANS_FLAVOR
if ([string]::IsNullOrWhiteSpace($Flavor)) { $Flavor = "opus" }
$Flavor = $Flavor.ToLower().Trim()

$AppName = "FlashTrans"
if ($Flavor -eq "nllb") { $AppName = "FlashTrans-NLLB" }
if ($Flavor -eq "qwen") { $AppName = "FlashTrans-Qwen" }

$PortableFolder = Join-Path $DistDir $AppName
$ZipPath = Join-Path $OutputDir ("{0}-Portable-{1}.zip" -f $AppName, $Version)
Get-ChildItem -Path $OutputDir -Filter "$AppName-Portable-*.zip" -ErrorAction SilentlyContinue | Where-Object { $_.FullName -ne $ZipPath } | Remove-Item -Force -ErrorAction SilentlyContinue
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
if (!(Test-Path $PortableFolder)) { throw "dist output folder not found: $PortableFolder" }

$BaseLib = Join-Path $PortableFolder "_internal\\base_library.zip"
if (Test-Path $BaseLib) {
  $deadline = (Get-Date).AddSeconds(90)
  while ($true) {
    try {
      $fs = [System.IO.File]::Open($BaseLib, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
      $fs.Dispose()
      break
    } catch {
      if ((Get-Date) -ge $deadline) { break }
      Start-Sleep -Milliseconds 500
    }
  }
}

$Ok = $false
for ($i = 0; $i -lt 20; $i++) {
  try {
    Compress-Archive -Path (Join-Path $PortableFolder "*") -DestinationPath $ZipPath -Force
    $Ok = $true
    break
  } catch {
    if ($i -ge 19) { throw }
    Start-Sleep -Milliseconds ([Math]::Min(3000, 400 + ($i * 200)))
  }
}
if (-not $Ok) { throw "Failed to create zip: $ZipPath" }
Write-Host $ZipPath

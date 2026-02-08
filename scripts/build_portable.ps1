$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ProjectRoot
$VenvPy = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"
$VenvPip = Join-Path $ProjectRoot ".venv\\Scripts\\pip.exe"

if (!(Test-Path $VenvPy)) {
  py -3 -m venv (Join-Path $ProjectRoot ".venv")
}

& $VenvPy -m pip install -U pip
& $VenvPy -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
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

& $VenvPy -m PyInstaller -y (Join-Path $ProjectRoot "FlashTrans.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed (exit code: $LASTEXITCODE)." }

$Version = $env:APP_VERSION
if ([string]::IsNullOrWhiteSpace($Version)) { $Version = "dev" }

$PortableFolder = Join-Path $DistDir "FlashTrans"
$ZipPath = Join-Path $OutputDir ("FlashTrans-Portable-{0}.zip" -f $Version)
Get-ChildItem -Path $OutputDir -Filter "FlashTrans-Portable-*.zip" -ErrorAction SilentlyContinue | Where-Object { $_.FullName -ne $ZipPath } | Remove-Item -Force -ErrorAction SilentlyContinue
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
if (!(Test-Path $PortableFolder)) { throw "dist\\FlashTrans output folder not found: $PortableFolder" }

Compress-Archive -Path (Join-Path $PortableFolder "*") -DestinationPath $ZipPath
Write-Host $ZipPath

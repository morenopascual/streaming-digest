# Compila la app de Windows:  dist\Ac2ality Digest\Ac2ality Digest.exe  (+ zip para compartir)
# Uso (PowerShell, desde la raíz del repo):  .\scripts\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

py -m pip install --upgrade -r requirements-desktop.txt
py scripts/make_icons.py

# Carpetas de trabajo cortas: evitan el límite de 260 caracteres de Windows
# cuando el repositorio está en una ruta larga (por ejemplo, dentro de OneDrive).
$work = Join-Path $env:TEMP "ac2-build"
$out = Join-Path $env:TEMP "ac2-dist"
py -m PyInstaller app/ac2ality.spec --noconfirm --clean --workpath $work --distpath $out
if ($LASTEXITCODE -ne 0) { throw "PyInstaller ha fallado" }

New-Item -ItemType Directory -Force dist | Out-Null
Compress-Archive -Path (Join-Path $out "Ac2ality Digest") -DestinationPath "dist\Ac2ality-Digest-Windows.zip" -Force

Write-Host ""
Write-Host "Listo: dist\Ac2ality-Digest-Windows.zip" -ForegroundColor Green
Write-Host "Descomprímelo y abre 'Ac2ality Digest\Ac2ality Digest.exe'." -ForegroundColor Green

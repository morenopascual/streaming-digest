#!/usr/bin/env bash
# Compila la app de macOS: dist/Ac2ality Digest.app (+ .zip para compartir)
# Uso (Terminal de Mac, desde la raíz del repo):  ./scripts/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install --upgrade -r requirements-desktop.txt
python3 scripts/make_icons.py
python3 -m PyInstaller app/ac2ality.spec --noconfirm --clean

# Firma ad-hoc: evita el aviso de "aplicación dañada" en Apple Silicon.
codesign --force --deep --sign - "dist/Ac2ality Digest.app" || true
ditto -c -k --keepParent "dist/Ac2ality Digest.app" "dist/Ac2ality-Digest-macOS.zip"

echo ""
echo "Listo: dist/Ac2ality Digest.app  y  dist/Ac2ality-Digest-macOS.zip"

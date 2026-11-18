# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera la app autocontenida.
#   Windows → dist/Ac2ality Digest/Ac2ality Digest.exe  (carpeta autocontenida, sin consola)
#             Se usa carpeta y no un único .exe: arranca más rápido y los antivirus
#             corporativos no lo confunden con un ejecutable que se autoextrae.
#   macOS   → dist/Ac2ality Digest.app
# Uso:  pyinstaller app/ac2ality.spec --noconfirm   (desde la raíz del repo)
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
APP_NAME = "Ac2ality Digest"
VERSION = "2.0.0"
IS_MAC = sys.platform == "darwin"

datas = [(str(ROOT / "web"), "web")]
datas += collect_data_files("certifi")
datas += collect_data_files("webview")

hiddenimports = ["fetch_digest", "certifi"] + collect_submodules("webview")

a = Analysis(
    [str(ROOT / "app" / "ac2ality_app.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "unittest", "pydoc", "test", "setuptools", "pkg_resources", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if IS_MAC:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name=APP_NAME,
        console=False,
        icon=str(ROOT / "app" / "assets" / "icon.icns"),
    )
    coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME)
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(ROOT / "app" / "assets" / "icon.icns"),
        bundle_identifier="com.ac2ality.digest",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.news",
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
else:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name=APP_NAME,
        console=False,           # sin ventana de terminal
        upx=False,
        icon=str(ROOT / "app" / "assets" / "icon.ico"),
        version=None,
    )
    coll = COLLECT(exe, a.binaries, a.datas, upx=False, name=APP_NAME)

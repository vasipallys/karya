# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path.cwd()
hiddenimports = []
hiddenimports.extend(name for name in collect_submodules("backend") if not name.startswith("backend.tests"))
for package in [
    "langchain_anthropic",
    "langchain_google_genai",
    "langchain_groq",
    "langchain_mistralai",
    "langchain_openai",
    "langgraph",
    "langgraph.checkpoint.sqlite",
    "docx",
    "pptx",
]:
    hiddenimports.extend(collect_submodules(package))

a = Analysis(
    [str(ROOT / "desktop" / "backend_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="storypointer-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

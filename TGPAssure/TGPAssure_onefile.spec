# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for a single-file Windows TGPAssure executable."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = Path(SPECPATH).resolve()

# Application-owned non-Python resources. They are extracted by the one-file
# bootloader to sys._MEIPASS and accessed via core.infrastructure.resource_paths.
datas = [
    (str(project_root / "assets"), "assets"),
    (str(project_root / "migrations"), "migrations"),
]

# Bundle build-time environment configuration into the one-file EXE.
# The runtime loader reads these files from sys._MEIPASS after extraction.
for env_name in (".env", ".env.local"):
    env_file = project_root / env_name
    if env_file.is_file():
        datas.append((str(env_file), "."))

resources_dir = project_root / "resources"
if resources_dir.is_dir():
    datas.append((str(resources_dir), "resources"))

# QtAwesome ships icon-font data that is loaded at runtime.
datas += collect_data_files("qtawesome", include_py_files=False)
# pyproj needs its PROJ database for projected-coordinate hover conversion.
datas += collect_data_files("pyproj", include_py_files=False)

# Some TGPAssure modules are imported dynamically from strings. Explicitly
# collect local package submodules so those runtime paths remain available.
hiddenimports = []
for package in ("core", "modules", "ui", "report"):
    hiddenimports += collect_submodules(package)

# Prevent accidental duplication if a module appears through more than one path.
hiddenimports = sorted(set(hiddenimports))

analysis = Analysis(
    [str(project_root / "run_app.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "pytest_qt",
        "tests",
        "tkinter",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="TGPAssure",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "assets" / "logo" / "logo.ico"),
)

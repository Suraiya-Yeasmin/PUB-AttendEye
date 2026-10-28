# PyInstaller spec: builds the windowed (no console) PUB AttendEye app folder.
#   pyinstaller packaging/attendeye.spec --noconfirm --distpath dist --workpath build
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
ICON = ROOT / "packaging" / "attendeye.ico"

a = Analysis(
    [str(ROOT / "desktop.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "static"), "static"), (str(ROOT / "models"), "models")],
    hiddenimports=collect_submodules("uvicorn") + collect_submodules("app") + ["sqlalchemy.dialects.sqlite"],
    excludes=["tkinter", "matplotlib", "pytest", "scipy", "pandas", "IPython", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PUB AttendEye",
    console=False,                      # no terminal window
    icon=str(ICON) if ICON.exists() else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PUB AttendEye", upx=False)

"""Builds store/hib-remover-ads.zip and installer/HibRemoverAds-Setup.exe from src/.

Run: python installer/build.py
"""
import subprocess
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT, HERE = ROOT / "src", ROOT / "store", ROOT / "installer"
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")

zip_path = OUT / "hib-remover-ads.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(SRC.rglob("*")):
        if p.is_file() and "_metadata" not in p.parts:
            z.write(p, p.relative_to(SRC).as_posix())
print(f"zip: {zip_path.stat().st_size // 1024} KB")

build = HERE / "build"
build.mkdir(exist_ok=True)
logo = Image.open(SRC / "icons" / "on-128.png")
logo.save(build / "logo.png")
logo.save(build / "app.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)])

exe = OUT / "HibRemoverAds-Setup.exe"
subprocess.run([
    str(CSC), "/nologo", "/target:winexe", "/optimize+", f"/out:{exe}",
    f"/win32icon:{build / 'app.ico'}",
    f"/resource:{zip_path},extension.zip", f"/resource:{build / 'logo.png'},logo.png",
    "/r:System.IO.Compression.dll", "/r:System.IO.Compression.FileSystem.dll", "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll",
    str(HERE / "Setup.cs"),
], check=True)
print(f"installer: {exe} ({exe.stat().st_size // 1024} KB)")

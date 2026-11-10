"""Builds the three downloads in store/:

  hib-remover-ads.zip          the browser extension
  HibRemoverAds-Windows.exe    the Windows app that blocks ads in every program (from windows/)
  HibRemoverAds-Setup.exe      the installer, which carries both of the above

Run: python installer/build.py
"""
import gzip
import subprocess
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT, HERE, WIN = ROOT / "src", ROOT / "store", ROOT / "installer", ROOT / "windows"
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

# The Windows app. Its block list is built in, compressed.
res = []
for name in ["block.txt", "allow.txt"]:
    gz = build / (name + ".gz")
    with gzip.GzipFile(gz, "wb", compresslevel=9, mtime=0) as f:
        f.write((WIN / "lists" / name).read_bytes())
    res.append(f"/resource:{gz},{name}.gz")
for state in ["on", "off"]:
    res.append(f"/resource:{SRC / 'icons' / (state + '-128.png')},{state}.png")
app = OUT / "HibRemoverAds-Windows.exe"
subprocess.run([
    str(CSC), "/nologo", "/target:winexe", "/optimize+", "/platform:anycpu", f"/out:{app}",
    f"/win32icon:{build / 'app.ico'}", f"/win32manifest:{WIN / 'app.manifest'}", *res,
    "/r:System.ServiceProcess.dll", "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll", "/r:System.Core.dll",
    *[str(p) for p in sorted(WIN.glob("*.cs"))],
], check=True)
print(f"windows app: {app} ({app.stat().st_size // 1024} KB)")

exe = OUT / "HibRemoverAds-Setup.exe"
subprocess.run([
    str(CSC), "/nologo", "/target:winexe", "/optimize+", f"/out:{exe}",
    f"/win32icon:{build / 'app.ico'}",
    f"/resource:{zip_path},extension.zip", f"/resource:{build / 'logo.png'},logo.png", f"/resource:{app},windows.exe",
    "/r:System.IO.Compression.dll", "/r:System.IO.Compression.FileSystem.dll", "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll",
    str(HERE / "Setup.cs"),
], check=True)
print(f"installer: {exe} ({exe.stat().st_size // 1024} KB)")

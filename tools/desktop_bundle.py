"""Builds a "Hib Remover Ads" folder on the Desktop with everything in one place.

  1 - Install            installer, zip, checksums
  2 - Source code        a git clone of the project, linked to GitHub
  3 - Test results       real-site and speed results, screenshots
  4 - Images             README images, store images
  START HERE.html        a guide to all of it

Run: python tools/desktop_bundle.py
"""
import hashlib
import html
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def desktop():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
        capture_output=True, text=True, check=True).stdout.strip()
    return Path(out)


DEST = desktop() / "Hib Remover Ads"
REPO = "https://github.com/ZakariaHibaoui2/hib-remover-ads"
SITE = "https://zakariahibaoui2.github.io/hib-remover-ads/"


def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def main():
    if DEST.exists():
        # Git stores objects read-only; clear the flag so they can be removed.
        def force(func, path, _):
            os.chmod(path, 0o666)
            func(path)
        shutil.rmtree(DEST, onexc=force)
    DEST.mkdir(parents=True)
    version = json.loads((ROOT / "src" / "manifest.json").read_text())["version"]

    inst = DEST / "1 - Install"
    sums = []
    for name in ["HibRemoverAds-Setup.exe", "hib-remover-ads.zip"]:
        copy(ROOT / "store" / name, inst / name)
        sums.append(f"{hashlib.sha256((inst / name).read_bytes()).hexdigest()}  {name}")
    (inst / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")

    subprocess.run(["git", "clone", "-q", str(ROOT), str(DEST / "2 - Source code")], check=True)
    subprocess.run(["git", "-C", str(DEST / "2 - Source code"), "remote", "set-url", "origin", REPO + ".git"], check=True)

    res = DEST / "3 - Test results"
    for f in ["real_sites_results.json", "performance_results.json"]:
        if (ROOT / "tests" / f).exists():
            copy(ROOT / "tests" / f, res / f)
    copy(ROOT / "tests" / "screenshots", res / "screenshots")

    img = DEST / "4 - Images"
    copy(ROOT / "docs" / "assets", img / "README and website")
    for f in (ROOT / "store").rglob("*.png"):
        copy(f, img / "Store listing" / f.name)

    (DEST / "START HERE.html").write_text(guide(version), encoding="utf-8")
    total = sum(f.stat().st_size for f in DEST.rglob("*") if f.is_file())
    print(f"{DEST}  ({total // 1_000_000} MB)")


def guide(version):
    perf = json.loads((ROOT / "tests" / "performance_results.json").read_text())
    sites = json.loads((ROOT / "docs" / "results.json").read_text())
    secs = lambda ms: f"{ms:.0f} ms" if ms < 1000 else f"{ms / 1000:.1f} s"
    pct = lambda a, b: f"{round((b - a) / a * 100):+d}%" if a else "-"
    perf_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{secs(r['load'][0])} → <b>{secs(r['load'][1])}</b></td>"
        f"<td>{pct(*r['cpu'])}</td><td>{pct(*r['heap'])}</td><td>{int(r['requests'][0]):,} → {int(r['requests'][1]):,}</td></tr>"
        for name, r in perf.items() if None not in r["load"])
    site_rows = "".join(
        f"<tr><td>{html.escape(s['name'])}</td><td>{s['without']:,}</td><td><b>{s['with']:,}</b></td>"
        f"<td>{'Yes' if s['intact'] else 'Check'}</td></tr>" for s in sites["sites"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hib Remover Ads: start here</title>
<style>
:root {{ --deep:#10272b; --tide:#183a3f; --line:#2a5057; --foam:#e4f0ec; --kelp:#9dbbb3; --amber:#f3b23c; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--deep); color:var(--foam); font:16px/1.6 "Segoe UI", system-ui, sans-serif; }}
main {{ max-width:860px; margin:0 auto; padding:56px 24px 80px; }}
h1 {{ font-size:48px; line-height:1; margin:18px 0 10px; letter-spacing:-1px; }}
h2 {{ font-size:26px; margin:48px 0 12px; }}
p, li {{ color:var(--kelp); }} b, strong {{ color:var(--foam); }}
a {{ color:var(--amber); }}
.links {{ display:flex; flex-wrap:wrap; gap:10px; margin:24px 0 8px; }}
.links a {{ background:var(--tide); color:var(--foam); text-decoration:none; padding:10px 16px; border-radius:999px; font-weight:600; }}
.links a.primary {{ background:var(--amber); color:var(--deep); }}
code {{ background:var(--tide); padding:2px 7px; border-radius:5px; color:var(--foam); font-size:14px; }}
pre {{ background:var(--tide); padding:16px; border-radius:12px; overflow-x:auto; }} pre code {{ padding:0; }}
table {{ width:100%; border-collapse:collapse; font-size:15px; }}
th {{ text-align:left; color:var(--kelp); font-weight:600; border-bottom:1px solid var(--line); padding:8px 8px 8px 0; }}
td {{ border-bottom:1px solid var(--line); padding:9px 8px 9px 0; }}
.map td:first-child {{ white-space:nowrap; font-weight:600; }}
</style></head><body><main>
<img src="2 - Source code/src/icons/on-128.png" width="64" alt="">
<h1>Hib Remover Ads</h1>
<p>Version {version}. A free, open-source ad blocker for Chrome, Edge, Brave and Opera. Everything you built is in this folder.</p>
<div class="links">
  <a class="primary" href="{SITE}">Website</a>
  <a href="{REPO}">GitHub repository</a>
  <a href="{REPO}/releases/latest">Latest release</a>
  <a href="{REPO}/actions">Automatic checks</a>
</div>

<h2>What's in this folder</h2>
<table class="map">
<tr><td>1 - Install</td><td>The Windows installer, the zip for any system, and their SHA-256 checksums.</td></tr>
<tr><td>2 - Source code</td><td>The full project with its history, linked to GitHub. Edit here, then <code>git push</code>.</td></tr>
<tr><td>3 - Test results</td><td>Real-site blocking results, speed results and screenshots.</td></tr>
<tr><td>4 - Images</td><td>The README images, the demo GIF, the social preview and the store listing images.</td></tr>
</table>

<h2>Install it in a browser</h2>
<ol>
<li>Run <b>1 - Install\\HibRemoverAds-Setup.exe</b>. If Windows warns you, click <b>More info</b>, then <b>Run anyway</b>.</li>
<li>Pick the browser and click <b>Install</b>. Its extensions page opens and the folder path is copied.</li>
<li>Turn on <b>Developer mode</b>, click <b>Load unpacked</b>, press <b>Ctrl+V</b>, click <b>Select Folder</b>.</li>
</ol>
<p>On your own PC it's already installed from <code>%LOCALAPPDATA%\\Hib Remover Ads\\extension</code>.</p>

<h2>Speed: with and without Hib Remover Ads</h2>
<table><tr><th>Site</th><th>Load time</th><th>CPU</th><th>Memory</th><th>Requests</th></tr>{perf_rows}</table>

<h2>Ads blocked on real sites</h2>
<p>Ad files downloaded per page, measured {html.escape(sites['date'])}.</p>
<table><tr><th>Site</th><th>Without</th><th>With</th><th>Page intact</th></tr>{site_rows}</table>

<h2>Publish a new version</h2>
<p>From <b>2 - Source code</b>, in a terminal:</p>
<pre><code>python tools/filterlists.py --fetch     # newest filter lists
python tests/test_extension.py          # 20 checks must pass
# bump "version" in src/manifest.json and add it to CHANGELOG.md
git commit -am "Release X.Y.Z" && git tag vX.Y.Z && git push && git push origin vX.Y.Z</code></pre>
<p>Pushing the tag makes GitHub build the installer and zip on its own servers and publish them with checksums. Every Monday GitHub also opens a pull request with refreshed filter lists; merge it, then tag a release.</p>

<h2>One thing to do by hand</h2>
<p>Set the social preview so shared links show a card: GitHub repository → <b>Settings</b> → <b>Social preview</b> → upload <b>4 - Images\\README and website\\social-preview.png</b>.</p>
</main></body></html>
"""


if __name__ == "__main__":
    main()

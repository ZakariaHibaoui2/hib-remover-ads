"""Captures the images used in README.md into docs/assets/.

  popup.png      the real popup on speedtest.net, at 2x
  site.png       the website's hero
  demo.gif       the website's hero as ads are cleared on scroll

Run: python tools/readme_assets.py            (needs network and Playwright)
     python tools/readme_assets.py popup      only the popup image
"""
import io
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "src"
OUT = ROOT / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)
SITE = "https://zakariahibaoui2.github.io/hib-remover-ads/"


def popup(p):
    with tempfile.TemporaryDirectory() as profile:
        ctx = p.chromium.launch_persistent_context(
            profile, channel="chromium", headless=True, device_scale_factor=2,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}", "--lang=en"])
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
        ext_id = sw.url.split("/")[2]
        page = ctx.new_page()
        page.goto("https://www.speedtest.net", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(9000)
        tab_id = sw.evaluate("chrome.tabs.query({url: 'https://www.speedtest.net/*'}).then(t => t[0].id)")
        pop = ctx.new_page()
        pop.add_init_script(f"""
          if (location.protocol === 'chrome-extension:') {{
            const q = chrome.tabs.query.bind(chrome.tabs);
            chrome.tabs.query = () => q({{}}).then(ts => ts.filter(t => t.id === {tab_id}));
          }}""")
        pop.set_viewport_size({"width": 340, "height": 600})
        pop.goto(f"chrome-extension://{ext_id}/popup/popup.html")
        pop.wait_for_timeout(2200)
        h = pop.evaluate("document.body.scrollHeight")
        pop.set_viewport_size({"width": 340, "height": h})
        pop.wait_for_timeout(300)
        pop.screenshot(path=str(OUT / "popup.png"))
        ctx.close()


def site_and_gif(p):
    b = p.chromium.launch(args=["--use-gl=angle", "--ignore-gpu-blocklist"])
    page = b.new_page(viewport={"width": 1280, "height": 760})
    page.goto(SITE, wait_until="networkidle")
    page.wait_for_timeout(2600)
    page.screenshot(path=str(OUT / "site.png"))
    span = page.evaluate("document.getElementById('track').offsetHeight - innerHeight")
    frames = []
    hold = lambda img, n: frames.extend([img] * n)
    grab = lambda: Image.open(io.BytesIO(page.screenshot())).convert("RGB").resize((800, 475), Image.LANCZOS)
    hold(grab(), 12)
    steps = 48
    for i in range(1, steps + 1):
        page.evaluate(f"window.scrollTo(0, {int(span * i / steps)})")
        page.wait_for_timeout(110)
        frames.append(grab())
    page.wait_for_timeout(900)
    hold(grab(), 18)
    b.close()
    pal = frames[len(frames) // 2].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(OUT / "demo.gif", save_all=True, append_images=q[1:], duration=70, loop=0, optimize=True)


with sync_playwright() as p:
    popup(p)
    if sys.argv[1:] != ["popup"]:
        site_and_gif(p)
for f in sorted(OUT.iterdir()):
    print(f.name, f.stat().st_size // 1024, "KB")

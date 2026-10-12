"""Builds the Chrome Web Store upload zip and listing images into store/.

Run after `node tools/build.mjs` and `python tests/test_real_sites.py`
(the screenshots reuse that test's before/after captures).
"""
import base64
import json
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
STORE = ROOT / "store"
SITES = ROOT / "tests" / "screenshots" / "sites"
STORE.mkdir(exist_ok=True)

manifest = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
NAME, VERSION = manifest["name"], manifest["version"]


def data_uri(path):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


ICON = data_uri(SRC / "icons" / "on-128.png")

BASE_CSS = """
* { box-sizing: border-box; margin: 0; }
body { width: %dpx; height: %dpx; overflow: hidden; background: #10272b; color: #e4f0ec;
       font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif; }
"""


def comparison(title, plain, hush):
    return f"""<style>{BASE_CSS % (1280, 800)}
      .head {{ padding: 44px 56px 28px; display: flex; align-items: center; gap: 18px; }}
      .head img {{ width: 52px; height: 52px; }}
      h1 {{ font-size: 38px; font-weight: 600; letter-spacing: -0.02em; }}
      .pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; padding: 30px 56px 0; }}
      .shot img {{ width: 100%; display: block; border-radius: 10px; }}
      .tag {{ display: inline-block; margin-bottom: 14px; padding: 6px 12px; border-radius: 6px;
              font: 600 16px system-ui; }}
      .before {{ background: #ef6f6c; color: #fff; }}
      .after {{ background: #f3b23c; color: #10272b; }}
    </style>
    <div class="head"><img src="{ICON}"><h1>{title}</h1></div>
    <div class="pair">
      <div class="shot"><span class="tag before">Without {NAME}</span><img src="{data_uri(plain)}"></div>
      <div class="shot"><span class="tag after">With {NAME}</span><img src="{data_uri(hush)}"></div>
    </div>"""


def popup_scene(popup_png, site_png):
    return f"""<style>{BASE_CSS % (1280, 800)}
      .site {{ position: absolute; top: 0; bottom: 0; left: 640px; right: 0;
               background: url({data_uri(site_png)}) top left / cover; }}
      .card {{ position: absolute; right: 100px; top: 170px; border-radius: 12px; overflow: hidden;
               box-shadow: 0 30px 80px rgba(0,0,0,.55); }}
      .card img {{ display: block; width: 400px; }}
      .copy {{ position: absolute; left: 72px; top: 230px; width: 500px; }}
      h1 {{ font-size: 46px; line-height: 1.1; font-weight: 600; letter-spacing: -0.02em; }}
      p {{ margin-top: 20px; font-size: 21px; line-height: 1.5; color: #c8ddd7; }}
    </style>
    <div class="site"></div>
    <div class="copy"><h1>See what was blocked. Pause any site in one click.</h1>
      <p>The counter shows ads blocked on the page you're on and since you installed.
         If a site needs ads to work, pause it there and keep blocking everywhere else.</p></div>
    <div class="card"><img src="{data_uri(popup_png)}"></div>"""


def promo_tile():
    return f"""<style>{BASE_CSS % (440, 280)}
      .wrap {{ height: 100%; display: flex; flex-direction: column; justify-content: center; padding: 0 34px; }}
      img {{ width: 64px; height: 64px; }}
      h1 {{ margin-top: 18px; font-size: 32px; font-weight: 600; letter-spacing: -0.02em; }}
      p {{ margin-top: 6px; font-size: 17px; color: #f3b23c; }}
    </style>
    <div class="wrap"><img src="{ICON}"><h1>{NAME}</h1><p>No ads on YouTube or the web</p></div>"""


def render(page, html, out, size):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.set_content(html)
    page.wait_for_timeout(300)
    page.screenshot(path=str(out))


def build_popup_png(p):
    """Renders the real popup with sample numbers, in dark mode, at 2x."""
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 320, "height": 330}, device_scale_factor=2,
                            color_scheme="dark")
    page.goto((SRC / "popup" / "popup.html").as_uri())
    page.evaluate("""() => {
      document.body.dataset.state = 'on';
      document.getElementById('host').textContent = 'allrecipes.com';
      document.getElementById('status').textContent = 'Blocking ads on this site';
      document.getElementById('page').textContent = '37';
      document.getElementById('page-label').textContent = 'ads blocked on this page';
      document.getElementById('total').textContent = '12,480';
    }""")
    out = STORE / "_popup.png"
    page.screenshot(path=str(out))
    browser.close()
    return out


def main():
    with sync_playwright() as p:
        popup = build_popup_png(p)
        browser = p.chromium.launch()
        page = browser.new_page()
        render(page, comparison("Ads gone, pages intact", SITES / "speedtest-plain.png", SITES / "speedtest-hush.png"),
               STORE / "screenshot-1.png", (1280, 800))
        hush_yahoo = SITES / "yahoo-hush-v2.png"
        render(page, comparison("Works on news, recipes, weather and more", SITES / "yahoo-plain.png",
                                hush_yahoo if hush_yahoo.exists() else SITES / "yahoo-hush.png"),
               STORE / "screenshot-2.png", (1280, 800))
        render(page, popup_scene(popup, SITES / "allrecipes-hush.png"), STORE / "screenshot-3.png", (1280, 800))
        render(page, promo_tile(), STORE / "promo-small-440x280.png", (440, 280))
        browser.close()
    popup.unlink()

    zip_path = STORE / f"{NAME.lower().replace(' ', '-')}-{VERSION}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SRC.rglob("*")):
            # Chrome writes _metadata/ when loading unpacked; the store rejects it.
            if f.is_file() and not f.relative_to(SRC).parts[0].startswith("_"):
                z.write(f, f.relative_to(SRC).as_posix())
    print("wrote", zip_path.name, "and store images to", STORE)


if __name__ == "__main__":
    main()

"""Draws the five 1280x800 store screenshots from tools/store_images.html.

Run: python tools/store_images.py   ->  store/listing/screenshot-1.png ... -5.png
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "tools" / "store_images.html").as_uri()
OUT = ROOT / "store" / "listing"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        for n in range(1, 6):
            page.goto(f"{PAGE}?s={n}")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=OUT / f"screenshot-{n}.png")
            print(OUT / f"screenshot-{n}.png")
        browser.close()


if __name__ == "__main__":
    main()

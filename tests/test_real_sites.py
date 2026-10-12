"""Loads real ad-heavy sites with and without Hush and compares ad traffic and
visible ad slots. Network-dependent; results vary by region and over time.

Run: python tests/test_real_sites.py
"""
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "src"
SHOTS = ROOT / "tests" / "screenshots" / "sites"
SHOTS.mkdir(parents=True, exist_ok=True)

SITES = [
    "https://www.cnn.com",
    "https://www.forbes.com",
    "https://www.dailymail.co.uk/home/index.html",
    "https://www.speedtest.net",
    "https://www.accuweather.com",
    "https://www.theguardian.com/international",
    "https://www.yahoo.com",
    "https://www.fandom.com",
    "https://www.imdb.com",
    "https://www.hespress.com",
    "https://www.allrecipes.com",
    "https://www.wikihow.com/Main-Page",
]

rules = json.loads((EXT / "rules" / "ads.json").read_text())
AD_DOMAINS = rules[0]["condition"]["requestDomains"]


def is_ad_host(url):
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in AD_DOMAINS)


# Ad slots measured with widely used markers, independent of whether they're hidden.
VISIBLE_ADS_JS = """() => {
  const sel = 'ins.adsbygoogle, [id^="google_ads_iframe"], [id^="div-gpt-ad"], [data-google-query-id],'
    + ' iframe[src*="doubleclick"], iframe[src*="googlesyndication"], iframe[src*="amazon-adsystem"],'
    + ' iframe[id^="google_ads_"], [id^="taboola-"], .trc_related_container, .OUTBRAIN, [data-ad-slot]';
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 20 && r.height > 20 && s.display !== 'none' && s.visibility !== 'hidden'; };
  return [...document.querySelectorAll(sel)].filter(vis).length;
}"""


def run(p, url, with_ext, tag):
    with tempfile.TemporaryDirectory() as profile:
        args = [f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"] if with_ext else []
        ctx = p.chromium.launch_persistent_context(
            profile, channel="chromium", headless=True, args=args,
            viewport={"width": 1366, "height": 900}, locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        )
        if with_ext:
            sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
            for _ in range(40):
                if sw.evaluate("chrome.scripting.getRegisteredContentScripts().then(s => s.length)") == 3:
                    break
                ctx.pages[0].wait_for_timeout(250) if ctx.pages else None
        page = ctx.new_page()
        stats = {"ad_requests": 0, "blocked": 0, "loaded_ad": 0}

        def on_request(r):
            if is_ad_host(r.url):
                stats["ad_requests"] += 1

        def on_failed(r):
            if "BLOCKED_BY_CLIENT" in (r.failure or ""):
                stats["blocked"] += 1

        def on_finished(r):
            if is_ad_host(r.url):
                stats["loaded_ad"] += 1

        page.on("request", on_request)
        page.on("requestfailed", on_failed)
        page.on("requestfinished", on_finished)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(5000)
            page.mouse.wheel(0, 2500)  # trigger lazy-loaded ads
            page.wait_for_timeout(4000)
            stats["visible_ads"] = page.evaluate(VISIBLE_ADS_JS)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
            page.screenshot(path=str(SHOTS / f"{tag}-{'hush' if with_ext else 'plain'}.png"))
            stats["ok"] = True
        except Exception as e:
            stats["ok"] = False
            stats["error"] = re.sub(r"\s+", " ", str(e))[:90]
        ctx.close()
        return stats


def main():
    rows = []
    with sync_playwright() as p:
        for url in SITES:
            tag = urlparse(url).hostname.replace("www.", "").split(".")[0]
            plain = run(p, url, False, tag)
            hush = run(p, url, True, tag)
            rows.append((tag, plain, hush))
            print(f"{tag:12} plain: {plain.get('loaded_ad', '-'):>4} ad loads, {plain.get('visible_ads', '-'):>3} visible ads"
                  f" | hush: {hush.get('loaded_ad', '-'):>4} ad loads, {hush.get('visible_ads', '-'):>3} visible ads,"
                  f" {hush.get('blocked', '-'):>4} blocked  {hush.get('error', '') or plain.get('error', '')}", flush=True)

        # Independent scorer: d3ward's ad-block test page.
        with tempfile.TemporaryDirectory() as profile:
            ctx = p.chromium.launch_persistent_context(
                profile, channel="chromium", headless=True,
                args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"],
            )
            page = ctx.new_page()
            page.wait_for_timeout(2000)
            try:
                page.goto("https://d3ward.github.io/toolz/adblock", timeout=45000)
                page.wait_for_timeout(15000)
                score = page.evaluate("""() => {
                  const t = document.body.innerText;
                  const m = t.match(/(\\d{1,3})\\s*%/);
                  return m ? m[1] + '%' : null; }""")
                page.screenshot(path=str(SHOTS / "d3ward-score.png"), full_page=False)
                print(f"\nd3ward ad-block test score with Hush: {score}")
            except Exception as e:
                print("d3ward test failed:", str(e)[:120])
            ctx.close()

    (ROOT / "tests" / "real_sites_results.json").write_text(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

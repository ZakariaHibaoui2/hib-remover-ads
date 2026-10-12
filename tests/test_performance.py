"""Measures what Hib Remover Ads costs and saves in page speed.

For each site, loads it in a fresh Chromium profile without and with the
extension and records, from Chrome's own performance counters:
  load       time until the page's load event (ms)
  cpu        main-thread busy time during the first 8 s (ms): scripts, layout, style
  style      time spent recalculating styles (ms), where element hiding shows up
  heap       JavaScript memory in use (MB)
  requests   network requests made

A local ad-free page shows the extension's own overhead with no ads to remove.
Run: python tests/test_performance.py [--runs N]
"""
import http.server
import json
import statistics
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "src"
RUNS = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 2

# A long, ad-free article with 3,000 elements: pure overhead measurement.
PLAIN = ("<!doctype html><html><head><title>Plain</title></head><body>"
         + "".join(f"<section class='post-{i}'><h2>Heading {i}</h2><p>" + "Lorem ipsum dolor sit amet. " * 20
                   + f"</p><a href='#{i}'>Link</a><div class='meta'><span>by A</span></div></section>"
                   for i in range(600))
         + "</body></html>").encode()

SITES = [
    "LOCAL",
    "https://www.speedtest.net",
    "https://www.cnn.com",
    "https://www.forbes.com",
    "https://www.weather.com",
    "https://www.hespress.com",
    "https://www.wikipedia.org",
    "https://www.youtube.com",
]


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PLAIN)

    def log_message(self, *a):
        pass


def measure(p, url, with_ext):
    with tempfile.TemporaryDirectory() as profile:
        args = [f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"] if with_ext else []
        ctx = p.chromium.launch_persistent_context(
            profile, channel="chromium", headless=True, args=args,
            viewport={"width": 1366, "height": 900}, locale="en-US")
        if with_ext:
            sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
            for _ in range(40):
                if sw.evaluate("chrome.scripting.getRegisteredContentScripts().then(s => s.length)") >= 5:
                    break
                ctx.pages[0].wait_for_timeout(250)
        page = ctx.new_page()
        requests = []
        page.on("request", lambda r: requests.append(r.url))
        cdp = ctx.new_cdp_session(page)
        cdp.send("Performance.enable")
        out = {}
        try:
            page.goto(url, wait_until="load", timeout=45000)
            out["load"] = page.evaluate("performance.getEntriesByType('navigation')[0].loadEventStart")
            page.wait_for_timeout(8000)
            m = {x["name"]: x["value"] for x in cdp.send("Performance.getMetrics")["metrics"]}
            out["cpu"] = (m["TaskDuration"]) * 1000
            out["style"] = m["RecalcStyleDuration"] * 1000
            out["heap"] = m["JSHeapUsedSize"] / 1e6
            out["requests"] = len(requests)
        except Exception as e:
            out["error"] = str(e)[:80]
        ctx.close()
        return out


def median(rows, key):
    vals = [r[key] for r in rows if key in r]
    return statistics.median(vals) if vals else None


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    local = f"http://127.0.0.1:{server.server_port}/"
    results = {}
    with sync_playwright() as p:
        for site in SITES:
            url = local if site == "LOCAL" else site
            name = "ad-free test page" if site == "LOCAL" else url.split("//")[1].replace("www.", "")
            plain = [measure(p, url, False) for _ in range(RUNS)]
            hib = [measure(p, url, True) for _ in range(RUNS)]
            row = {k: (median(plain, k), median(hib, k)) for k in ("load", "cpu", "style", "heap", "requests")}
            results[name] = row
            f = lambda k, d=0: "  -  " if None in row[k] else f"{row[k][0]:7.{d}f} -> {row[k][1]:7.{d}f}"
            print(f"{name:20} load {f('load')} ms | cpu {f('cpu')} ms | style {f('style')} ms"
                  f" | heap {f('heap', 1)} MB | requests {f('requests')}", flush=True)
    server.shutdown()
    (ROOT / "tests" / "performance_results.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()

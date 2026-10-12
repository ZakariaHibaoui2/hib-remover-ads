"""Popunder protection: ad tabs opened by a page close, real tabs don't.

Cases
  1. a click opens an ad network in a new tab               -> tab closes
  2. same, with noopener                                     -> tab closes
  3. same, with noopener and noreferrer                      -> tab closes
  4. a real link with target=_blank                          -> stays open
  5. typing an ad network's address into a tab already in use -> stays open, shows the blocked page

Run: python tests/test_popups.py
"""
import http.server
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

EXT = Path(__file__).resolve().parent.parent / "src"
AD = "popads.net"
FEATURES = {"plain": "", "noopener": "noopener", "noopener+noreferrer": "noopener,noreferrer"}

PAGE = """<!doctype html><html><body style="height:2000px"><h1>Popunder test</h1>
<a id="real" href="https://www.wikipedia.org/" target="_blank">Real link</a>
<script>
  const features = new URLSearchParams(location.search).get('f') || '';
  document.addEventListener('click', (e) => {
    if (e.target.id !== 'real') window.open('https://%s/', '_blank', features);
  });
</script></body></html>""" % AD


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE.encode())

    def log_message(self, *a):
        pass


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/"
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} {name}{'  (' + detail + ')' if detail and not ok else ''}")

    with sync_playwright() as p, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        ctx = p.chromium.launch_persistent_context(
            profile, channel="chromium", headless=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        page = ctx.new_page()
        for name, features in FEATURES.items():
            page.goto(f"{base}?f={features}")
            page.wait_for_timeout(800)
            with ctx.expect_page() as info:
                page.mouse.click(400, 600)
            ad = info.value
            try:
                ad.wait_for_event("close", timeout=5000)
            except Exception:
                pass
            check(f"popunder ({name}) closed", ad.is_closed(), "" if ad.is_closed() else ad.url)

        with ctx.expect_page() as info:
            page.click("#real")
        real = info.value
        real.wait_for_load_state()
        real.wait_for_timeout(1000)
        check("real link opens", not real.is_closed() and "wikipedia.org" in real.url, real.url)

        used = ctx.new_page()
        used.goto("https://www.wikipedia.org/")
        used.wait_for_timeout(500)
        used.goto(f"https://{AD}/")
        used.wait_for_timeout(2000)
        check("typed ad address keeps the tab, shows blocked page",
              not used.is_closed() and used.url.endswith("/blocked/popup.html"),
              "closed" if used.is_closed() else used.url)
        ctx.close()
    server.shutdown()
    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

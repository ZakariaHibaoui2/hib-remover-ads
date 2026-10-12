"""End-to-end test: loads Hush into Chromium and checks blocking, hiding,
per-site pause, the global switch, and YouTube pruning.

Run: python tests/test_extension.py   (needs `python -m playwright install chromium`)
"""
import http.server
import socketserver
import sys
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "src"
SHOTS = ROOT / "tests" / "screenshots"
SHOTS.mkdir(exist_ok=True)

PAGE = b"""<!doctype html><html><head><title>Hush test</title></head><body>
<p id="article">Real article text that must stay visible.</p>
<ins class="adsbygoogle" id="ad1" style="display:block;width:300px;height:250px"></ins>
<div id="div-gpt-ad-123" style="height:90px;background:red">GPT ad</div>
<div class="ad-container-fake" id="not-ad">Keep me: not an ad selector</div>
<script src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"></script>
<script>window.googletag = window.googletag || {cmd: []};
  googletag.cmd.push(() => { window.gptRan = googletag.pubads().enableSingleRequest() !== undefined; });</script>
<script src="https://securepubads.g.doubleclick.net/tag/js/gpt.js"></script>
<script>
  setTimeout(() => {
    const late = document.createElement('div');
    late.className = 'advertisement'; late.id = 'late'; late.textContent = 'late ad';
    document.body.appendChild(late);
  }, 300);
</script>
</body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *a):
        pass


results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))


def wait_for(fn, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    return fn()


def main():
    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"

    with sync_playwright() as p, tempfile.TemporaryDirectory() as profile:
        ctx = p.chromium.launch_persistent_context(
            profile,
            channel="chromium",
            headless=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"],
            viewport={"width": 1280, "height": 800},
        )
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
        ext_id = sw.url.split("/")[2]

        ready = wait_for(lambda: sw.evaluate("chrome.scripting.getRegisteredContentScripts().then(s => s.length)") == 5)
        check("content scripts registered on install", ready)

        blocked = []
        page = ctx.new_page()
        page.on("requestfailed", lambda r: blocked.append(r.url) if "BLOCKED_BY_CLIENT" in (r.failure or "") else None)

        def load():
            blocked.clear()
            page.goto(url)
            page.wait_for_timeout(1500)

        def display(sel):
            return page.eval_on_selector(sel, "e => getComputedStyle(e).display")

        # --- Blocking on ---
        load()
        check("ad script blocked at network level", any("googlesyndication" in u for u in blocked), str(blocked))
        check("adsbygoogle slot hidden", display("#ad1") == "none")
        check("GPT slot hidden", display("#div-gpt-ad-123") == "none")
        check("late-inserted ad hidden", display("#late") == "none")
        check("GPT replaced by stand-in, queued page code still runs",
              page.evaluate("window.gptRan === true && googletag.apiReady === true"))
        check("article text visible", display("#article") != "none")
        check("non-ad element visible", display("#not-ad") != "none")
        page.screenshot(path=str(SHOTS / "test-page-blocking.png"))

        # The popup reads the active tab; point it at the test page.
        tab_id = sw.evaluate(f"chrome.tabs.query({{url: '{url}*'}}).then(t => t[0].id)")
        popup = ctx.new_page()
        popup.add_init_script(f"""
          if (location.protocol === 'chrome-extension:') {{
            const q = chrome.tabs.query.bind(chrome.tabs);
            chrome.tabs.query = () => q({{}}).then(ts => ts.filter(t => t.id === {tab_id}));
          }}""")
        popup.set_viewport_size({"width": 340, "height": 600})
        popup.goto(f"chrome-extension://{ext_id}/popup/popup.html")
        popup.wait_for_timeout(1200)
        page_count = int(popup.inner_text("#page").replace(",", ""))
        check("popup shows host", popup.inner_text("#host") == "127.0.0.1", popup.inner_text("#host"))
        check("popup counts blocked items on page", page_count >= 4, str(page_count))
        check("all-time total counted", int(popup.inner_text("#total").replace(",", "")) >= page_count)
        popup.screenshot(path=str(SHOTS / "popup-on.png"))

        # --- Pause this site (through the real popup button) ---
        popup.click("#pause")
        wait_for(lambda: popup.get_attribute("body", "data-state") == "paused")
        check("popup shows paused state", popup.get_attribute("body", "data-state") == "paused")
        popup.screenshot(path=str(SHOTS / "popup-paused.png"))
        load()
        check("paused: ad script not blocked", not blocked, str(blocked))
        check("paused: ad slot visible", display("#ad1") != "none")

        popup.click("#pause")
        wait_for(lambda: popup.get_attribute("body", "data-state") == "on")
        load()
        check("resumed: blocking again", any("googlesyndication" in u for u in blocked) and display("#ad1") == "none")

        # --- Global switch ---
        popup.click("#power")
        wait_for(lambda: popup.get_attribute("body", "data-state") == "off")
        popup.screenshot(path=str(SHOTS / "popup-off.png"))
        load()
        check("off: nothing blocked or hidden", not blocked and display("#ad1") != "none")
        popup.click("#power")
        wait_for(lambda: popup.get_attribute("body", "data-state") == "on")
        load()
        check("back on: blocking restored", display("#ad1") == "none")

        # --- YouTube (live) ---
        yt = ctx.new_page()
        try:
            yt.goto("https://www.youtube.com/watch?v=jNQXAC9IVRw", wait_until="domcontentloaded", timeout=30000)
            yt.wait_for_timeout(6000)
            pruned = yt.evaluate("""() => {
              const r = window.ytInitialPlayerResponse;
              return r ? !('adPlacements' in r) && !('playerAds' in r) : null;
            }""")
            check("YouTube: player response has no ad placements", pruned is True, str(pruned))
            check("YouTube: hiding stylesheet injected", yt.evaluate("!!document.querySelector('style[data-hush]')"))
            check("YouTube: video player present", yt.evaluate("!!document.querySelector('video')"))
            yt.screenshot(path=str(SHOTS / "youtube.png"))
        except Exception as e:  # network-dependent; report but don't crash
            check("YouTube reachable", False, repr(e)[:200])

        ctx.close()
    server.shutdown()

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

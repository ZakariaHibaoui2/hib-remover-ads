"""Checks the features added in 2.1: click-to-remove, the weekly savings,
the prefilled report link, and the popup in English, French and Arabic.

Run: python tests/test_features.py
"""
import http.server
import socketserver
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "src"
SHOTS = ROOT / "tests" / "screenshots"
SHOTS.mkdir(exist_ok=True)

PAGE = b"""<!doctype html><html><head><title>Feature test</title></head><body style="margin:40px">
<p id="article">Real article text that must stay visible.</p>
<div id="annoying" style="width:300px;height:120px;background:#c33;color:#fff">Annoying box</div>
<div class="row"><span>one</span><span class="pick" style="display:inline-block;width:120px;height:40px;background:#36c">second</span></div>
<a id="link" href="/elsewhere" style="display:block;width:200px;height:40px;background:#3a3">A link</a>
<ins class="adsbygoogle" style="display:block;width:300px;height:250px"></ins>
<script src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"></script>
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


def launch(p, profile, lang=None):
    args = [f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"]
    if lang:
        args.append(f"--lang={lang}")
    ctx = p.chromium.launch_persistent_context(profile, channel="chromium", headless=True, args=args,
                                               viewport={"width": 1280, "height": 800})
    sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
    wait_for(lambda: sw.evaluate("chrome.scripting.getRegisteredContentScripts().then(s => s.length)") == 5)
    return ctx, sw, sw.url.split("/")[2]


def open_popup(ctx, ext_id, tab_id):
    popup = ctx.new_page()
    popup.add_init_script(f"""
      if (location.protocol === 'chrome-extension:') {{
        const q = chrome.tabs.query.bind(chrome.tabs);
        chrome.tabs.query = () => q({{}}).then(ts => ts.filter(t => t.id === {tab_id}));
      }}""")
    popup.set_viewport_size({"width": 340, "height": 600})
    popup.goto(f"chrome-extension://{ext_id}/popup/popup.html")
    popup.wait_for_timeout(1200)
    return popup


def main():
    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"

    with sync_playwright() as p:
        # ---------------- English: zapper, week, report ----------------
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
            ctx, sw, ext_id = launch(p, profile, "en")
            page = ctx.new_page()
            page.goto(url)
            page.wait_for_timeout(1500)
            tab_id = sw.evaluate(f"chrome.tabs.query({{url: '{url}*'}}).then(t => t[0].id)")
            display = lambda sel: page.eval_on_selector(sel, "e => getComputedStyle(e).display")

            popup = open_popup(ctx, ext_id, tab_id)
            check("popup in English by default", popup.inner_text("#zap").strip() == "Remove something on this page",
                  popup.inner_text("#zap"))
            for _ in range(3):
                week_ads = int(popup.inner_text("#week-ads").replace(",", ""))
                if week_ads:
                    break
                page.wait_for_timeout(2000)
                popup.close()
                popup = open_popup(ctx, ext_id, tab_id)
            check("weekly ads counted", week_ads > 0, popup.inner_text("#week-ads"))
            check("weekly time and data shown", popup.inner_text("#week-time")[:1] in "≈<"
                  and popup.inner_text("#week-data").startswith("≈"),
                  popup.inner_text("#week-time") + " / " + popup.inner_text("#week-data"))
            report = urlparse(popup.get_attribute("#report", "href"))
            q = parse_qs(report.query)
            check("report link prefilled", q.get("template") == ["ad-got-through.yml"]
                  and q.get("url") == [url] and q.get("version", [""])[0].count(".") == 2
                  and q.get("title") == ["Ad on 127.0.0.1"], report.query)
            check("zapped line hidden before any removal", popup.is_hidden("#zapped"))
            popup.screenshot(path=str(SHOTS / "popup-on.png"))

            # Start the zapper the way the popup button does.
            started = popup.evaluate(f"chrome.runtime.sendMessage({{type: 'zapStart', tabId: {tab_id}}})")
            check("zapper starts", started is True and wait_for(lambda: page.locator("hib-zapper").count() == 1),
                  str(started))
            page.bring_to_front()
            box = page.locator("#annoying").bounding_box()
            page.mouse.move(box["x"] + 20, box["y"] + 20)
            page.wait_for_timeout(200)
            page.screenshot(path=str(SHOTS / "zapper.png"))
            page.mouse.click(box["x"] + 20, box["y"] + 20)
            check("click removes the element", display("#annoying") == "none")
            check("other content untouched", display("#article") != "none")

            box = page.locator(".pick").bounding_box()
            page.mouse.click(box["x"] + 10, box["y"] + 10)
            check("second element removed", display(".pick") == "none")

            box = page.locator("#link").bounding_box()
            before = page.url
            page.mouse.click(box["x"] + 10, box["y"] + 10)
            page.wait_for_timeout(500)
            check("clicking a link while picking doesn't navigate", page.url == before, page.url)
            check("link removed instead", display("#link") == "none")

            page.keyboard.press("Control+z")
            page.wait_for_timeout(300)
            check("undo brings the last one back", display("#link") != "none")
            page.keyboard.press("Escape")
            check("Esc closes the zapper", wait_for(lambda: page.locator("hib-zapper").count() == 0))

            saved = wait_for(lambda: sw.evaluate("chrome.storage.local.get('zapped').then(r => r.zapped || {})")
                             .get("127.0.0.1"), 5) or []
            check("two removals saved for the site", len(saved) == 2, str(saved))

            page.goto(url)
            page.wait_for_timeout(1500)
            check("removed elements stay hidden after reload",
                  display("#annoying") == "none" and display(".pick") == "none", f"{display('#annoying')} {display('.pick')}")
            check("undone element visible after reload", display("#link") != "none")
            check("article still visible after reload", display("#article") != "none")

            popup = open_popup(ctx, ext_id, tab_id)
            check("popup shows removals on this site", popup.is_visible("#zapped")
                  and "2" in popup.inner_text("#zapped-text"), popup.inner_text("#zapped-text"))
            popup.screenshot(path=str(SHOTS / "popup-zapped.png"))
            popup.click("#restore")
            wait_for(lambda: popup.is_hidden("#zapped"), 6)
            page.goto(url)
            page.wait_for_timeout(1500)
            check("restore brings everything back", display("#annoying") != "none" and display(".pick") != "none")

            bad = sw.evaluate("""(async () => {
              await chrome.storage.local.set({zapped: {'127.0.0.1': ['body{display:none}#x']}});
              return true; })()""")
            page.goto(url)
            page.wait_for_timeout(1200)
            check("unsafe stored selector ignored", bad and display("#article") != "none")
            ctx.close()

        # ---------------- French and Arabic ----------------
        for lang, expect_zap, expect_dir in [("fr", "Retirer un élément de la page", "ltr"),
                                             ("ar", "إزالة عنصر من هذه الصفحة", "rtl")]:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
                ctx, sw, ext_id = launch(p, profile, lang)
                page = ctx.new_page()
                page.goto(url)
                page.wait_for_timeout(1200)
                tab_id = sw.evaluate(f"chrome.tabs.query({{url: '{url}*'}}).then(t => t[0].id)")
                popup = open_popup(ctx, ext_id, tab_id)
                check(f"popup in {lang}", popup.inner_text("#zap").strip() == expect_zap, popup.inner_text("#zap"))
                check(f"{lang}: text direction {expect_dir}", popup.get_attribute("html", "dir") == expect_dir)
                check(f"{lang}: digits stay Latin", popup.inner_text("#total").replace(",", "").replace(" ", "")
                      .replace("\xa0", "").isascii())
                popup.screenshot(path=str(SHOTS / f"popup-{lang}.png"))
                ctx.close()

    server.shutdown()
    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

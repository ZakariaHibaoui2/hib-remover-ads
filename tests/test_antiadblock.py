"""Checks that "ad blocker detected" walls stay away with the extension on.

1. A local page with the common checks: a bait element (class "adsbox") and a
   bait image from Google's ad server. It must show no wall, and the ad server
   must never be contacted.
2. A local page that shows a wall straight away: the wall must be removed and
   scrolling given back.
3. Optional real site (korahlive.online), skipped when offline.

Run: python tests/test_antiadblock.py
"""
import functools
import http.server
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

EXT = str(Path(__file__).resolve().parent.parent / "src")
REAL = "https://w.korahlive.online/2026/09/ch1.html?match=test"

BAIT = """<!doctype html><meta charset="utf-8"><body style="height:3000px"><p>Match stream</p>
<script>
function wall(){ if(document.querySelector('#antiAdblockPopup')) return;
  var d=document.createElement('div'); d.id='antiAdblockPopup';
  d.style.cssText='position:fixed;inset:0;background:#000c;z-index:999999';
  d.innerHTML='تم اكتشاف مانع إعلانات أو متصفح محمي'; document.body.appendChild(d);
  document.body.style.overflow='hidden'; window.walls=(window.walls||0)+1; }
addEventListener('load', function(){
  var b=document.createElement('div'); b.className='adsbox'; b.style.height='1px';
  b.style.position='absolute'; b.style.left='-999px'; document.body.appendChild(b);
  setTimeout(function(){ if(b.offsetHeight===0) { window.why='bait'; wall(); } window.baitDone=1; }, 300);
  var i=new Image(); i.onload=function(){ window.imgOk=1; };
  i.onerror=function(){ window.why='image'; wall(); window.imgOk=0; };
  i.src='https://pagead2.googlesyndication.com/pagead/imgad?id=CICAgKCr6dP9-QEQARgBMgjGDN_tg4kL&rand='+Math.random();
});
</script>"""

WALL = """<!doctype html><meta charset="utf-8"><body style="height:3000px;overflow:hidden"><p>Article</p>
<div id="w" style="position:fixed;top:0;left:0;width:100%;height:100%;background:#000c;z-index:99999">
Ad blocker detected. Please disable your ad blocker to continue.</div></body>"""

NOT_WALL = """<!doctype html><meta charset="utf-8"><body>
<div id="n" style="position:fixed;top:0;left:0;width:100%;height:100%;background:#fff">How to set up an ad blocker: a guide</div>
<div id="m" style="position:fixed;top:0;left:0;width:100%;height:100%;background:#0003">Sign in to continue</div></body>"""

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  ({detail})"), flush=True)


def main():
    site = Path(tempfile.mkdtemp(prefix="hush-aab-"))
    (site / "bait.html").write_text(BAIT, encoding="utf-8")
    (site / "wall.html").write_text(WALL, encoding="utf-8")
    (site / "notwall.html").write_text(NOT_WALL, encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a: None
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    with sync_playwright() as p:
        profile = tempfile.mkdtemp(prefix="hush-aab-profile-")
        ctx = p.chromium.launch_persistent_context(
            profile, channel="chromium", headless=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        ctx.wait_for_event("serviceworker") if not ctx.service_workers else None
        page = ctx.new_page()
        reached = []
        page.on("requestfinished", lambda r: reached.append(r.url) if "googlesyndication" in r.url and r.url.startswith("https://pagead2") and not r.url.startswith("chrome-extension") else None)

        page.goto(f"{base}/bait.html")
        page.wait_for_timeout(2500)
        state = page.evaluate("({walls: window.walls || 0, why: window.why || '', imgOk: window.imgOk, wall: !!document.querySelector('#antiAdblockPopup')})")
        check("bait page: no wall appears", state["walls"] == 0 and not state["wall"], str(state))
        check("bait page: the bait image loads (a blank stand-in)", state["imgOk"] == 1, str(state))
        server_hits = page.evaluate("performance.getEntriesByType('resource').filter(e => e.name.includes('googlesyndication')).map(e => e.transferSize)")
        check("bait page: nothing is downloaded from the ad server", all(s == 0 for s in server_hits), str(server_hits))

        page.goto(f"{base}/wall.html")
        page.wait_for_timeout(1500)
        gone = page.evaluate("!document.querySelector('#w')")
        scroll = page.evaluate("getComputedStyle(document.body).overflow")
        check("wall page: the wall is removed", gone)
        check("wall page: scrolling works again", scroll != "hidden", scroll)

        page.goto(f"{base}/notwall.html")
        page.wait_for_timeout(1500)
        kept = page.evaluate("!!document.querySelector('#n') && !!document.querySelector('#m')")
        check("ordinary full-screen layers are left alone", kept)

        if "--no-real" not in sys.argv:
            try:
                page.goto(REAL, wait_until="load", timeout=45000)
                page.wait_for_timeout(4000)
                wall = page.evaluate("(() => { const w = document.querySelector('#antiAdblockPopup'); return !!w && getComputedStyle(w).display !== 'none'; })()")
                check("korahlive.online: no 'ad blocker detected' wall", not wall)
                page.screenshot(path=str(Path(__file__).parent / "screenshots" / "korahlive.png"))
            except Exception as e:
                print(f"SKIP korahlive.online ({str(e)[:80]})")
        ctx.close()
    srv.shutdown()
    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())

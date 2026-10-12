"""Loads popular Arabic, Moroccan, North-African and French sites with and
without Hib Remover Ads and compares ad traffic, visible ad slots and page
text (to catch breakage). Network-dependent; results vary by region and time.

Run: python tests/test_arabic_sites.py            (all sites)
     python tests/test_arabic_sites.py hespress kooora   (only matching sites)
"""
import json
import re
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "src"
SHOTS = ROOT / "tests" / "screenshots" / "arabic"
RESULTS = ROOT / "tests" / "arabic_sites_results.json"

SITES = {
    # Morocco
    "hespress": "https://www.hespress.com",
    "le360": "https://le360.ma",
    "hibapress": "https://www.hibapress.com",
    "alyaoum24": "https://alyaoum24.com",
    "goud": "https://www.goud.ma",
    "barlamane": "https://www.barlamane.com",
    "chouftv": "https://chouftv.ma",
    "avito": "https://www.avito.ma",
    "medias24": "https://medias24.com",
    "lematin": "https://lematin.ma",
    "yabiladi": "https://www.yabiladi.com",
    "akhbarona": "https://www.akhbarona.com",
    "assabah": "https://assabah.ma",
    "lesiteinfo": "https://www.lesiteinfo.com",
    "2m": "https://2m.ma/ar",
    "elbotola": "https://www.elbotola.com",
    "telquel": "https://telquel.ma",
    "snrtnews": "https://snrtnews.com",
    # Pan-Arab and Egypt / Gulf
    "kooora": "https://www.kooora.com",
    "aljazeera": "https://www.aljazeera.net",
    "alarabiya": "https://www.alarabiya.net",
    "youm7": "https://www.youm7.com",
    "masrawy": "https://www.masrawy.com",
    "elbalad": "https://www.elbalad.news",
    "almasryalyoum": "https://www.almasryalyoum.com",
    "skynewsarabia": "https://www.skynewsarabia.com",
    "sabq": "https://sabq.org",
    "filgoal": "https://www.filgoal.com",
    "yallakora": "https://www.yallakora.com",
    "btolat": "https://www.btolat.com",
    "cnnarabic": "https://arabic.cnn.com",
    "bbcarabic": "https://www.bbc.com/arabic",
    "france24ar": "https://www.france24.com/ar/",
    # French
    "leparisien": "https://www.leparisien.fr",
    "20minutes": "https://www.20minutes.fr",
    "lefigaro": "https://www.lefigaro.fr",
    "jeuxvideo": "https://www.jeuxvideo.com",
    "marmiton": "https://www.marmiton.org",
    "ouest-france": "https://www.ouest-france.fr",
    # Arabic streaming / download mirrors (popup-heavy; skipped if unreachable)
    "akwam": "https://ak.sv",
    "wecima": "https://wecima.video",
    "egybest": "https://egybest.la",
    "shahid4u": "https://shahid4u.cam",
    "arabseed": "https://arabseed.show",
    "cimaclub": "https://cimaclub.day",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


def load_ad_domains():
    """Curated domains plus every plain domain block from the compiled lists."""
    doms = set(json.loads((EXT / "rules" / "ads.json").read_text())[0]["condition"]["requestDomains"])
    for r in json.loads((EXT / "rules" / "block.json").read_text()):
        c = r["condition"]
        if r["action"]["type"] == "block" and "requestDomains" in c and not c.get("initiatorDomains") \
                and not c.get("urlFilter") and not c.get("excludedInitiatorDomains"):
            doms.update(c["requestDomains"])
    return sorted(doms)


AD_DOMAINS = load_ad_domains()

# Visible ad slots: well-known markers plus any iframe served from a known ad host.
# Returns details so remaining ads can be fixed.
VISIBLE_ADS_JS = """(adDomains) => {
  const ads = new Set(adDomains);
  const isAd = (u) => { try { let h = new URL(u, location.href).hostname;
      while (h.includes('.')) { if (ads.has(h)) return true; h = h.slice(h.indexOf('.') + 1); } } catch (e) {}
      return false; };
  const sel = 'ins.adsbygoogle, [id^="google_ads_iframe"], [id^="div-gpt-ad"], [data-google-query-id],'
    + ' iframe[src*="doubleclick"], iframe[src*="googlesyndication"], iframe[src*="amazon-adsystem"],'
    + ' iframe[id^="google_ads_"], [id^="taboola-"], .trc_related_container, .OUTBRAIN, [data-ad-slot],'
    + ' [id^="mgid_"], .mgbox, [data-revcontent-widget], [id^="adsterra"], .teads-inread';
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 20 && r.height > 20 && s.display !== 'none' && s.visibility !== 'hidden'
      && s.opacity !== '0' && !e.closest('[style*="display: none"]'); };
  const found = new Set([...document.querySelectorAll(sel)].filter(vis));
  for (const f of document.querySelectorAll('iframe[src]')) if (isAd(f.src) && vis(f)) found.add(f);
  // Count outermost only.
  const top = [...found].filter((e) => ![...found].some((o) => o !== e && o.contains(e)));
  const describe = (e) => {
    const chain = []; let n = e;
    for (let i = 0; n && n !== document.body && i < 5; i++, n = n.parentElement)
      chain.push(n.tagName.toLowerCase() + (n.id ? '#' + n.id : '')
        + (typeof n.className === 'string' && n.className.trim() ? '.' + n.className.trim().split(/\\s+/).slice(0, 3).join('.') : ''));
    const r = e.getBoundingClientRect();
    return { chain: chain.join(' < '), src: (e.src || e.querySelector('iframe')?.src || '').slice(0, 120),
             size: Math.round(r.width) + 'x' + Math.round(r.height) };
  };
  // Candidates: visible, banner-sized boxes whose id/class looks ad-related (not counted).
  const re = /(^|[-_\\s])(ads?|advert\\w*|pub|banner|sponsor\\w*|dfp|gpt|adslot|adunit|teads|outbrain|taboola|mgid)([-_\\s\\d]|$)/i;
  const cands = [];
  for (const e of document.querySelectorAll('div[id], div[class], aside, section[class], iframe')) {
    const key = (e.id || '') + ' ' + (typeof e.className === 'string' ? e.className : '');
    if (!re.test(key) || !vis(e)) continue;
    const r = e.getBoundingClientRect();
    if (r.height < 40 || r.height > 1000) continue;
    if (cands.some((c) => c.el.contains(e))) continue;
    cands.push({ el: e, ...describe(e) });
    if (cands.length >= 12) break;
  }
  const frames = [...new Set([...document.querySelectorAll('iframe')].filter(vis)
    .map((f) => { try { return new URL(f.src).hostname; } catch (e) { return ''; } }).filter(Boolean))];
  return { count: top.length, ads: top.slice(0, 10).map(describe),
           candidates: cands.map(({ el, ...rest }) => rest), frames };
}"""


def ad_host(url):
    host = urlparse(url).hostname or ""
    parts = host.split(".")
    return any(".".join(parts[i:]) in AD_SET for i in range(len(parts) - 1))


AD_SET = set(AD_DOMAINS)


def wait_for_extension(ctx):
    sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
    for _ in range(40):
        try:
            if sw.evaluate("chrome.scripting.getRegisteredContentScripts().then(s => s.length)") >= 4:
                return
        except Exception:
            pass
        (ctx.pages[0] if ctx.pages else ctx.new_page()).wait_for_timeout(250)


def run(p, url, with_ext, name):
    with tempfile.TemporaryDirectory() as profile:
        args = [f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"] if with_ext else []
        ctx = p.chromium.launch_persistent_context(
            profile, channel="chromium", headless=True, args=args,
            viewport={"width": 1366, "height": 900}, locale="ar-MA", user_agent=UA,
        )
        if with_ext:
            wait_for_extension(ctx)
        page = ctx.new_page()
        stats = {"ad_requests": 0, "loaded_ad": 0, "blocked": 0, "popups": 0}
        scripts = set()

        def on_request(r):
            if ad_host(r.url):
                stats["ad_requests"] += 1
            if r.resource_type == "script":
                scripts.add(urlparse(r.url).hostname or "")

        def on_failed(r):
            if "BLOCKED_BY_CLIENT" in (r.failure or ""):
                stats["blocked"] += 1

        def on_finished(r):
            if ad_host(r.url):
                stats["loaded_ad"] += 1

        ctx.on("request", on_request)
        ctx.on("requestfailed", on_failed)
        ctx.on("requestfinished", on_finished)
        ctx.on("page", lambda pg: stats.__setitem__("popups", stats["popups"] + 1))
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(6000)
            page.mouse.wheel(0, 2500)  # trigger lazy-loaded ads
            page.wait_for_timeout(4000)
            for attempt in range(3):  # some sites redirect once after load
                try:
                    res = page.evaluate(VISIBLE_ADS_JS, AD_DOMAINS)
                    stats["text"] = page.evaluate("document.body ? document.body.innerText.length : 0")
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    page.wait_for_timeout(4000)
            stats["visible_ads"] = res["count"]
            stats["ads"] = res["ads"]
            stats["final_url"] = page.url
            if with_ext:
                stats["candidates"] = res["candidates"]
                stats["frames"] = res["frames"]
                stats["script_hosts"] = sorted(scripts)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(500)
                page.screenshot(path=str(SHOTS / f"{name}.png"))
            # Popunder networks fire on the first click anywhere; measured last
            # because the click may also follow a link.
            try:
                page.mouse.click(5, 450)
                page.wait_for_timeout(2500)
            except Exception:
                pass
            stats["ok"] = True
        except Exception as e:
            stats["ok"] = False
            stats["error"] = re.sub(r"\s+", " ", str(e))[:120]
        ctx.close()
        return stats


def test_site(item):
    name, url = item
    with sync_playwright() as p:
        plain = run(p, url, False, name)
        if not plain.get("ok"):
            return {"name": name, "url": url, "skipped": plain.get("error", "failed")}
        hush = run(p, url, True, name)
    ratio = round(hush.get("text", 0) / plain["text"], 2) if plain.get("text") else None
    return {"name": name, "url": url, "plain": plain, "hush": hush, "text_ratio": ratio,
            # Text heavily below the plain run suggests breakage (pages also rotate content).
            "possible_breakage": bool(ratio is not None and ratio < 0.6)}


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    only = [a.lower() for a in sys.argv[1:]]
    items = [(n, u) for n, u in SITES.items() if not only or any(o in n for o in only)]
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(test_site, items))

    totals = {"plain_visible": 0, "hush_visible": 0, "plain_ad_loads": 0, "hush_ad_loads": 0}
    for r in rows:
        if "skipped" in r:
            print(f"{r['name']:14} SKIPPED: {r['skipped']}")
            continue
        pl, hu = r["plain"], r["hush"]
        if not hu.get("ok"):
            print(f"{r['name']:14} with-extension run failed: {hu.get('error')}")
            continue
        totals["plain_visible"] += pl["visible_ads"]
        totals["hush_visible"] += hu["visible_ads"]
        totals["plain_ad_loads"] += pl["loaded_ad"]
        totals["hush_ad_loads"] += hu["loaded_ad"]
        print(f"{r['name']:14} plain: {pl['loaded_ad']:>4} ad loads, {pl['visible_ads']:>3} visible"
              f" | hib: {hu['loaded_ad']:>4} ad loads, {hu['visible_ads']:>3} visible, {hu['blocked']:>4} blocked,"
              f" popups {pl['popups']}->{hu['popups']}, text {hu['text']}/{pl['text']}"
              f"{'  POSSIBLE BREAKAGE' if r['possible_breakage'] else ''}", flush=True)
    tested = sum(1 for r in rows if "skipped" not in r and r["hush"].get("ok"))
    print(f"\n{tested} sites tested. Visible ads: {totals['plain_visible']} without -> {totals['hush_visible']} with."
          f" Ad loads: {totals['plain_ad_loads']} -> {totals['hush_ad_loads']}.")
    RESULTS.write_text(json.dumps({"totals": totals, "sites": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Hib Remover Ads

A Chrome (Manifest V3) extension that blocks ads on YouTube and across the web.

## Install

**Windows:** download `HibRemoverAds-Setup.exe` from the [latest release](https://github.com/ZakariaHibaoui2/hib-remover-ads/releases/latest), run it, pick your browser and click Install. It unpacks the extension, copies the folder path and opens the extensions page. Then turn on **Developer mode**, click **Load unpacked**, press Ctrl+V and click Select Folder.

**Anywhere else:** download `hib-remover-ads.zip`, extract it, open `chrome://extensions`, turn on Developer mode, click **Load unpacked** and choose the folder.

Works in Chrome, Edge, Brave, Opera and other Chromium browsers. Website: https://zakariahibaoui2.github.io/hib-remover-ads/

## How it works

| Layer | What it does | File |
|---|---|---|
| Network blocking | ~17,000 rules compiled from EasyList, EasyPrivacy, uBlock filters, Liste FR and Liste AR, plus a curated list | `src/rules/block.json`, `allow.json`, `ads.json` |
| Element hiding | ~15,700 generic hiding rules on every site, plus per-site rules for ~10,000 sites | `src/content/generic.css`, `src/rules/cosmetic.json` |
| Scriptlets | ~4,600 per-site fixes from uBlock Origin that switch off anti-adblock checks, popunders and ad timers | `src/scriptlets/` |
| YouTube pre-roll removal | Strips ad instructions out of YouTube's player data so most video ads are never scheduled | `src/content/yt-main.js` |
| YouTube fallback | If an ad still plays: mutes it, jumps to the end, presses Skip, restores your sound and speed | `src/content/youtube.js` |

The popup shows how much was blocked on the current page and in total. It lets you pause Hib Remover Ads on one site or turn it off everywhere. Paused sites get no blocking and no injected scripts.

## Updating the filters

```sh
python tools/filterlists.py --fetch   # download the lists and compile them (needs Playwright)
node tools/build.mjs                  # curated list in tools/filters.mjs
python installer/build.py             # zip + Windows installer in store/
```

Reload the extension in `chrome://extensions` afterwards.

## Tests

```sh
python -m playwright install chromium
python tests/test_extension.py   # local checks
python tests/test_real_sites.py  # 21 real ad-heavy sites, with and without the extension
```

Loads the extension into Chromium and checks network blocking, element hiding, late-inserted ads, the page and total counters, site pause/resume, the global switch, and YouTube pruning on a live video. Screenshots land in `tests/screenshots/`.

## Limits

- YouTube changes its ad delivery often. If ads come back, the fallback skipper still shortens them, and the selectors in `tools/filters.mjs` are the first place to update.
- Some sites detect ad blockers and refuse to load. Use **Pause on this site** for those.
- Regex network rules and procedural cosmetic filters from the lists are skipped, so a few site-specific ads that uBlock Origin catches may get through.
- Chrome caps extensions at 30,000 enabled rules, so the lists are compiled to fit that budget.

## License

GPL-3.0. Filter lists by the EasyList authors and uBlock Origin contributors, used under GPL-3.0.

## Website

The download page lives in `docs/` and is served by GitHub Pages at https://zakariahibaoui2.github.io/hib-remover-ads/

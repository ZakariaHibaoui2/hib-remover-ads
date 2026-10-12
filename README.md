# Hib Remover Ads

A Chrome (Manifest V3) extension that blocks ads on YouTube and across the web.

## Install

1. Open `chrome://extensions`
2. Turn on **Developer mode** (top right)
3. Click **Load unpacked** and choose the `src` folder
4. Pin Hib Remover Ads from the puzzle-piece menu so its counter is visible

Works in Chrome, Edge, Brave and other Chromium browsers.

## How it works

| Layer | What it does | File |
|---|---|---|
| Network blocking | ~130 ad networks and YouTube ad endpoints are blocked before they download | `src/rules/ads.json` |
| Element hiding | Leftover ad slots (AdSense, GPT, Taboola, Outbrain, YouTube feed ads...) are hidden, including ones added later | `src/content/cosmetic.js` |
| YouTube pre-roll removal | Strips ad instructions out of YouTube's player data so most video ads are never scheduled | `src/content/yt-main.js` |
| YouTube fallback | If an ad still plays: mutes it, jumps to the end, presses Skip, restores your sound and speed | `src/content/youtube.js` |

The popup shows how much was blocked on the current page and in total. It lets you pause Hib Remover Ads on one site or turn it off everywhere. Paused sites get no blocking and no injected scripts.

## Editing the filters

Edit `tools/filters.mjs`, then regenerate:

```sh
node tools/build.mjs      # rules/ads.json + content/selectors.js
python tools/icons.py     # toolbar icons (needs Pillow)
```

Reload the extension in `chrome://extensions` afterwards.

## Tests

```sh
python -m playwright install chromium
python tests/test_extension.py
```

Loads the extension into Chromium and checks network blocking, element hiding, late-inserted ads, the page and total counters, site pause/resume, the global switch, and YouTube pruning on a live video. Screenshots land in `tests/screenshots/`.

## Limits

- YouTube changes its ad delivery often. If ads come back, the fallback skipper still shortens them, and the selectors in `tools/filters.mjs` are the first place to update.
- Some sites detect ad blockers and refuse to load. Use **Pause on this site** for those.
- The filter list is curated and small, not a full EasyList. Popular ad networks are covered; obscure ones may get through.

## Website

The download page lives in `docs/` and is served by GitHub Pages at https://zakariahibaoui2.github.io/hib-remover-ads/

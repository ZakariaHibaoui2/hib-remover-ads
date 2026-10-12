# Changelog

## 2.1.1

- Better blocking on Arabic, Moroccan and French sites: tested on 45 sites (Hespress, Le360, Hibapress, Kooora, Al Jazeera, Youm7, FilGoal, 20 Minutes and others), 81 visible ads without the extension and 0 with it.
- Blocks Project Agora and Adeq Media ad tags, the Axel Springer ad library on Sky News Arabia, and hides the empty ad boxes left on Akhbarona, FilGoal, Elbalad, Btolat, Alyaoum24, Telquel, 20 Minutes and others.
- No more "Extension context invalidated" errors in tabs that were open while the extension updated.
- New test: `tests/test_arabic_sites.py`.

## 2.1.0

- Click-to-remove: "Remove something on this page" in the popup lets you click any box to hide it for good on that site. Undo (Ctrl+Z), Esc, and Restore in the popup.
- "This week" in the popup: ads blocked, time saved and data saved, estimated from the requests blocked.
- The popup and the blocked-ad page are now in English, French and Arabic (right to left), following the browser's language.
- "Report a site" opens a GitHub issue already filled in with the page address, the version and the browser.
- New test: `tests/test_features.py` (26 checks).

## 2.0.6

- Install in every browser at once: the installer and the one-command install now offer "All browsers on this PC" first.
- Step-by-step Chrome Web Store, Edge Add-ons and Opera add-ons guide in `store/LISTING.md`.

## 2.0.5

- One-command install for Windows that doesn't trigger the SmartScreen warning: `irm https://zakariahibaoui2.github.io/hib-remover-ads/install.ps1 | iex`.
- The installer now finds 22 Chromium browsers, including Opera Air, Yandex, Chromium, Thorium, Cent, Cốc Cốc, Comodo Dragon, Epic, and the Beta, Dev and Canary channels of Chrome, Edge and Brave.
- New store listing images and text for the Chrome Web Store, Edge Add-ons and Opera add-ons (`store/`).

## 2.0.4

- Popunder protection: ad tabs that a page opens to one of 3,333 ad networks close themselves, including ones that hide their opener. On myflixerz, six clicks opened 4 ad tabs without the extension and none with it.
- A tab you navigate to an ad network yourself stays open and shows a "blocked" page instead.
- New test: `tests/test_popups.py`.

## 2.0.3

- Blocks YieldPilot, a first-party ad system on streaming sites (myflixerz, soap2day, onlyflix and others) that serves popunders and fake "prove you are human" popups from the site's own domain.
- Blocks the holdbitter.com ad CDN.

## 2.0.2

- Faster per-site hiding lookups in the background worker.
- Speed tests: load time, CPU and memory with and without the extension.
- Tested on 39 sites: 206 visible ads without the extension, 0 with it.
- Security review fixes: stricter selector validation, no page-visible globals, CSS injected only into the requesting document.
- Project docs: privacy policy, security policy, contributing guide, issue forms.

## 2.0.1

- Redesigned popup: bundled brand fonts, glowing 3D coin with a turning ring, the site's icon, and separate counts for requests stopped and ad boxes hidden.

## 2.0.0

- Blocking now uses EasyList, EasyPrivacy, uBlock Origin's lists, Liste FR and Liste AR: about 17,000 blocking rules and 15,700 hiding rules.
- About 4,600 per-site scriptlets that switch off anti-adblock walls, popunders and ad timers.
- Windows installer.
- New website with a 3D demo and measured results.
- Relicensed under GPL-3.0 to match the filter lists.

## 1.0.0

- First release: curated network blocking, element hiding, YouTube ad removal, per-site pause.

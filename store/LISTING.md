# Chrome Web Store listing: Hib Remover Ads

Upload: `hib-remover-ads-1.0.0.zip`
Screenshots (upload all three, in order): `screenshot-1.png`, `screenshot-2.png`, `screenshot-3.png`
Small promo tile: `promo-small-440x280.png`
Icon: `../src/icons/on-128.png`
Category: Privacy & Security (Confidentialité/sécurité)
Language: English (add French too: Store > Listing > add language)

## Summary (from manifest)
Ad remover and ad blocker for YouTube and every site. Blocks video ads, popups and trackers. Pause on any site in one click.

## Description
Hib Remover Ads removes ads from YouTube and the rest of the web.

- Removes YouTube video ads, overlays and sponsored cards
- Blocks banners, popups and trackers from about 120 ad networks
- Hides leftover empty ad boxes so pages look clean
- Shows how many ads were blocked on each page and in total
- Pause it on one site with one click, or turn it off everywhere

No account and no setup. Hib Remover Ads collects no data: everything runs inside your browser.

## Single purpose
Blocks and hides advertisements on web pages and YouTube.

## Permission justifications
- declarativeNetRequest: block requests to known ad and tracker servers.
- declarativeNetRequestFeedback: count blocked requests for the per-page counter in the popup.
- scripting: inject the element-hiding and YouTube ad-removal scripts, and skip them on sites the user paused.
- storage: remember paused sites, the on/off switch and the blocked counter.
- alarms: save the blocked counter periodically.
- Host permission <all_urls>: ads appear on every site, so blocking must work on every site.
- Remote code: No.

## Data usage
Declare that no user data is collected. Tick the three certification boxes.

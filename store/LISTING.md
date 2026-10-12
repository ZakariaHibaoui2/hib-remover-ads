# Store listing: Hib Remover Ads

Everything needed to publish Hib Remover Ads on the browser stores. Once it is listed, people install it with one click ("Add to Chrome") and the Windows SmartScreen warning no longer applies.

| Store | Cost | Sign up | Covers |
|---|---|---|---|
| Chrome Web Store | $5, once | https://chrome.google.com/webstore/devconsole | Chrome, Brave, Opera, Vivaldi, Yandex and other Chromium browsers |
| Microsoft Edge Add-ons | Free | https://partner.microsoft.com/dashboard/microsoftedge | Edge |
| Opera add-ons | Free | https://addons.opera.com/developer/ | Opera, Opera GX |

Review usually takes 1 to 7 days.

## Chrome Web Store, step by step

1. Open https://chrome.google.com/webstore/devconsole and sign in with your Google account.
2. Accept the developer agreement and pay the one-time $5 registration fee with your card.
3. In **Account**, set a publisher name (Hib Remover Ads) and verify your contact email.
4. Click **New item** and upload `hib-remover-ads.zip` from the latest release.
5. **Store listing** tab: paste the summary and description below, set the category and language, upload the icon, the 5 screenshots and the small promo tile, and add the website and support links.
6. **Privacy** tab: paste the single purpose and each permission justification below, answer "No" to remote code, tick "I do not collect user data" and the three certification boxes, and paste the privacy policy link.
7. **Distribution** tab: Public, all regions.
8. Click **Submit for review**. Google emails you when it's approved, usually in 1 to 7 days.

For later updates, upload the new zip in **Package** and submit again.

## Edge Add-ons and Opera add-ons

Both are free and use the same zip, text and images. For Edge, open https://partner.microsoft.com/dashboard/microsoftedge, enrol with your Microsoft account, then use **Create new extension**. For Opera, sign in at https://addons.opera.com/developer/ and use **Upload extension**.

## Files to upload

- Package: `hib-remover-ads.zip` from the latest GitHub release
- Screenshots, 1280×800, in this order: `listing/screenshot-1.png` … `listing/screenshot-5.png`
- Small promo tile, 440×280: `promo-small-440x280.png`
- Icon, 128×128: `../src/icons/on-128.png`
- Category: Privacy & Security (Confidentialité et sécurité)
- Language: English. Add French as a second language if you like.
- Website: https://zakariahibaoui2.github.io/hib-remover-ads/
- Support: https://github.com/ZakariaHibaoui2/hib-remover-ads/issues
- Privacy policy: https://github.com/ZakariaHibaoui2/hib-remover-ads/blob/main/PRIVACY.md

The screenshots are drawn from `tools/store_images.html`. Redraw them after a change with `python tools/store_images.py`.

## Summary (132 characters max)

Free ad blocker for YouTube and every site. Blocks video ads, popups, popunder tabs and trackers. Private, fast and open source.

## Description

Hib Remover Ads removes ads from YouTube and the rest of the web, and makes pages load faster.

What it blocks
- YouTube video ads, overlays and sponsored cards
- Banner ads, text ads and video ads on every site
- Popup and popunder ads: ad tabs that a site opens close themselves
- Fake "verify you're human" and "you won" pages
- Trackers and malicious ads
- "Turn off your ad blocker" walls

How well it works
- Built on the same filter lists as the big blockers: EasyList, EasyPrivacy, uBlock Origin's lists, Liste FR and Liste AR, about 17,000 blocking rules and 15,700 hiding rules
- Tested on 39 popular sites: 206 visible ads without it, 0 with it
- 100/100 on adblock-tester.com
- Pages load faster because ads never download: cnn.com went from 35.9 s to 4.3 s in our test

Private by design
- No account, no analytics, no servers
- Nothing you browse ever leaves your browser
- Open source under GPL-3.0: https://github.com/ZakariaHibaoui2/hib-remover-ads

Easy to control
- See how many ads were blocked on each page and in total
- Pause it on one site with one click, or turn it off everywhere

## Single purpose

Blocks and hides advertisements, popups and trackers on web pages, including YouTube.

## Permission justifications

- declarativeNetRequest: block requests to ad and tracker servers before they download.
- declarativeNetRequestFeedback: count the requests blocked on each page for the counter in the popup.
- scripting: inject the element-hiding styles, the YouTube ad remover and the per-site fixes, and skip them on sites the user paused.
- storage: remember paused sites, the on/off switch and the blocked counter.
- alarms: save the blocked counter periodically.
- favicon: show the current site's icon in the popup.
- Host permission <all_urls>: ads appear on every site, so blocking has to work on every site.
- Remote code: No. All code and filter lists are inside the package.

## Data usage

Declare that no user data is collected, and tick the three certification boxes.

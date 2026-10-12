// Source of truth for what Hush blocks. Run `node tools/build.mjs` after editing.

// Ad servers, ad exchanges and popunder networks. Subdomains are matched too.
export const AD_DOMAINS = [
  // Google ads
  'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
  'adservice.google.com', 'pagead2.googlesyndication.com', 'googletagservices.com',
  'securepubads.g.doubleclick.net',
  // Amazon / Microsoft / Meta ad endpoints
  'amazon-adsystem.com', 'aax.amazon-adsystem.com', 'ads.linkedin.com',
  'bat.bing.com', 'ads.microsoft.com', 'an.facebook.com',
  // Exchanges and SSPs
  'adnxs.com', 'adsrvr.org', 'pubmatic.com', 'rubiconproject.com', 'openx.net',
  'casalemedia.com', 'indexww.com', 'criteo.com', 'criteo.net', 'smartadserver.com',
  'yieldmo.com', 'sharethrough.com', 'triplelift.com', '3lift.com', 'teads.tv',
  'media.net', 'contextweb.com', 'sovrn.com', 'lijit.com', 'districtm.io',
  'adform.net', 'adition.com', 'yieldlab.net', 'improvedigital.com', '360yield.com',
  'smaato.net', 'inmobi.com', 'mopub.com', 'applovin.com', 'unityads.unity3d.com',
  'adcolony.com', 'vungle.com', 'chartboost.com', 'spotxchange.com', 'spotx.tv',
  'springserve.com', 'stickyadstv.com', 'tremorhub.com',
  'yahoo-ads.com', 'ads.yahoo.com', 'adtech.com', 'advertising.com', 'gumgum.com',
  'kargo.com', 'undertone.com', 'zedo.com', 'bidswitch.net', 'adkernel.com',
  'onetag-sys.com', 'richaudience.com', 'seedtag.com', 'emxdgt.com',
  'admixer.net', 'adhese.com', 'adpone.com',
  'vidoomy.com', 'adsafeprotected.com', 'moatads.com',
  'doubleverify.com', 'serving-sys.com', 'flashtalking.com', 'innovid.com',
  'eyeota.net', 'bluekai.com', 'krxd.net', 'quantserve.com',
  'adroll.com', 'outbrain.com', 'outbrainimg.com', 'taboola.com', 'revcontent.com',
  'mgid.com', 'zergnet.com', 'nativo.com', 'content.ad', 'plista.com', 'ligatus.com',
  'buysellads.com', 'carbonads.net', 'adzerk.net', 'adbutler.com', 'adblade.com',
  // Popunders, redirect and aggressive networks
  'popads.net', 'popcash.net', 'propellerads.com', 'propellerclick.com',
  'adsterra.com', 'adsterratools.com', 'exoclick.com', 'exosrv.com', 'juicyads.com',
  'trafficjunky.net', 'trafficstars.com', 'hilltopads.net', 'clickadu.com',
  'adcash.com', 'onclickads.net', 'popunder.net', 'admaven.com', 'ad-maven.com',
  'richpush.co', 'pushame.com', 'evadav.com', 'galaksion.com', 'monetag.com',
  'holdbitter.com',
  'a-ads.com', 'coinzilla.com', 'bitmedia.io', 'adskeeper.com', 'adskeeper.co.uk',
];

// Path-level rules for first-party ad endpoints that cannot be blocked by domain.
export const URL_FILTERS = [
  '||youtube.com/pagead/',
  '||youtube.com/api/stats/ads',
  '||youtube.com/ptracking',
  '||youtube.com/get_midroll_',
  '||youtube.com/youtubei/v1/player/ad_break',
  '||google.com/pagead/',
  '||facebook.com/tr/',
  '||reddit.com/api/v1/ads',
  '||twitter.com/i/ads',
  '/prebid.js',
  '/pubads_impl',
  '/adsbygoogle.js',
  // YieldPilot: popunders and fake "prove you are human" interstitials served
  // from the site's own domain (myflixerz, soap2day, onlyflix and others).
  '/__yield/',
  '/yieldpilot',
];

// Elements hidden on every page. Keep these specific: a loose selector here
// hides real content across the whole web.
export const GENERIC_SELECTORS = [
  'ins.adsbygoogle', '.adsbygoogle', '.yieldpilot-slot',
  '[id^="google_ads_iframe"]', '[id^="div-gpt-ad"]', '[data-google-query-id]',
  'iframe[src*="doubleclick.net"]', 'iframe[src*="googlesyndication.com"]',
  'iframe[src*="amazon-adsystem.com"]', 'iframe[id^="google_ads_"]',
  '[data-ad-slot]', '[data-ad-unit]', '[data-adunit]', '[data-ad-client]',
  '.ad-slot', '.ad-banner', '.ad-unit', '.ad-leaderboard', '.ad-placeholder',
  '.advertisement', '.adsbox', '.sponsored-ad', '.GoogleActiveViewElement',
  'amp-ad', 'amp-embed[type="taboola"]', 'amp-embed[type="outbrain"]',
  '.trc_related_container', '[id^="taboola-"]', '.OUTBRAIN', '.ob-widget',
  '#carbonads', '[aria-label="Advertisement"]', '[aria-label="advertisement"]',
  '[id^="mgid_"]', '.mgbox', '[data-revcontent-widget]',
  // Empty containers that big publishers leave behind once the ad itself is gone.
  '.ad-slot-header', '.ad-slot-header__wrapper', '.ad-slot-rail', '.ad-slot__wrapper',
  '.ad-feedback-link', 'div[class*="cls-ad-"]', '[id^="sda-"]', '.gemini-ad',
  '[data-content="Advertisement"]', '.ad-wrapper--header', '.top-ad-container',
];

// YouTube-only elements (custom elements, so they never match elsewhere).
export const YOUTUBE_SELECTORS = [
  'ytd-ad-slot-renderer', 'ytd-in-feed-ad-layout-renderer', 'ytd-display-ad-renderer',
  'ytd-promoted-sparkles-web-renderer', 'ytd-promoted-video-renderer',
  'ytd-compact-promoted-video-renderer', 'ytd-banner-promo-renderer',
  'ytd-statement-banner-renderer', 'ytd-search-pyv-renderer',
  'ytd-player-legacy-desktop-watch-ads-renderer', 'ytd-companion-slot-renderer',
  'ytd-action-companion-ad-renderer', 'ytd-video-masthead-ad-v3-renderer',
  'ytd-primetime-promo-renderer', 'ytd-merch-shelf-renderer',
  'ytd-rich-item-renderer:has(ytd-ad-slot-renderer)',
  'ytd-rich-section-renderer:has(ytd-statement-banner-renderer)',
  'ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-ads"]',
  '#masthead-ad', '#player-ads', '#panels > ytd-ads-engagement-panel-content-renderer',
  '.ytp-ad-overlay-container', '.ytp-ad-overlay-slot', '.ytp-ad-image-overlay',
  '.ytp-featured-product', '.ytp-suggested-action-badge',
  'ad-slot-renderer', 'ytm-promoted-sparkles-web-renderer', 'ytm-companion-ad-renderer',
  'tp-yt-paper-dialog:has(ytd-enforcement-message-view-model)',
  'ytd-enforcement-message-view-model',
];

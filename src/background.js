// Hib Remover Ads service worker: owns blocking state, per-site pauses and counters.
//
// Storage layout
//   local:   { enabled, paused: [host], total, lastMatchTs }
//   session: { tabs: { [tabId]: { since, net, cosmetic } } }
//
// Counting: the toolbar badge is Chrome's own live count of blocked requests,
// bumped by us for hidden elements. The popup and the all-time total come from
// getMatchedRules, which Chrome limits to 20 calls per 10 minutes, so it is only
// called from a 2-minute alarm and when the popup opens. Matches are kept for
// 5 minutes, so the alarm never misses any.

// 'ads' is our own curated list; 'block' and 'allow' are compiled from EasyList,
// EasyPrivacy and uBlock Origin's lists by tools/filterlists.py. Only block
// rulesets count toward the numbers users see.
const RULESETS = ['ads', 'block', 'allow'];
const COUNTED = new Set(['ads', 'block']);
const PAUSE_RULE_ID = 1;
const YT_MATCHES = ['*://*.youtube.com/*', '*://*.youtube-nocookie.com/*'];
const VALID_HOST = /^[a-z0-9-]+(\.[a-z0-9-]+)*$/;

const SCRIPTS = [
  {
    id: 'hib-generic',
    css: ['content/generic.css'],
    matches: ['<all_urls>'],
    runAt: 'document_start',
    allFrames: true,
  },
  {
    id: 'hib-cosmetic',
    js: ['content/selectors.js', 'content/cosmetic.js'],
    matches: ['<all_urls>'],
    runAt: 'document_start',
    allFrames: true,
  },
  {
    id: 'hib-yt-main',
    js: ['content/yt-main.js'],
    matches: YT_MATCHES,
    runAt: 'document_start',
    allFrames: true,
    world: 'MAIN',
  },
  {
    id: 'hib-yt',
    js: ['content/youtube.js'],
    matches: YT_MATCHES,
    runAt: 'document_start',
    allFrames: true,
  },
];

// All state changes run one at a time so concurrent messages can't clobber counters.
let queue = Promise.resolve();
const serial = (fn) => {
  const run = queue.then(fn);
  queue = run.catch((err) => console.error('[hib]', err));
  return run;
};

const normalizeHost = (host) => (host || '').toLowerCase().replace(/^www\./, '');

const hostOf = (url) => {
  try {
    const u = new URL(url);
    if (!/^https?:$/.test(u.protocol)) return '';
    const host = normalizeHost(u.hostname);
    return VALID_HOST.test(host) ? host : '';
  } catch {
    return '';
  }
};

const isPausedHost = (host, paused) =>
  !!host && paused.some((p) => host === p || host.endsWith('.' + p));

async function getSettings() {
  const { enabled = true, paused = [] } = await chrome.storage.local.get(['enabled', 'paused']);
  return { enabled, paused: paused.filter((h) => VALID_HOST.test(h)) };
}

// ---- Filter data -----------------------------------------------------------

const loadJson = (path) => fetch(chrome.runtime.getURL(path)).then((r) => r.json());
let cosmeticData;
// Site lists become Sets so the per-frame lookup is constant time.
const getCosmetic = () => (cosmeticData ??= loadJson('rules/cosmetic.json').then((d) => ({
  ...d,
  noCosmeticSet: new Set(d.noCosmetic),
  noGenericSet: new Set(d.noGeneric),
  partialGenericSet: new Set(d.partialGeneric),
})));

// Entity rules ("example.*") can't be match patterns, so expand common suffixes.
const ENTITY_TLDS = ['com', 'net', 'org', 'io', 'co', 'to', 'tv', 'me', 'cc', 'ws', 'info', 'biz',
  'fr', 'de', 'es', 'it', 'nl', 'be', 'ch', 'pl', 'ru', 'ma', 'dz', 'tn', 'eg', 'sa', 'ae',
  'co.uk', 'com.br', 'com.tr', 'in', 'xyz', 'site', 'online', 'live', 'pro', 'top', 'lol'];
const hostPatterns = (hosts) => [...new Set(hosts.flatMap((h) => (h.endsWith('.*')
  ? ENTITY_TLDS.map((t) => `*://*.${h.slice(0, -1)}${t}/*`)
  : [`*://*.${h}/*`])))];

// Walks a host up through its parent domains, plus entity forms.
const hostKeys = (host) => {
  const labels = host.split('.');
  const keys = [];
  for (let i = 0; i < labels.length - 1; i++) {
    keys.push(labels.slice(i).join('.'));
    if (labels.length - i - 1 <= 2) keys.push(`${labels[i]}.*`);
  }
  return keys;
};

const cssCache = new Map();
// Element hiding for one site: its own selectors, plus generic ones when the
// static generic stylesheet is switched off there because of exceptions.
async function cosmeticFor(host) {
  if (cssCache.has(host)) return cssCache.get(host);
  const data = await getCosmetic();
  const keys = hostKeys(host);
  const has = (set) => keys.some((k) => set.has(k));
  let result = { css: '', selectors: [] };
  if (!has(data.noCosmeticSet)) {
    const except = new Set(keys.flatMap((k) => data.exceptions[k] || []));
    const own = keys.flatMap((k) => data.specific[k] || []).filter((s) => !except.has(s));
    const generic = !has(data.noGenericSet) && has(data.partialGenericSet)
      ? data.generic.filter((s) => !except.has(s))
      : [];
    const all = [...new Set([...own, ...generic])];
    result = {
      css: all.length ? `${all.join(',')}{display:none!important}` : '',
      selectors: own,
    };
  }
  if (cssCache.size > 200) cssCache.clear();
  cssCache.set(host, result);
  return result;
}

async function injectCosmetic(sender, host) {
  const { css, selectors } = await cosmeticFor(host);
  if (css) {
    try {
      await chrome.scripting.insertCSS({
        // The exact document that asked, so a frame that navigated meanwhile gets nothing.
        target: sender.documentId
          ? { tabId: sender.tab.id, documentIds: [sender.documentId] }
          : { tabId: sender.tab.id, frameIds: [sender.frameId] },
        css,
        origin: 'USER',
      });
    } catch {
      // Frame went away or a selector was rejected; the rest of the blocking still works.
    }
  }
  return selectors;
}

async function registerScripts(paused) {
  const pausedMatches = paused.flatMap((h) => [`*://${h}/*`, `*://*.${h}/*`]);
  const data = await getCosmetic();
  const scriptletHosts = await loadJson('scriptlets/hosts.json');
  const noGeneric = hostPatterns([...data.noGeneric, ...data.partialGeneric, ...data.noCosmetic]);
  const scripts = [
    ...SCRIPTS,
    {
      id: 'hib-scriptlets',
      js: ['scriptlets/config.js', 'scriptlets/engine.js'],
      matches: hostPatterns(scriptletHosts),
      runAt: 'document_start',
      allFrames: true,
      world: 'MAIN',
    },
  ].map((s) => {
    const excludeMatches = [...pausedMatches, ...(s.id === 'hib-generic' ? noGeneric : [])];
    return excludeMatches.length ? { ...s, excludeMatches } : s;
  });
  try {
    await chrome.scripting.registerContentScripts(scripts);
  } catch (err) {
    // Never leave the web unprotected because of one bad pause entry.
    console.error('[hib] register with exclusions failed, registering without', err);
    // Fall back to the core scripts, still honouring the user's paused sites.
    const registered = await chrome.scripting.getRegisteredContentScripts();
    if (registered.length) await chrome.scripting.unregisterContentScripts({ ids: registered.map((s) => s.id) });
    await chrome.scripting.registerContentScripts(
      SCRIPTS.map((s) => (pausedMatches.length ? { ...s, excludeMatches: pausedMatches } : s)),
    );
  }
}

// Bring rulesets, the pause rule, content scripts and the icon in line with settings.
async function applySettings() {
  const { enabled, paused } = await getSettings();

  await chrome.declarativeNetRequest.updateEnabledRulesets(
    enabled ? { enableRulesetIds: RULESETS } : { disableRulesetIds: RULESETS },
  );

  const dynamic = await chrome.declarativeNetRequest.getDynamicRules();
  await chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: dynamic.map((r) => r.id),
    addRules: paused.length
      ? [{
          id: PAUSE_RULE_ID,
          priority: 100,
          action: { type: 'allowAllRequests' },
          condition: { requestDomains: paused, resourceTypes: ['main_frame', 'sub_frame'] },
        }]
      : [],
  });

  const registered = await chrome.scripting.getRegisteredContentScripts();
  if (registered.length) {
    await chrome.scripting.unregisterContentScripts({ ids: registered.map((s) => s.id) });
  }
  if (enabled) await registerScripts(paused);

  const state = enabled ? 'on' : 'off';
  await chrome.action.setIcon({
    path: { 16: `icons/${state}-16.png`, 32: `icons/${state}-32.png` },
  });
}

// ---- Counting -------------------------------------------------------------

async function getTabs() {
  const { tabs = {} } = await chrome.storage.session.get('tabs');
  return tabs;
}

// Tabs we haven't seen start (e.g. open before install) count everything.
const tabEntry = (tabs, tabId) => (tabs[tabId] ??= { since: 0, net: 0, cosmetic: 0 });

// Pull network matches since the last pull and credit them to open tabs and the total.
async function flushMatches() {
  const { lastMatchTs = 0, total = 0 } = await chrome.storage.local.get(['lastMatchTs', 'total']);
  let info;
  try {
    info = await chrome.declarativeNetRequest.getMatchedRules({ minTimeStamp: lastMatchTs + 1 });
  } catch (err) {
    // Over Chrome's call quota; the next alarm picks these matches up.
    console.warn('[hib] getMatchedRules', err.message);
    return;
  }
  const hits = info.rulesMatchedInfo.filter((m) => COUNTED.has(m.rule.rulesetId));
  if (!hits.length) return;

  const open = new Set((await chrome.tabs.query({})).map((t) => t.id));
  const tabs = await getTabs();
  let newest = lastMatchTs;
  for (const hit of hits) {
    newest = Math.max(newest, hit.timeStamp);
    if (!open.has(hit.tabId)) continue;
    const entry = tabEntry(tabs, hit.tabId);
    if (hit.timeStamp >= entry.since) entry.net += 1;
  }
  await chrome.storage.session.set({ tabs });
  await chrome.storage.local.set({ total: total + hits.length, lastMatchTs: newest });
}

async function addCosmetic(tabId, count) {
  const tabs = await getTabs();
  tabEntry(tabs, tabId).cosmetic += count;
  const { total = 0 } = await chrome.storage.local.get('total');
  await chrome.storage.session.set({ tabs });
  await chrome.storage.local.set({ total: total + count });
  try {
    await chrome.declarativeNetRequest.setExtensionActionOptions({
      tabUpdate: { tabId, increment: count },
    });
  } catch {
    // Tab closed in the meantime.
  }
}

// `since` is when the page started, not when this queued call runs, so blocks
// that happen while the queue is busy still count toward the new page.
async function resetTab(tabId, since) {
  const tabs = await getTabs();
  tabs[tabId] = { since, net: 0, cosmetic: 0 };
  await chrome.storage.session.set({ tabs });
}

async function forgetTab(tabId) {
  const tabs = await getTabs();
  delete tabs[tabId];
  await chrome.storage.session.set({ tabs });
}

// ---- Popup API ------------------------------------------------------------

async function getStats(tabId, url) {
  await flushMatches();
  const { enabled, paused } = await getSettings();
  const { total = 0 } = await chrome.storage.local.get('total');
  const entry = (await getTabs())[tabId];
  const host = hostOf(url);
  return {
    enabled,
    host,
    paused: isPausedHost(host, paused),
    page: entry ? entry.net + entry.cosmetic : 0,
    net: entry ? entry.net : 0,
    cosmetic: entry ? entry.cosmetic : 0,
    total,
  };
}

async function setEnabled(enabled) {
  await chrome.storage.local.set({ enabled });
  await applySettings();
}

async function setPaused(host, pause) {
  host = normalizeHost(host);
  if (!VALID_HOST.test(host)) return false;
  const { paused } = await getSettings();
  // Drop the host and anything it covers, so unpausing "example.com" also clears
  // a pause set on "news.example.com" and vice versa.
  const rest = paused.filter((p) => !(p === host || p.endsWith('.' + host) || host.endsWith('.' + p)));
  await chrome.storage.local.set({ paused: pause ? [...rest, host].sort() : rest });
  await applySettings();
  return true;
}

// ---- Wiring ---------------------------------------------------------------

async function init() {
  await chrome.declarativeNetRequest.setExtensionActionOptions({ displayActionCountAsBadgeText: true });
  await chrome.action.setBadgeBackgroundColor({ color: '#F3B23C' });
  await chrome.action.setBadgeTextColor?.({ color: '#10272B' });
  await chrome.alarms.create('flush', { periodInMinutes: 2 });
  await applySettings();
}

chrome.runtime.onInstalled.addListener(() => serial(init));
chrome.runtime.onStartup.addListener(() => serial(init));

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'flush') serial(flushMatches);
});

// New URL in a tab (including in-app navigation). Reloads are caught by the
// top-frame content script's 'pageStart' message instead.
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (change.url) {
    const since = Date.now();
    serial(() => resetTab(tabId, since));
  }
});

chrome.tabs.onRemoved.addListener((tabId) => serial(() => forgetTab(tabId)));

const fromExtensionPage = (sender) => sender.url?.startsWith(chrome.runtime.getURL(''));

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const tabId = sender.tab?.id;
  switch (msg?.type) {
    case 'pageStart': {
      if (tabId != null && sender.frameId === 0) {
        const since = Math.min(Date.now(), Number(msg.at) || Date.now());
        serial(() => resetTab(tabId, since));
      }
      return false;
    }
    case 'cosmetic': {
      const host = hostOf(sender.url);
      if (tabId == null || !host) return false;
      injectCosmetic(sender, host).then(reply, () => reply([]));
      return true;
    }
    case 'hidden': {
      const count = Math.min(500, Math.max(0, Math.floor(Number(msg.count) || 0)));
      if (tabId != null && count) serial(() => addCosmetic(tabId, count));
      return false;
    }
    case 'adTab': {
      // From our blocked-ad page: close it if another tab opened it (a popunder).
      if (fromExtensionPage(sender) && tabId != null && sender.tab.openerTabId != null) {
        chrome.tabs.remove(tabId).catch(() => {});
      }
      return false;
    }
    case 'stats':
      if (!fromExtensionPage(sender)) return false;
      serial(() => getStats(msg.tabId, msg.url)).then(reply, () => reply(null));
      return true;
    case 'setEnabled':
      if (!fromExtensionPage(sender)) return false;
      serial(() => setEnabled(!!msg.enabled)).then(() => reply(true), () => reply(false));
      return true;
    case 'setPaused':
      if (!fromExtensionPage(sender)) return false;
      serial(() => setPaused(msg.host, !!msg.paused)).then(reply, () => reply(false));
      return true;
    default:
      return false;
  }
});

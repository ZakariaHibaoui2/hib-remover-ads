// Hush service worker: owns blocking state, per-site pauses and counters.
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

const RULESET = 'ads';
const PAUSE_RULE_ID = 1;
const YT_MATCHES = ['*://*.youtube.com/*', '*://*.youtube-nocookie.com/*'];
const VALID_HOST = /^[a-z0-9-]+(\.[a-z0-9-]+)*$/;

const SCRIPTS = [
  {
    id: 'hush-cosmetic',
    js: ['content/selectors.js', 'content/cosmetic.js'],
    matches: ['<all_urls>'],
    runAt: 'document_start',
    allFrames: true,
  },
  {
    id: 'hush-yt-main',
    js: ['content/yt-main.js'],
    matches: YT_MATCHES,
    runAt: 'document_start',
    allFrames: true,
    world: 'MAIN',
  },
  {
    id: 'hush-yt',
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
  queue = run.catch((err) => console.error('[hush]', err));
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

async function registerScripts(paused) {
  const excludeMatches = paused.flatMap((h) => [`*://${h}/*`, `*://*.${h}/*`]);
  try {
    await chrome.scripting.registerContentScripts(
      SCRIPTS.map((s) => (excludeMatches.length ? { ...s, excludeMatches } : s)),
    );
  } catch (err) {
    // Never leave the web unprotected because of one bad pause entry.
    console.error('[hush] register with pauses failed, registering without', err);
    await chrome.scripting.registerContentScripts(SCRIPTS);
  }
}

// Bring rulesets, the pause rule, content scripts and the icon in line with settings.
async function applySettings() {
  const { enabled, paused } = await getSettings();

  await chrome.declarativeNetRequest.updateEnabledRulesets(
    enabled ? { enableRulesetIds: [RULESET] } : { disableRulesetIds: [RULESET] },
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
    console.warn('[hush] getMatchedRules', err.message);
    return;
  }
  const hits = info.rulesMatchedInfo.filter((m) => m.rule.rulesetId === RULESET);
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
    case 'hidden': {
      const count = Math.min(500, Math.max(0, Math.floor(Number(msg.count) || 0)));
      if (tabId != null && count) serial(() => addCosmetic(tabId, count));
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

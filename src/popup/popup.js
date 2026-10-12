const $ = (id) => document.getElementById(id);
const t = (key, sub) => chrome.i18n.getMessage(key, sub) || key;
const lang = chrome.i18n.getUILanguage();
// Latin digits everywhere, as Moroccan and most Arabic sites use them.
const fmt = new Intl.NumberFormat(lang, { numberingSystem: 'latn' });
const fmt1 = new Intl.NumberFormat(lang, { numberingSystem: 'latn', maximumFractionDigits: 1 });

document.documentElement.lang = lang;
document.documentElement.dir = t('@@bidi_dir');
for (const el of document.querySelectorAll('[data-i18n]')) el.textContent = t(el.dataset.i18n);
for (const el of document.querySelectorAll('[data-i18n-label]')) el.setAttribute('aria-label', t(el.dataset.i18nLabel));

// What one blocked request saves, as measured in our speed tests (median),
// so the weekly numbers stay on the cautious side.
const MS_PER_REQUEST = 5;
const KB_PER_REQUEST = 10;
const duration = (ms) => {
  const s = ms / 1000;
  return s < 60 ? `${fmt.format(Math.round(s))} ${t('unitSec')}` : `${fmt.format(Math.round(s / 60))} ${t('unitMin')}`;
};
const size = (kb) => (kb < 1024
  ? `${fmt.format(Math.round(kb))} ${t('unitKB')}`
  : `${(kb < 10240 ? fmt1 : fmt).format(kb / 1024)} ${t('unitMB')}`);

const browserName = () => {
  if (navigator.brave) return 'Brave';
  const brands = (navigator.userAgentData?.brands || []).map((b) => b.brand).join(' ');
  if (/Edge/.test(brands)) return 'Edge';
  if (/Opera/.test(brands)) return 'Opera';
  return /Chrome/.test(brands) ? 'Chrome' : 'Other';
};

const send = (msg) => chrome.runtime.sendMessage(msg);

let tab;
let stats;
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

// Counts a number up from where it was, then gives it a small bump.
function countTo(el, to) {
  const from = Number(el.dataset.value || 0);
  el.dataset.value = to;
  if (reduced || from === to) {
    el.textContent = fmt.format(to);
    return;
  }
  const start = performance.now();
  const dur = Math.min(900, 300 + Math.abs(to - from) * 40);
  const step = (now) => {
    const t = Math.min(1, (now - start) / dur);
    el.textContent = fmt.format(Math.round(from + (to - from) * (1 - (1 - t) ** 3)));
    if (t < 1) return requestAnimationFrame(step);
    el.classList.remove('bump');
    void el.offsetWidth; // restart the animation
    el.classList.add('bump');
  };
  requestAnimationFrame(step);
}

// The coin leans toward the pointer and spins in when the popup opens.
const coin = document.querySelector('.coin');
if (!reduced) {
  document.addEventListener('pointermove', (e) => {
    const r = coin.getBoundingClientRect();
    const x = (e.clientX - (r.left + r.width / 2)) / innerWidth;
    const y = (e.clientY - (r.top + r.height / 2)) / innerHeight;
    coin.style.setProperty('--ry', `${(x * 50).toFixed(1)}deg`);
    coin.style.setProperty('--rx', `${(-y * 40).toFixed(1)}deg`);
  });
  document.documentElement.addEventListener('pointerleave', () => {
    coin.style.setProperty('--ry', '0deg');
    coin.style.setProperty('--rx', '0deg');
  });
  document.body.classList.add('intro');
  setTimeout(() => document.body.classList.remove('intro'), 1300);
}

function render() {
  const { enabled, host, paused, page, total, net = 0, cosmetic = 0, zapped = 0, week = { net: 0, cosmetic: 0 } } = stats;
  const state = !host ? 'unsupported' : !enabled ? 'off' : paused ? 'paused' : 'on';
  document.body.dataset.state = state;

  $('power').setAttribute('aria-checked', String(enabled));
  $('host').textContent = host || t('thisPage');
  $('status').textContent = t({
    on: 'statusOn', paused: 'statusPaused', off: 'statusOff', unsupported: 'statusUnsupported',
  }[state]);

  countTo($('page'), page);
  $('page-label').textContent = t(page === 1 ? 'adsBlockedOne' : 'adsBlockedMany');
  countTo($('net'), net);
  countTo($('cosmetic'), cosmetic);
  $('total').textContent = fmt.format(total);

  $('week-ads').textContent = fmt.format(week.net + week.cosmetic);
  const savedMs = week.net * MS_PER_REQUEST;
  $('week-time').textContent = savedMs === 0 ? duration(0)
    : savedMs < 1000 ? `< ${duration(1000)}` : `≈ ${duration(savedMs)}`;
  $('week-data').textContent = `≈ ${size(week.net * KB_PER_REQUEST)}`;
  document.querySelector('.week dl').title = t('weekHint');

  $('zapped').hidden = !(host && zapped);
  $('zapped-text').textContent = t('zappedHere', [fmt.format(zapped)]);
  $('zap').disabled = state !== 'on';
  if (host && tab?.url) {
    const fav = new URL(chrome.runtime.getURL('/_favicon/'));
    fav.searchParams.set('pageUrl', tab.url);
    fav.searchParams.set('size', '32');
    $('fav').src = fav.href;
    // Origin and path only: query strings can carry personal data.
    const pageUrl = new URL(tab.url);
    const report = new URL('https://github.com/ZakariaHibaoui2/hib-remover-ads/issues/new');
    report.search = new URLSearchParams({
      template: 'ad-got-through.yml',
      title: `Ad on ${host}`,
      url: pageUrl.origin + pageUrl.pathname,
      version: chrome.runtime.getManifest().version,
      browser: browserName(),
    });
    $('report').href = report.href;
  }

  const pause = $('pause');
  pause.disabled = !enabled;
  $('pause-label').textContent = t(paused ? 'resumeSite' : 'pauseSite');
}

async function refresh() {
  stats = await send({ type: 'stats', tabId: tab?.id, url: tab?.url });
  if (stats) render();
}

async function act(msg) {
  for (const b of document.querySelectorAll('button')) b.disabled = true;
  const ok = await send(msg);
  if (ok && tab?.id != null && stats?.host) await chrome.tabs.reload(tab.id);
  for (const b of document.querySelectorAll('button')) b.disabled = false;
  await refresh();
}

$('zap').addEventListener('click', async () => {
  if (tab?.id == null) return;
  if (await send({ type: 'zapStart', tabId: tab.id })) window.close();
});
$('restore').addEventListener('click', () => act({ type: 'zapClear', host: stats.host }));
$('power').addEventListener('click', () => act({ type: 'setEnabled', enabled: !stats.enabled }));
$('pause').addEventListener('click', () =>
  act({ type: 'setPaused', host: stats.host, paused: !stats.paused }));

[tab] = await chrome.tabs.query({ active: true, currentWindow: true });
await refresh();

const $ = (id) => document.getElementById(id);
const fmt = new Intl.NumberFormat();

const send = (msg) => chrome.runtime.sendMessage(msg);

let tab;
let stats;

function render() {
  const { enabled, host, paused, page, total } = stats;
  const state = !host ? 'unsupported' : !enabled ? 'off' : paused ? 'paused' : 'on';
  document.body.dataset.state = state;

  $('power').setAttribute('aria-checked', String(enabled));
  $('host').textContent = host || 'This page';
  $('status').textContent = {
    on: 'Blocking ads on this site',
    paused: 'Paused on this site. Ads will load here.',
    off: 'Hib Remover Ads is off on every site',
    unsupported: 'Hib Remover Ads only runs on websites, not browser pages.',
  }[state];

  $('page').textContent = fmt.format(page);
  $('page-label').textContent = page === 1 ? 'ad blocked on this page' : 'ads blocked on this page';
  $('total').textContent = fmt.format(total);

  const pause = $('pause');
  pause.disabled = !enabled;
  pause.textContent = paused ? 'Resume blocking here' : 'Pause on this site';
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

$('power').addEventListener('click', () => act({ type: 'setEnabled', enabled: !stats.enabled }));
$('pause').addEventListener('click', () =>
  act({ type: 'setPaused', host: stats.host, paused: !stats.paused }));

[tab] = await chrome.tabs.query({ active: true, currentWindow: true });
await refresh();

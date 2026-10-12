const $ = (id) => document.getElementById(id);
const fmt = new Intl.NumberFormat();

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
  const { enabled, host, paused, page, total, net = 0, cosmetic = 0 } = stats;
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

  countTo($('page'), page);
  $('page-label').textContent = page === 1 ? 'ad blocked on this page' : 'ads blocked on this page';
  countTo($('net'), net);
  countTo($('cosmetic'), cosmetic);
  $('total').textContent = fmt.format(total);
  $('note').textContent = 'Open a website and Hib Remover Ads will start blocking its ads.';
  if (host && tab?.url) {
    const fav = new URL(chrome.runtime.getURL('/_favicon/'));
    fav.searchParams.set('pageUrl', tab.url);
    fav.searchParams.set('size', '32');
    $('fav').src = fav.href;
    $('report').href = `https://github.com/ZakariaHibaoui2/hib-remover-ads/issues/new?title=${encodeURIComponent(`Ads on ${host}`)}`;
  }

  const pause = $('pause');
  pause.disabled = !enabled;
  $('pause-label').textContent = paused ? 'Resume blocking here' : 'Pause on this site';
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

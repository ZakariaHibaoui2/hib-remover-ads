// Hides ad elements with a stylesheet and reports how many were hidden.
// Only registered on sites that aren't paused, so it never checks settings itself.
(() => {
  if (window.__hushCosmetic) return;
  window.__hushCosmetic = true;

  // After the extension updates or reloads, scripts left in open tabs lose their
  // connection and sendMessage throws instead of rejecting. Stop quietly then.
  let observer;
  const send = (msg) => {
    try {
      if (chrome.runtime?.id) return chrome.runtime.sendMessage(msg).catch(() => {});
    } catch {
      // Fall through: the extension context is gone.
    }
    observer?.disconnect();
    return Promise.resolve();
  };

  // Start this tab's per-page counter from the moment navigation began.
  if (window.top === window) {
    send({ type: 'pageStart', at: Math.floor(performance.timeOrigin) });
  }

  const { generic, youtube } = globalThis.HUSH_SELECTORS;
  const isYouTube = /(^|\.)youtube(-nocookie)?\.com$/.test(location.hostname);
  // Drop selectors this browser can't parse; one bad selector would void the whole list.
  const list = (isYouTube ? generic.concat(youtube) : generic)
    .filter((s) => CSS.supports(`selector(${s})`));
  let selector = list.join(',');

  const style = document.createElement('style');
  style.dataset.hush = '';
  style.textContent = list.map((s) => `${s}{display:none!important}`).join('\n');
  const attach = () => {
    if (!style.isConnected) (document.head || document.documentElement).appendChild(style);
  };
  attach();

  const seen = new WeakSet();
  const count = () => {
    attach(); // Some single-page apps wipe <head> on navigation.
    let n = 0;
    for (const el of document.querySelectorAll(selector)) {
      if (seen.has(el)) continue;
      seen.add(el);
      // Count each ad once, not once per nested match inside it.
      if (!el.parentElement?.closest(selector)) n++;
    }
    if (n) send({ type: 'hidden', count: n });
  };

  let timer;
  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(count, 700);
  };

  // Site-specific hiding from the filter lists. The background injects it as a
  // user stylesheet and sends back the selectors so those ads get counted too.
  send({ type: 'cosmetic' }).then((own) => {
    const extra = (Array.isArray(own) ? own : []).filter((s) => CSS.supports(`selector(${s})`));
    if (extra.length) {
      selector = [selector, ...extra].filter(Boolean).join(',');
      schedule();
    }
  }).catch(() => {});

  const start = () => {
    count();
    observer = new MutationObserver(schedule);
    observer.observe(document.documentElement, { childList: true, subtree: true });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();

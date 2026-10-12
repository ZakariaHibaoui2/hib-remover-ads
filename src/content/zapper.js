// Click-to-remove: injected into the top frame when the user picks "Remove
// something on this page" in the popup. Hover highlights an element, a click
// hides it and saves a selector for this site, Undo brings the last one back,
// Esc or Done leaves. Running it again while it's open closes it.
(() => {
  if (window.__hibZapper) {
    window.__hibZapper();
    return;
  }

  const t = (key, sub) => chrome.i18n.getMessage(key, sub) || key;
  const rtl = chrome.i18n.getMessage('@@bidi_dir') === 'rtl';

  // ---- UI, isolated from the page's styles ---------------------------------
  const host = document.createElement('hib-zapper');
  host.style.cssText = 'all:initial;position:fixed;inset:0;z-index:2147483647;pointer-events:none;';
  const root = host.attachShadow({ mode: 'closed' });
  root.innerHTML = `
    <style>
      :host { all: initial; }
      .box {
        position: fixed; pointer-events: none; display: none;
        border: 2px solid #f3b23c; border-radius: 4px;
        background: rgba(243, 178, 60, .18);
        box-shadow: 0 0 0 99999px rgba(14, 36, 39, .25);
        transition: all 90ms ease-out;
      }
      .tag {
        position: fixed; pointer-events: none; display: none;
        max-width: 60vw; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
        padding: 3px 8px; border-radius: 6px;
        background: #0e2427; color: #e8f3ef; font: 600 12px/1.4 system-ui, sans-serif;
      }
      .bar {
        position: fixed; left: 50%; top: 14px; transform: translateX(-50%);
        display: flex; align-items: center; gap: 10px;
        padding: 8px 8px 8px 16px; border-radius: 999px;
        background: #0e2427; color: #e8f3ef; pointer-events: auto;
        font: 500 14px/1.2 system-ui, "Segoe UI", sans-serif;
        box-shadow: 0 12px 32px rgba(0, 0, 0, .35), inset 0 0 0 1px #27494e;
        direction: ${rtl ? 'rtl' : 'ltr'};
      }
      .bar[dir="rtl"] { padding: 8px 16px 8px 8px; }
      .dot { width: 10px; height: 10px; border-radius: 50%; background: #f3b23c; flex: none; }
      .count { color: #94b3ab; font-size: 13px; }
      button {
        all: unset; cursor: pointer; padding: 7px 14px; border-radius: 999px;
        font: 700 13px/1 system-ui, sans-serif;
      }
      button:focus-visible { outline: 2px solid #f3b23c; outline-offset: 2px; }
      .undo { color: #e8f3ef; box-shadow: inset 0 0 0 1px #27494e; }
      .undo[disabled] { opacity: .4; cursor: default; }
      .done { background: #f3b23c; color: #0e2427; }
    </style>
    <div class="box"></div>
    <div class="tag"></div>
    <div class="bar" role="toolbar">
      <span class="dot"></span>
      <span class="hint"></span>
      <span class="count"></span>
      <button class="undo" type="button" disabled></button>
      <button class="done" type="button"></button>
    </div>`;
  const $ = (s) => root.querySelector(s);
  const box = $('.box');
  const tag = $('.tag');
  const bar = $('.bar');
  bar.dir = rtl ? 'rtl' : 'ltr';
  $('.hint').textContent = t('zapHint');
  $('.undo').textContent = t('zapUndo');
  $('.done').textContent = t('zapDone');
  document.documentElement.appendChild(host);

  // ---- Selectors -----------------------------------------------------------
  // Ids and classes that look generated (long digit runs) change on every load.
  const stableId = (id) => /^[A-Za-z][\w-]{0,60}$/.test(id) && !/\d{4,}/.test(id);
  const stableClass = (c) => /^[A-Za-z_-][\w-]{1,60}$/.test(c) && !/\d{3,}/.test(c);

  function selectorFor(el) {
    const parts = [];
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      if (node === document.body || node === document.documentElement) {
        parts.unshift(node.localName);
        break;
      }
      if (node.id && stableId(node.id) && document.querySelectorAll(`#${CSS.escape(node.id)}`).length === 1) {
        parts.unshift(`#${CSS.escape(node.id)}`);
        break;
      }
      let part = node.localName;
      part += [...node.classList].filter(stableClass).slice(0, 2).map((c) => `.${CSS.escape(c)}`).join('');
      const parent = node.parentElement;
      if (parent) {
        const same = [...parent.children].filter((c) => c.localName === node.localName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(node) + 1})`;
      }
      parts.unshift(part);
    }
    const sel = parts.join(' > ');
    try {
      return sel.length <= 480 && document.querySelector(sel) === el ? sel : null;
    } catch {
      return null;
    }
  }

  // ---- Picking -------------------------------------------------------------
  let target = null;
  const removed = [];

  const pick = (x, y) => {
    for (const el of document.elementsFromPoint(x, y)) {
      if (el === host || el === document.documentElement || el === document.body) continue;
      return el;
    }
    return null;
  };

  const show = (el) => {
    target = el;
    if (!el) {
      box.style.display = tag.style.display = 'none';
      return;
    }
    const r = el.getBoundingClientRect();
    Object.assign(box.style, {
      display: 'block', left: `${r.left - 2}px`, top: `${r.top - 2}px`,
      width: `${r.width}px`, height: `${r.height}px`,
    });
    const name = el.localName + (el.id ? `#${el.id}` : '') +
      [...el.classList].slice(0, 2).map((c) => `.${c}`).join('');
    tag.textContent = `${name}  ${Math.round(r.width)}×${Math.round(r.height)}`;
    Object.assign(tag.style, {
      display: 'block', left: `${Math.max(4, r.left)}px`,
      top: `${r.top > 30 ? r.top - 26 : r.bottom + 4}px`,
    });
  };

  const updateCount = () => {
    $('.count').textContent = removed.length ? t('zapCount', [String(removed.length)]) : '';
    $('.undo').disabled = !removed.length;
  };

  // Only the toolbar takes pointer events inside our closed shadow root, and
  // events from it reach page-level listeners retargeted to the host.
  const onBar = (e) => e.target === host;

  function remove(el) {
    const selector = selectorFor(el);
    const prev = el.getAttribute('style');
    el.style.setProperty('display', 'none', 'important');
    removed.push({ el, prev, selector });
    if (selector) chrome.runtime.sendMessage({ type: 'zapSave', selector }).catch(() => {});
    show(null);
    updateCount();
  }

  function undo() {
    const last = removed.pop();
    if (!last) return;
    if (last.prev == null) last.el.removeAttribute('style');
    else last.el.setAttribute('style', last.prev);
    if (last.selector) chrome.runtime.sendMessage({ type: 'zapRemove', selector: last.selector }).catch(() => {});
    updateCount();
  }

  // Swallow the page's own reaction to clicks while picking, so links don't open.
  const block = (e) => {
    if (onBar(e)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
  };
  const onMove = (e) => {
    if (onBar(e)) return show(null);
    show(pick(e.clientX, e.clientY));
  };
  const onClick = (e) => {
    if (onBar(e)) return;
    block(e);
    const el = pick(e.clientX, e.clientY);
    if (el) remove(el);
  };
  const onKey = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      stop();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      undo();
    }
  };
  const onScroll = () => target && show(target);

  const BLOCKED = ['mousedown', 'mouseup', 'pointerdown', 'pointerup', 'dblclick', 'auxclick', 'contextmenu'];
  function stop() {
    removeEventListener('mousemove', onMove, true);
    removeEventListener('click', onClick, true);
    removeEventListener('keydown', onKey, true);
    removeEventListener('scroll', onScroll, true);
    for (const type of BLOCKED) removeEventListener(type, block, true);
    host.remove();
    delete window.__hibZapper;
  }

  addEventListener('mousemove', onMove, true);
  addEventListener('click', onClick, true);
  addEventListener('keydown', onKey, true);
  addEventListener('scroll', onScroll, true);
  for (const type of BLOCKED) addEventListener(type, block, true);
  $('.undo').addEventListener('click', undo);
  $('.done').addEventListener('click', stop);
  window.__hibZapper = stop;
})();

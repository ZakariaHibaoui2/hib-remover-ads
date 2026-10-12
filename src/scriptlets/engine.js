// Runs in the page's own context on sites that need it, before the page's scripts.
// Applies the site's scriptlet calls from config.js: small, targeted patches that
// switch off anti-adblock checks, popunders and ad schedulers. Behaviour follows
// uBlock Origin's scriptlets of the same names.
(() => {
  const all = globalThis.HIB_SCRIPTLETS;
  try { delete globalThis.HIB_SCRIPTLETS; } catch {}
  if (!all || window.__hibScriptlets) return;
  Object.defineProperty(window, '__hibScriptlets', { value: true });

  // ---- Which calls apply to this page --------------------------------------

  const calls = [];
  const labels = location.hostname.toLowerCase().replace(/\.$/, '').split('.');
  for (let i = 0; i < labels.length - 1; i++) {
    const suffix = labels.slice(i).join('.');
    if (all[suffix]) calls.push(...all[suffix]);
    // Entity rules like "example.*" match any public suffix.
    const rest = labels.length - i - 1;
    if (rest <= 2 && all[`${labels[i]}.*`]) calls.push(...all[`${labels[i]}.*`]);
  }
  if (!calls.length) return;

  // ---- Helpers -------------------------------------------------------------

  const magic = String.fromCharCode(Date.now() % 26 + 97) + Math.floor(Math.random() * 982451653 + 982451653).toString(36);
  const noop = () => {};
  const fnString = (fn) => { try { return String(fn); } catch { return ''; } };

  // Matches uBO's pattern rules: "" matches everything, /re/flags is a regex,
  // anything else is a literal substring. A leading "!" negates.
  const matcher = (raw = '') => {
    let negate = false;
    if (raw.startsWith('!')) { negate = true; raw = raw.slice(1); }
    let re;
    const m = /^\/(.+)\/([gimsu]*)$/.exec(raw);
    try {
      re = m ? new RegExp(m[1], m[2].replace('g', '')) : new RegExp(raw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    } catch {
      re = /^\b$/; // invalid regex never matches
    }
    return (s) => re.test(String(s)) !== negate;
  };

  const VALUES = {
    undefined: () => undefined, false: () => false, true: () => true, null: () => null,
    noopFunc: () => function () {}, trueFunc: () => () => true, falseFunc: () => () => false,
    throwFunc: () => () => { throw new Error(magic); },
    emptyArr: () => [], '[]': () => [], emptyObj: () => ({}), '{}': () => ({}),
    '': () => '', emptyStr: () => '', "''": () => '', yes: () => true, no: () => false,
    NaN: () => NaN, Infinity: () => Infinity, '-1': () => -1, '0': () => 0, '1': () => 1,
    noopCallbackFunc: () => () => noop,
  };
  const parseValue = (raw) => {
    if (Object.hasOwn(VALUES, raw)) return { ok: true, value: VALUES[raw]() };
    if (/^-?\d+$/.test(raw) && Math.abs(Number(raw)) <= 0x7fff) return { ok: true, value: Number(raw) };
    if (/^'.*'$/.test(raw)) return { ok: true, value: raw.slice(1, -1) };
    return { ok: false };
  };

  // Follows a dotted property chain from window, trapping each link until it exists,
  // then calls `leaf(owner, prop)` on the final property.
  const trapChain = (owner, chain, leaf) => {
    const dot = chain.indexOf('.');
    if (dot === -1) return leaf(owner, chain);
    const prop = chain.slice(0, dot);
    const rest = chain.slice(dot + 1);
    const v = owner[prop];
    if (v instanceof Object || (typeof v === 'object' && v !== null)) return trapChain(v, rest, leaf);
    const desc = Object.getOwnPropertyDescriptor(owner, prop);
    if (desc && !desc.configurable) return;
    let current = v;
    try {
      Object.defineProperty(owner, prop, {
        configurable: true,
        get: () => current,
        set: (a) => {
          current = a;
          if (a instanceof Object) trapChain(a, rest, leaf);
        },
      });
    } catch {}
  };

  // ---- Scriptlets ----------------------------------------------------------

  const S = {};

  S.set = (chain, raw) => {
    if (!chain) return;
    const parsed = parseValue(raw ?? '');
    if (!parsed.ok) return;
    const value = parsed.value;
    trapChain(window, chain, (owner, prop) => {
      const desc = Object.getOwnPropertyDescriptor(owner, prop);
      if (desc && !desc.configurable) return;
      const original = desc ? ('value' in desc ? desc.value : undefined) : owner[prop];
      // Don't change a value's type, like uBO.
      if (original !== undefined && original !== null && value !== undefined && value !== null
          && typeof original !== typeof value) return;
      try {
        Object.defineProperty(owner, prop, { configurable: false, get: () => value, set: noop });
      } catch {}
    });
  };

  const abortOn = (kind) => (chain) => {
    if (!chain) return;
    trapChain(window, chain, (owner, prop) => {
      const desc = Object.getOwnPropertyDescriptor(owner, prop);
      if (desc && !desc.configurable) return;
      let value = owner[prop];
      try {
        Object.defineProperty(owner, prop, {
          configurable: true,
          get: () => { if (kind === 'read') throw new ReferenceError(magic); return value; },
          set: (a) => { if (kind === 'write') throw new ReferenceError(magic); value = a; },
        });
      } catch {}
    });
  };
  S.aopr = abortOn('read');
  S.aopw = abortOn('write');

  S.acs = (chain, needle = '', context = '') => {
    if (!chain) return;
    const test = matcher(needle);
    const inContext = matcher(context);
    const me = document.currentScript;
    const check = () => {
      const e = document.currentScript;
      if (!(e instanceof HTMLScriptElement) || e === me) return;
      const text = e.src ? e.src + '\n' + e.textContent : e.textContent;
      if (context && !inContext(e.src || text)) return;
      if (test(text)) throw new ReferenceError(magic);
    };
    trapChain(window, chain, (owner, prop) => {
      const desc = Object.getOwnPropertyDescriptor(owner, prop);
      if (desc && !desc.configurable) return;
      let value = owner[prop];
      const getter = desc?.get;
      const setter = desc?.set;
      try {
        Object.defineProperty(owner, prop, {
          configurable: true,
          get() { check(); return getter ? getter.call(this) : value; },
          set(a) { check(); if (setter) setter.call(this, a); else value = a; },
        });
      } catch {}
    });
  };

  // Deletes dotted paths from parsed JSON. "[]" walks every array item, "[-]"
  // removes the array item that holds the rest of the path, "*" any key.
  const prunePath = (obj, parts) => {
    if (!obj || typeof obj !== 'object') return false;
    const [head, ...rest] = parts;
    if (head === '[]' || head === '*' || head === '{}') {
      let hit = false;
      for (const k of Object.keys(obj)) hit = (rest.length ? prunePath(obj[k], rest) : (delete obj[k], true)) || hit;
      return hit;
    }
    if (head === '[-]' && Array.isArray(obj)) {
      let hit = false;
      for (let i = obj.length - 1; i >= 0; i--) {
        if (hasPath(obj[i], rest)) { obj.splice(i, 1); hit = true; }
      }
      return hit;
    }
    if (!Object.hasOwn(obj, head)) return false;
    if (!rest.length) { delete obj[head]; return true; }
    return prunePath(obj[head], rest);
  };
  const hasPath = (obj, parts) => {
    if (!parts.length) return true;
    if (!obj || typeof obj !== 'object') return false;
    const [head, ...rest] = parts;
    if (head === '[]' || head === '*') return Object.keys(obj).some((k) => hasPath(obj[k], rest));
    return Object.hasOwn(obj, head) && hasPath(obj[head], rest);
  };
  const splitPath = (p) => p.split('.').filter(Boolean);
  const pruners = [];
  S['json-prune'] = (prune = '', needles = '') => {
    const paths = prune.split(/\s+/).filter(Boolean).map(splitPath);
    const required = needles.split(/\s+/).filter(Boolean).map(splitPath);
    if (!paths.length) return;
    pruners.push((obj) => {
      if (required.length && !required.every((r) => hasPath(obj, r))) return;
      for (const p of paths) prunePath(obj, p);
    });
    if (pruners.length > 1) return;
    const run = (obj) => {
      if (obj && typeof obj === 'object') for (const fn of pruners) { try { fn(obj); } catch {} }
      return obj;
    };
    JSON.parse = new Proxy(JSON.parse, { apply: (t, self, args) => run(Reflect.apply(t, self, args)) });
    Response.prototype.json = new Proxy(Response.prototype.json, {
      apply: (t, self, args) => Reflect.apply(t, self, args).then(run),
    });
  };

  const timerDefuser = (name) => (needle = '', delay = '') => {
    const test = matcher(needle);
    let negDelay = false;
    if (delay.startsWith('!')) { negDelay = true; delay = delay.slice(1); }
    const wanted = delay === '' ? null : Number(delay);
    window[name] = new Proxy(window[name], {
      apply: (t, self, args) => {
        const [fn, ms] = args;
        const delayHit = wanted === null || ((Number(ms) || 0) === wanted) !== negDelay;
        if (delayHit && test(fnString(fn))) args[0] = noop;
        return Reflect.apply(t, self, args);
      },
    });
  };
  S.nostif = timerDefuser('setTimeout');
  S.nosiif = timerDefuser('setInterval');

  const booster = (name) => (needle = '', delay = '1000', boost = '0.05') => {
    const test = matcher(needle);
    const wanted = delay === '*' ? null : Number(delay) || 1000;
    let factor = Number(boost);
    if (!(factor >= 0.001 && factor <= 50)) factor = 0.05;
    window[name] = new Proxy(window[name], {
      apply: (t, self, args) => {
        if ((wanted === null || Number(args[1]) === wanted) && test(fnString(args[0]))) {
          args[1] = (Number(args[1]) || 0) * factor;
        }
        return Reflect.apply(t, self, args);
      },
    });
  };
  S['nano-stb'] = booster('setTimeout');
  S['nano-sib'] = booster('setInterval');

  S.aeld = (type = '', needle = '') => {
    const testType = matcher(type);
    const test = matcher(needle);
    EventTarget.prototype.addEventListener = new Proxy(EventTarget.prototype.addEventListener, {
      apply: (t, self, args) => {
        const [evType, handler] = args;
        const h = typeof handler === 'function' ? handler : handler?.handleEvent;
        if (testType(evType) && test(fnString(h))) return undefined;
        return Reflect.apply(t, self, args);
      },
    });
  };

  S.nowoif = (needle = '') => {
    const test = matcher(needle);
    const fake = () => new Proxy({ closed: false, opener: window, location: { href: '' } }, {
      get: (target, prop) => (prop in target ? target[prop] : noop),
      set: () => true,
    });
    window.open = new Proxy(window.open, {
      apply: (t, self, args) => (test(args[0] ?? '') ? fake() : Reflect.apply(t, self, args)),
    });
  };

  const onDom = (fn) => {
    const run = () => { try { fn(); } catch {} };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run, { once: true });
    else run();
    let pending = false;
    new MutationObserver(() => {
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; run(); });
    }).observe(document, { childList: true, subtree: true, attributes: true });
  };

  S.ra = (attrs = '', selector = '') => {
    const names = attrs.split(/\s*\|\s*/).filter(Boolean);
    if (!names.length) return;
    const sel = selector || names.map((a) => `[${CSS.escape(a)}]`).join(',');
    onDom(() => {
      for (const el of document.querySelectorAll(sel)) for (const a of names) el.removeAttribute(a);
    });
  };

  S.rc = (classes = '', selector = '') => {
    const names = classes.split(/\s*\|\s*/).filter(Boolean);
    if (!names.length) return;
    const sel = selector || names.map((c) => `.${CSS.escape(c)}`).join(',');
    onDom(() => {
      for (const el of document.querySelectorAll(sel)) el.classList.remove(...names);
    });
  };

  // "prop:value" pairs or a bare needle, tested against the request URL.
  const requestTest = (spec) => {
    if (!spec || spec === '*') return () => true;
    const pairs = spec.split(/\s+/).map((p) => {
      const i = p.indexOf(':');
      return i > 0 && /^[a-z]+$/.test(p.slice(0, i)) ? [p.slice(0, i), matcher(p.slice(i + 1))] : ['url', matcher(p)];
    });
    return (info) => pairs.every(([k, test]) => test(info[k] ?? ''));
  };

  S['no-fetch-if'] = (spec = '') => {
    const test = requestTest(spec);
    window.fetch = new Proxy(window.fetch, {
      apply: (t, self, args) => {
        const [res, init] = args;
        const url = res instanceof Request ? res.url : String(res);
        const method = (init?.method || (res instanceof Request ? res.method : 'GET'));
        if (test({ url, method })) return Promise.resolve(new Response('', { status: 200, statusText: 'OK' }));
        return Reflect.apply(t, self, args);
      },
    });
  };

  S['no-xhr-if'] = (spec = '') => {
    const test = requestTest(spec);
    const blocked = new WeakSet();
    const XHR = XMLHttpRequest.prototype;
    XHR.open = new Proxy(XHR.open, {
      apply: (t, self, args) => {
        if (test({ method: args[0], url: String(args[1]) })) blocked.add(self);
        return Reflect.apply(t, self, args);
      },
    });
    XHR.send = new Proxy(XHR.send, {
      apply: (t, self, args) => {
        if (!blocked.has(self)) return Reflect.apply(t, self, args);
        for (const [k, v] of [['readyState', 4], ['status', 200], ['statusText', 'OK'], ['response', ''], ['responseText', '']]) {
          Object.defineProperty(self, k, { value: v, configurable: true });
        }
        setTimeout(() => {
          for (const type of ['readystatechange', 'load', 'loadend']) self.dispatchEvent(new Event(type));
        }, 1);
        return undefined;
      },
    });
  };

  S['noeval-if'] = (needle = '') => {
    const test = matcher(needle);
    window.eval = new Proxy(window.eval, {
      apply: (t, self, args) => (test(String(args[0])) ? undefined : Reflect.apply(t, self, args)),
    });
  };

  S['window.name-defuser'] = () => {
    if (window === window.top) window.name = '';
  };

  S['disable-newtab-links'] = () => {
    document.addEventListener('click', (e) => {
      const a = e.target instanceof Element && e.target.closest('a[target="_blank"]');
      if (a) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, true);
  };

  // Hide the abort errors we throw on purpose so they don't reach the page's error handlers.
  window.addEventListener('error', (e) => {
    if (typeof e.message === 'string' && e.message.includes(magic)) e.preventDefault();
  }, true);

  for (const [name, ...args] of calls) {
    try { S[name]?.(...args); } catch {}
  }
})();

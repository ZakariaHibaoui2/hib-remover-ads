// Stand-in for Google Publisher Tag (gpt.js). Pages that queue work on
// `googletag` keep running, but no ad is ever requested or shown.
(() => {
  const noop = () => {};
  // Any method call returns the same object, so chained calls like
  // googletag.defineSlot(...).addService(...).setTargeting(...) all work.
  const chain = new Proxy(noop, {
    get: (_, prop) => {
      if (prop === 'then') return undefined; // never look like a promise
      if (prop === Symbol.toPrimitive) return () => '';
      return chain;
    },
    apply: () => chain,
  });

  const pubads = new Proxy({}, {
    get: (_, prop) => {
      if (prop === 'getSlots') return () => [];
      if (prop === 'getTargeting' || prop === 'getTargetingKeys') return () => [];
      if (prop === 'isInitialLoadDisabled') return () => false;
      return chain;
    },
  });

  const run = (fn) => {
    try {
      if (typeof fn === 'function') fn();
    } catch (err) {
      console.debug('[hush] googletag.cmd', err);
    }
  };
  const cmd = { push: (...fns) => { fns.forEach(run); return fns.length; } };

  const existing = window.googletag;
  const pending = Array.isArray(existing?.cmd) ? existing.cmd : [];

  window.googletag = {
    apiReady: true,
    pubadsReady: true,
    cmd,
    pubads: () => pubads,
    companionAds: () => chain,
    content: () => chain,
    defineSlot: () => chain,
    defineOutOfPageSlot: () => chain,
    destroySlots: () => true,
    display: noop,
    enableServices: noop,
    getVersion: () => '',
    sizeMapping: () => chain,
    setAdIframeTitle: noop,
    openConsole: noop,
  };
  pending.forEach(run);
})();

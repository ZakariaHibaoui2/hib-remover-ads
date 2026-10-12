// Runs in YouTube's own page context before its scripts load, and removes ad
// instructions from player data so most ads are never scheduled at all.
(() => {
  if (window.__hushPrune) return;
  window.__hushPrune = true;

  const AD_KEYS = ['adPlacements', 'adSlots', 'playerAds', 'adBreakHeartbeatParams'];

  const strip = (obj) => {
    for (const key of AD_KEYS) {
      if (key in obj) delete obj[key];
    }
  };

  const prune = (data) => {
    if (!data || typeof data !== 'object') return data;
    try {
      strip(data);
      if (data.playerResponse && typeof data.playerResponse === 'object') strip(data.playerResponse);
      if (Array.isArray(data)) {
        for (const item of data) {
          if (item && typeof item === 'object') {
            strip(item);
            if (item.playerResponse) strip(item.playerResponse);
          }
        }
      }
    } catch {
      // Frozen or exotic objects: leave them alone.
    }
    return data;
  };

  // JSON.parse covers XHR and text-based fetch handling.
  JSON.parse = new Proxy(JSON.parse, {
    apply: (target, self, args) => prune(Reflect.apply(target, self, args)),
  });

  // Response.json covers fetch-based player requests.
  Response.prototype.json = new Proxy(Response.prototype.json, {
    apply: (target, self, args) => Reflect.apply(target, self, args).then(prune),
  });

  // The first video's data is embedded in the page as a global assignment.
  for (const name of ['ytInitialPlayerResponse', 'playerResponse']) {
    let value;
    try {
      Object.defineProperty(window, name, {
        configurable: true,
        get: () => value,
        set: (v) => { value = prune(v); },
      });
    } catch {
      // Already defined by the page; the JSON hooks still apply.
    }
  }
})();

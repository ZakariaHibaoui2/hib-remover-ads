// Fallback for YouTube ads that still reach the player: mutes them, jumps to the
// end, presses Skip, then restores the viewer's sound and speed.
(() => {
  if (window.__hushYouTube) return;
  window.__hushYouTube = true;

  const SKIP_BUTTONS = [
    '.ytp-skip-ad-button',
    '.ytp-ad-skip-button',
    '.ytp-ad-skip-button-modern',
    '.videoAdUiSkipButton',
    'button[id^="skip-button"]',
  ].join(',');

  // Visible ad UI. Required alongside the player's ad class so a stale class
  // can never make us seek the real video to its end.
  const AD_UI = [
    '.ytp-ad-player-overlay',
    '.ytp-ad-player-overlay-layout',
    '.ytp-ad-preview-container',
    '.ytp-ad-skip-button-container',
    '.ytp-ad-persistent-progress-bar-container',
    '.ytp-ad-text',
    '.ytp-ad-badge',
    '.ytp-skip-ad',
  ].join(',');

  let inAd = false;
  let saved = null;
  // The viewer's own speed, tracked outside ads. YouTube forces 1x during an ad,
  // so reading the rate when the ad starts would lose a chosen 1.5x or 2x.
  let contentRate = 1;

  const report = () => {
    // Throws, rather than rejects, once the extension has been updated under this tab.
    try {
      if (chrome.runtime?.id) chrome.runtime.sendMessage({ type: 'hidden', count: 1 }).catch(() => {});
    } catch {
      // Extension context gone; the page keeps working without the counter.
    }
  };

  const handleAd = (player, video) => {
    if (!inAd) {
      inAd = true;
      saved = { video, muted: video.muted };
      report();
    }
    video.muted = true;
    try {
      video.playbackRate = 16;
    } catch {
      // Some ad formats cap the rate; seeking below still ends them.
    }
    if (Number.isFinite(video.duration) && video.duration > 0 && video.currentTime < video.duration - 0.3) {
      video.currentTime = video.duration - 0.1;
    }
    for (const button of player.querySelectorAll(SKIP_BUTTONS)) button.click();
    if (video.paused) video.play().catch(() => {});
  };

  const endAd = () => {
    inAd = false;
    // Restore the element we changed, even if the viewer navigated mid-ad.
    const video = saved?.video;
    if (video) {
      video.muted = saved.muted;
      if (video.playbackRate === 16) video.playbackRate = contentRate;
    }
    saved = null;
  };

  const isVisible = (el) => el.offsetWidth > 0 || el.offsetHeight > 0;

  // Prefer the main watch player; Shorts and previews add more players later in the page.
  const findPlayer = () =>
    document.querySelector('#movie_player') || document.querySelector('.html5-video-player');

  // YouTube pauses playback behind its "ad blockers aren't allowed" dialog.
  const dismissEnforcement = (video) => {
    const notice = document.querySelector('ytd-enforcement-message-view-model');
    if (!notice) return;
    notice.closest('tp-yt-paper-dialog')?.remove();
    notice.remove();
    document.querySelector('tp-yt-iron-overlay-backdrop')?.remove();
    document.body.style.removeProperty('overflow');
    if (video?.paused) video.play().catch(() => {});
  };

  const tick = () => {
    const player = findPlayer();
    if (!player) return;
    const video = player.querySelector('video.html5-main-video') || player.querySelector('video');
    const showingAd =
      (player.classList.contains('ad-showing') || player.classList.contains('ad-interrupting')) &&
      [...player.querySelectorAll(AD_UI)].some(isVisible);

    if (showingAd && video) handleAd(player, video);
    else {
      if (inAd) endAd();
      if (video && video.playbackRate !== 16) contentRate = video.playbackRate;
    }

    dismissEnforcement(video);
  };

  let observed = null;
  const watchPlayer = () => {
    const player = findPlayer();
    if (player && player !== observed) {
      observed = player;
      new MutationObserver(tick).observe(player, { attributes: true, attributeFilter: ['class'] });
    }
  };

  // The observer reacts instantly to ads starting; the interval catches the
  // player being swapped out during in-app navigation.
  setInterval(() => {
    watchPlayer();
    tick();
  }, 400);
})();

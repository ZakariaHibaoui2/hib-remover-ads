// Ad tabs are redirected here. A tab another page opened (a popunder) closes
// itself; one the user navigated to on purpose stays open and explains.
if (window.opener || document.referrer) window.close();
// Pages can hide the opener and referrer, but the browser still knows which tab
// opened this one; the background closes a brand-new tab that has an opener.
if (history.length <= 1) chrome.runtime.sendMessage({ type: 'adTab' }).catch(() => {});
document.addEventListener('DOMContentLoaded', () => {
  const t = (key) => chrome.i18n.getMessage(key) || key;
  document.documentElement.lang = chrome.i18n.getUILanguage();
  document.documentElement.dir = t('@@bidi_dir');
  for (const el of document.querySelectorAll('[data-i18n]')) el.textContent = t(el.dataset.i18n);
  document.title = t('blockedTitle');
  const back = document.getElementById('back');
  if (history.length <= 1) back.textContent = t('closeTab');
  back.addEventListener('click', () => (history.length > 1 ? history.back() : window.close()));
});

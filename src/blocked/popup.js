// Ad tabs are redirected here. A tab another page opened (a popunder) closes
// itself; one the user navigated to on purpose stays open and explains.
if (window.opener || document.referrer) window.close();
// Pages can hide the opener and referrer, but the browser still knows which tab
// opened this one; the background closes a brand-new tab that has an opener.
if (history.length <= 1) chrome.runtime.sendMessage({ type: 'adTab' }).catch(() => {});
document.addEventListener('DOMContentLoaded', () => {
  const back = document.getElementById('back');
  if (history.length <= 1) back.textContent = 'Close this tab';
  back.addEventListener('click', () => (history.length > 1 ? history.back() : window.close()));
});

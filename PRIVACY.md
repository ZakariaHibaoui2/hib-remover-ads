# Privacy

**Hib Remover Ads collects nothing.** It has no account, no analytics, no crash reporting and no server. It never sends your browsing data anywhere.

## What stays on your device

Stored with Chrome's extension storage, on your computer only:

- whether blocking is on or off;
- the sites you paused;
- how many ads were blocked, per open tab, per day for the last 35 days, and in total (only numbers, never which sites);
- for each site where you used "Remove something on this page", the CSS selectors of the elements you removed.

Uninstalling the extension deletes all of it.

## Network

The extension makes no network requests of its own. Filter lists are compiled into the extension when it is built, not downloaded while you browse. The only time it opens a web page is when you click **Report a site** in the popup, which opens a GitHub issue form in a new tab. The form is prefilled with the page's address (without anything after a `?`), the extension's version and your browser's name, and nothing is sent unless you submit it yourself.

## Permissions

| Permission | Why |
|---|---|
| `declarativeNetRequest` | Lets Chrome block ad and tracker requests using the bundled rules. Chrome does the matching; requests never pass through extension code. |
| `declarativeNetRequestFeedback` | Reads how many requests Chrome blocked, for the counter in the popup. |
| `scripting` | Injects the hiding stylesheet and the YouTube and anti-adblock fixes, skips them on sites you paused, and starts the click-to-remove picker when you ask for it. |
| `storage` | Remembers your settings and the counters listed above. |
| `alarms` | Updates the blocked counter every two minutes. |
| `favicon` | Shows the current site's icon in the popup, from Chrome's own cache. |
| Access to all sites | Ads appear on every site, so blocking has to work on every site. |

## Installer

The Windows installer only unpacks the extension to `%LOCALAPPDATA%\Hib Remover Ads\extension`, copies that path to your clipboard and opens your browser's extensions page. It needs no administrator rights, changes no system settings and makes no network requests. Its source is [`installer/Setup.cs`](installer/Setup.cs).

Questions: open an [issue](https://github.com/ZakariaHibaoui2/hib-remover-ads/issues).

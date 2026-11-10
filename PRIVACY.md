# Privacy

**Hib Remover Ads collects nothing.** It has no account, no analytics, no crash reporting and no server of its own. It never sends your browsing data to us or to anyone who uses it for ads.

This page covers the browser extension first, then the [Windows app](#windows-app).

# Browser extension

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

# Windows app

The Windows app (optional, a tick box in the installer) blocks ads in every program by answering your PC's server lookups (DNS). Its source is in [`windows/`](windows).

## What it sends

- **Lookups for servers that aren't blocked** go to Cloudflare's public DNS service (1.1.1.1) over HTTPS, so your internet provider and the network you are on can't read them. If Cloudflare can't be reached it tries Quad9 (9.9.9.9), then the DNS server your network handed out, which is the one your PC used before. Every DNS service sees the names it is asked for; that is how DNS works, with or without this app. Lookups carry no account, no ID and no cookie.
- **Lookups for blocked ad servers** go nowhere. They are answered on your PC.
- **Names of your local network** (printers, your router, company servers) are only ever asked from your network's own DNS server.
- **Once a week** it downloads the newest block list, a plain list of names, from this GitHub repository. GitHub sees your IP address, as for any download.

It sends nothing else: no statistics, no crash reports, no check-ins.

## What it keeps on your PC

In `C:\ProgramData\Hib Remover Ads`:

- how many lookups it blocked today and in total (numbers only);
- the names of the ad servers it blocked most since the PC started, for the list in its window. They are kept in memory and one small file, and are gone at restart;
- your on/off switch and the servers you chose to allow;
- your DNS settings from before, so it can put them back;
- a short log of starts, stops and errors. It never contains a name you looked up.

It keeps no history of the sites or servers you visit.

## What it changes on your PC

- The DNS setting of your network adapters, to point at itself (127.0.0.1), with 1.1.1.1 and your network's own server as spares.
- A Windows service, a tray icon that starts with Windows, and a Start menu shortcut.
- If you leave those boxes ticked: six per-user Windows settings that switch off ads in Windows itself. They are the same settings the Settings app changes.
- While Spotify plays an audio ad: Spotify's volume in the Windows mixer. Spotify's files are never touched.

Uninstalling from **Settings > Apps** puts the DNS setting back exactly as it was and removes all of the above.

## Installer

The Windows installer unpacks the extension to `%LOCALAPPDATA%\Hib Remover Ads\extension`, copies that path to your clipboard and opens your browser's extensions page. That part needs no administrator rights and makes no network requests. If "Also block ads in Windows apps" is ticked, it also runs the Windows app's own install, which asks for administrator permission. Its source is [`installer/Setup.cs`](installer/Setup.cs).

Questions: open an [issue](https://github.com/ZakariaHibaoui2/hib-remover-ads/issues).

# Security policy

## Supported versions

Only the [latest release](https://github.com/ZakariaHibaoui2/hib-remover-ads/releases/latest) gets fixes.

## Reporting a vulnerability

Please don't open a public issue for security problems. Report them privately through GitHub: **Security → Report a vulnerability** on this repository ([direct link](https://github.com/ZakariaHibaoui2/hib-remover-ads/security/advisories/new)).

Include the version, the browser, what an attacker can do and the steps to reproduce. You'll get a reply within 7 days.

## Verifying a download

Each release lists SHA-256 checksums for the installer and the zip. On Windows, check a file with:

```powershell
Get-FileHash .\HibRemoverAds-Setup.exe -Algorithm SHA256
```

The installer and the zip are built from the tagged source with `python installer/build.py`.

"""Builds the block list for the Windows app (windows/lists/block.txt and allow.txt).

The Windows app blocks ad servers by name for every program on the PC, so it
needs plain domain lists rather than browser rules. Sources:

  AdGuard DNS filter   GPL-3.0   https://github.com/AdguardTeam/AdGuardSDNSFilter
  HaGeZi Pro           GPL-3.0   https://github.com/hagezi/dns-blocklists
  windows/lists/apps.txt and allow-extra.txt, kept by hand

Run: python tools/hostlist.py
"""
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LISTS = ROOT / "windows" / "lists"
SOURCES = {
    "adguard-dns": "https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt",
    "hagezi-pro": "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/pro-onlydomains.txt",
}
DOMAIN = re.compile(r"^(?:[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?\.)+[a-z][a-z0-9-]{1,62}$")
RULE = re.compile(r"^(@@)?\|\|([^\^$/*|]+)\^(\$important)?$")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "hib-remover-ads-build"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


def parse(text):
    block, allow = set(), set()
    for line in text.splitlines():
        line = line.strip().lower()
        if not line or line[0] in "#!":
            continue
        m = RULE.match(line)
        if m:
            (allow if m.group(1) else block).add(m.group(2))
        elif DOMAIN.match(line):
            block.add(line)
    return block, allow


def covered(domain, rules):
    """True if a parent of this domain is already in the set."""
    i = domain.find(".")
    while i != -1:
        if domain[i + 1:] in rules:
            return True
        i = domain.find(".", i + 1)
    return False


def main():
    block, allow = parse((LISTS / "apps.txt").read_text(encoding="utf-8"))
    allow |= parse((LISTS / "allow-extra.txt").read_text(encoding="utf-8"))[0]
    for name, url in SOURCES.items():
        b, a = parse(fetch(url))
        print(f"{name}: {len(b)} blocked, {len(a)} allowed")
        block |= b
        allow |= a
    block = {d for d in block if DOMAIN.match(d)} - allow
    allow = {d for d in allow if DOMAIN.match(d)}
    block = {d for d in block if not covered(d, block)}
    # An allow entry only matters if it sits under something blocked.
    allow = {d for d in allow if covered(d, block)} | parse((LISTS / "allow-extra.txt").read_text(encoding="utf-8"))[0]
    assert len(block) > 50000, f"only {len(block)} domains, a source is probably down"
    (LISTS / "block.txt").write_text("\n".join(sorted(block)) + "\n", encoding="ascii", newline="\n")
    (LISTS / "allow.txt").write_text("\n".join(sorted(allow)) + "\n", encoding="ascii", newline="\n")
    print(f"block.txt: {len(block)} domains, allow.txt: {len(allow)} domains")


if __name__ == "__main__":
    main()

"""Downloads the community filter lists and compiles them for the extension.

  python tools/filterlists.py            # use cached lists in tools/lists/
  python tools/filterlists.py --fetch    # download fresh copies first

Outputs
  src/rules/block.json        network block rules (declarativeNetRequest)
  src/rules/allow.json        network exceptions, kept apart so they aren't counted as blocks
  src/content/generic.css     element hiding that applies on every site
  src/rules/cosmetic.json     per-site hiding, per-site exceptions, sites that opt out of generic hiding
  src/scriptlets/config.js    per-site scriptlet calls (anti-adblock defusing, YouTube, popups)
  src/scriptlets/hosts.json   which sites need the scriptlet engine

Filter syntax follows Adblock Plus and uBlock Origin. Anything we can't express
faithfully (regex rules, procedural selectors, redirects, unknown options) is
skipped rather than approximated, because a wrong approximation breaks sites.
"""
import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / "lists"
SRC = ROOT / "src"

LISTS = {
    "easylist": "https://easylist.to/easylist/easylist.txt",
    "easyprivacy": "https://easylist.to/easylist/easyprivacy.txt",
    "ubo-filters": "https://ublockorigin.github.io/uAssets/filters/filters.txt",
    "ubo-quick-fixes": "https://ublockorigin.github.io/uAssets/filters/quick-fixes.txt",
    "ubo-privacy": "https://ublockorigin.github.io/uAssets/filters/privacy.txt",
    "ubo-unbreak": "https://ublockorigin.github.io/uAssets/filters/unbreak.txt",
    "liste-fr": "https://easylist-downloads.adblockplus.org/liste_fr.txt",
    "liste-ar": "https://easylist-downloads.adblockplus.org/Liste_AR.txt",
}

# Chrome guarantees 30,000 enabled static rules per extension.
MAX_BLOCK_RULES = 27000

TYPES = {
    "script": "script", "image": "image", "stylesheet": "stylesheet", "css": "stylesheet",
    "object": "object", "xmlhttprequest": "xmlhttprequest", "xhr": "xmlhttprequest",
    "subdocument": "sub_frame", "frame": "sub_frame", "ping": "ping", "beacon": "ping",
    "media": "media", "font": "font", "websocket": "websocket", "other": "other",
}
ALL_SUB = sorted(set(TYPES.values()))
HOST_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
PLAIN_DOMAIN = re.compile(r"^\|\|([a-z0-9.-]+\.[a-z0-9-]+)\^?\|?$")
COSMETIC = re.compile(r"^([^#/|\"]*?)(#@?#|#@?\?#|#@?\$#|#@?%#)(.*)$")
PROCEDURAL = re.compile(
    r":(?:has-text|-abp-[a-z-]+|matches-css(?:-before|-after)?|xpath|upward|remove|style|"
    r"watch-attr|min-text-length|matches-path|matches-attr|matches-prop|remove-attr|"
    r"remove-class|others|shadow|if|if-not|nth-ancestor|contains|matches-media|spath)\("
    r"|:remove\(\)|:others\(\)"
)
SCRIPTLETS = {
    # uBO name or alias -> canonical name implemented in src/scriptlets/engine.js
    "set-constant": "set", "set": "set",
    "abort-on-property-read": "aopr", "aopr": "aopr",
    "abort-on-property-write": "aopw", "aopw": "aopw",
    "abort-current-script": "acs", "acs": "acs", "abort-current-inline-script": "acs", "acis": "acs",
    "json-prune": "json-prune",
    "no-setTimeout-if": "nostif", "nostif": "nostif", "prevent-setTimeout": "nostif",
    "no-setInterval-if": "nosiif", "nosiif": "nosiif", "prevent-setInterval": "nosiif",
    "addEventListener-defuser": "aeld", "aeld": "aeld", "prevent-addEventListener": "aeld",
    "no-window-open-if": "nowoif", "nowoif": "nowoif", "prevent-window-open": "nowoif",
    "remove-attr": "ra", "ra": "ra",
    "remove-class": "rc", "rc": "rc",
    "adjust-setTimeout": "nano-stb", "nano-setTimeout-booster": "nano-stb", "nano-stb": "nano-stb",
    "adjust-setInterval": "nano-sib", "nano-setInterval-booster": "nano-sib", "nano-sib": "nano-sib",
    "prevent-fetch": "no-fetch-if", "no-fetch-if": "no-fetch-if",
    "prevent-xhr": "no-xhr-if", "no-xhr-if": "no-xhr-if",
    "noeval-if": "noeval-if", "prevent-eval-if": "noeval-if",
    "window.name-defuser": "window.name-defuser",
    "disable-newtab-links": "disable-newtab-links",
}


def fetch():
    CACHE.mkdir(parents=True, exist_ok=True)
    for name, url in LISTS.items():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 hib-remover-ads"})
        data = urllib.request.urlopen(req, timeout=60).read()
        (CACHE / f"{name}.txt").write_bytes(data)
        print(f"  fetched {name}: {len(data) // 1024} KB")


def read_lines():
    for name in LISTS:
        path = CACHE / f"{name}.txt"
        if not path.exists():
            sys.exit(f"missing {path}; run with --fetch")
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line and not line.startswith(("!", "[")):
                yield line


def split_domains(text, sep):
    inc, exc = [], []
    for d in filter(None, (x.strip().lower() for x in text.split(sep))):
        (exc if d.startswith("~") else inc).append(d.lstrip("~"))
    ok = lambda d: HOST_RE.match(d) or re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.\*$", d)
    return [d for d in inc if ok(d)], [d for d in exc if ok(d)], len(inc)


# ---- Network ---------------------------------------------------------------

class Net:
    def __init__(self):
        self.block, self.allow = [], []
        self.block_domains = defaultdict(set)  # option-key -> domains
        self.allow_domains = defaultdict(set)
        self.no_generic, self.no_cosmetic = set(), set()
        self.skipped = 0

    def add(self, line, bad):
        if line in bad:
            return
        exception = line.startswith("@@")
        body = line[2:] if exception else line
        pattern, opts = body, ""
        i = body.rfind("$")
        if i != -1 and re.match(r"^[\w~,=|.\-*:/]+$", body[i + 1:] or "#"):
            pattern, opts = body[:i], body[i + 1:]
        if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
            self.skipped += 1  # regex rules: Chrome allows only 1000, skip them
            return

        types, not_types = set(), set()
        cond = {}
        priority = 2 if exception else 1
        document = hide_kind = None
        for opt in filter(None, opts.split(",")):
            neg = opt.startswith("~")
            key, _, val = opt.lstrip("~").partition("=")
            if key in TYPES:
                (not_types if neg else types).add(TYPES[key])
            elif key in ("third-party", "3p"):
                cond["domainType"] = "firstParty" if neg else "thirdParty"
            elif key in ("first-party", "1p"):
                cond["domainType"] = "thirdParty" if neg else "firstParty"
            elif key in ("strict3p", "strict1p"):
                cond["domainType"] = "thirdParty" if key == "strict3p" else "firstParty"
            elif key in ("domain", "from"):
                inc, exc, given = split_domains(val, "|")
                inc = [d for d in inc if "*" not in d]
                exc = [d for d in exc if "*" not in d]
                if given and not inc and not exc:
                    return
                if inc:
                    cond["initiatorDomains"] = inc
                elif given and "~" not in val and not inc:
                    return
                if exc:
                    cond["excludedInitiatorDomains"] = exc
            elif key == "match-case":
                cond["isUrlFilterCaseSensitive"] = True
            elif key == "important":
                priority = 3
            elif key in ("document", "doc") and not neg:
                document = True
            elif key in ("generichide", "ghide", "elemhide", "ehide") and exception:
                hide_kind = key
            elif key == "all":
                types.update(ALL_SUB)
            elif key in ("badfilter",):
                return
            else:
                self.skipped += 1  # popup, csp, redirect, removeparam, ...: not expressible
                return

        if hide_kind:
            m = re.match(r"^\|\|([a-z0-9.-]+)\^?$", pattern)
            if m:
                (self.no_cosmetic if hide_kind in ("elemhide", "ehide") else self.no_generic).add(m.group(1))
            return
        if types and not_types:
            types -= not_types
            not_types = set()
        if not_types:
            cond["excludedResourceTypes"] = sorted(not_types)
        if document and not exception:
            self.skipped += 1  # strict page blocking: not something we want
            return

        if pattern in ("", "*", "|", "||"):
            if not cond.get("initiatorDomains"):
                self.skipped += 1
                return
            pattern = ""
        if not pattern.isascii():
            self.skipped += 1
            return

        if document:
            action = {"type": "allowAllRequests"}
            cond["resourceTypes"] = ["main_frame", "sub_frame"]
        else:
            action = {"type": "allow" if exception else "block"}
            if types:
                cond["resourceTypes"] = sorted(types)

        m = PLAIN_DOMAIN.match(pattern.lower())
        if m and not cond.get("isUrlFilterCaseSensitive"):
            key = json.dumps([action, priority, cond], sort_keys=True)
            (self.allow_domains if exception else self.block_domains)[key].add(m.group(1))
            return
        if pattern:
            cond["urlFilter"] = pattern
        (self.allow if exception else self.block).append({"priority": priority, "action": action, "condition": cond})

    def rules(self, exception):
        out = []
        for key, domains in (self.allow_domains if exception else self.block_domains).items():
            action, priority, cond = json.loads(key)
            for chunk in chunks(sorted(domains), 2000):
                out.append({"priority": priority, "action": action,
                            "condition": {"requestDomains": chunk, **cond}})
        seen, singles = set(), []
        for r in (self.allow if exception else self.block):
            k = json.dumps(r, sort_keys=True)
            if k not in seen:
                seen.add(k)
                singles.append(r)
        return out + singles


def chunks(seq, n):
    return [seq[i:i + n] for i in range(0, len(seq), n)]


# ---- Cosmetic and scriptlets ------------------------------------------------

def parse_args(text):
    """Splits uBO scriptlet arguments on commas, honouring quotes and \\, escapes."""
    args, cur, quote, i = [], "", None, 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text) and text[i + 1] == ",":
            cur += ","
            i += 2
            continue
        if quote:
            if c == quote:
                quote = None
            else:
                cur += c
        elif c in "'\"" and not cur.strip():
            quote, cur = c, ""
        elif c == ",":
            args.append(cur.strip())
            cur = ""
        else:
            cur += c
        i += 1
    args.append(cur.strip())
    return args


class Cosmetic:
    def __init__(self):
        self.generic = set()
        self.generic_off = set()
        self.specific = defaultdict(set)
        self.exceptions = defaultdict(set)
        self.scriptlets = defaultdict(list)
        self.scriptlet_off = defaultdict(set)
        self.skipped = 0

    def add(self, domains, sep, body):
        exception = "@" in sep
        if sep not in ("##", "#@#"):
            self.skipped += 1
            return
        inc, exc, given = split_domains(domains, ",")
        if given and not inc and not exc:
            return
        if body.startswith("+js("):
            if not body.endswith(")"):
                return
            args = parse_args(body[4:-1])
            name = args[0].removesuffix(".js")
            if exception:
                for d in inc:
                    self.scriptlet_off[d].add(name)
                return
            canonical = SCRIPTLETS.get(name)
            if not canonical or not inc:
                self.skipped += 1
                return
            for d in inc:
                self.scriptlets[d].append([canonical, *args[1:]])
            return
        if body.startswith("^") or PROCEDURAL.search(body) or len(body) > 1000:
            self.skipped += 1
            return
        sel = body
        if exception:
            if not inc:
                self.generic_off.add(sel)
            for d in inc:
                self.exceptions[d].add(sel)
            return
        if inc:
            for d in inc:
                self.specific[d].add(sel)
            for d in exc:
                self.exceptions[d].add(sel)
        else:
            self.generic.add(sel)
            for d in exc:
                self.exceptions[d].add(sel)


def validate(selectors):
    """Keeps only selectors Chromium can parse."""
    from playwright.sync_api import sync_playwright
    sels = sorted(selectors)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        ok = page.evaluate(
            "(l) => l.map((s) => { try { document.createDocumentFragment().querySelector(s); return true; }"
            " catch { return false; } })", sels)
        b.close()
    return {s for s, good in zip(sels, ok) if good}


def main():
    if "--fetch" in sys.argv:
        fetch()

    lines = list(dict.fromkeys(read_lines()))
    bad = {l[: l.rfind("$")] + l[l.rfind("$"):].replace(",badfilter", "").replace("$badfilter", "")
           for l in lines if "badfilter" in l}
    net, cos = Net(), Cosmetic()
    for line in lines:
        m = COSMETIC.match(line)
        if m:
            cos.add(*m.groups())
        else:
            net.add(line, bad)

    block, allow = net.rules(False), net.rules(True)
    block.sort(key=lambda r: ("requestDomains" not in r["condition"], -r["priority"]))
    if len(block) > MAX_BLOCK_RULES:
        print(f"  trimming block rules {len(block)} -> {MAX_BLOCK_RULES}")
        block = block[:MAX_BLOCK_RULES]
    curated = len(json.loads((SRC / "rules" / "ads.json").read_text(encoding="utf-8")))
    room = 29800 - curated - len(block)
    if len(allow) > room:
        print(f"  trimming allow rules {len(allow)} -> {room}")
        allow.sort(key=lambda r: ("requestDomains" not in r["condition"], -r["priority"]))
        allow = allow[:room]
    for rules in (block, allow):
        for i, r in enumerate(rules, 1):
            r["id"] = i
    (SRC / "rules" / "block.json").write_text(json.dumps(block, separators=(",", ":")), encoding="utf-8")
    (SRC / "rules" / "allow.json").write_text(json.dumps(allow, separators=(",", ":")), encoding="utf-8")

    every = cos.generic | {s for v in cos.specific.values() for s in v}
    valid = validate(every)
    generic = sorted((cos.generic - cos.generic_off) & valid)
    css = "".join(",".join(c) + "{display:none!important}\n" for c in chunks(generic, 200))
    (SRC / "content" / "generic.css").write_text("/* Generated by tools/filterlists.py from EasyList and uBlock filters. */\n" + css, encoding="utf-8")

    generic_set = set(generic)
    partial = {d for d, ex in cos.exceptions.items() if ex & generic_set} - net.no_generic
    cosmetic = {
        "generic": generic,
        "specific": {d: sorted(s & valid) for d, s in sorted(cos.specific.items()) if s & valid},
        "exceptions": {d: sorted(s) for d, s in sorted(cos.exceptions.items()) if s & (generic_set | {x for v in cos.specific.values() for x in v})},
        "noGeneric": sorted(net.no_generic),
        "partialGeneric": sorted(partial),
        "noCosmetic": sorted(net.no_cosmetic),
    }
    (SRC / "rules" / "cosmetic.json").write_text(json.dumps(cosmetic, separators=(",", ":")), encoding="utf-8")

    scriptlets = {}
    for d, calls in sorted(cos.scriptlets.items()):
        off = cos.scriptlet_off.get(d, set())
        kept = [c for c in calls if c[0] not in off and "" not in off]
        if kept:
            scriptlets[d] = [list(x) for x in dict.fromkeys(tuple(c) for c in kept)]
    (SRC / "scriptlets").mkdir(exist_ok=True)
    (SRC / "scriptlets" / "config.js").write_text(
        "// Generated by tools/filterlists.py from uBlock Origin filters. Do not edit.\n"
        f"globalThis.HIB_SCRIPTLETS = {json.dumps(scriptlets, separators=(',', ':'))};\n")
    (SRC / "scriptlets" / "hosts.json").write_text(json.dumps(sorted(scriptlets)), encoding="utf-8")

    print(f"block rules {len(block)}  allow rules {len(allow)}  skipped network {net.skipped}")
    print(f"generic selectors {len(generic)}  sites with own hiding {len(cosmetic['specific'])}  "
          f"no-generic sites {len(net.no_generic)}  partial-generic sites {len(partial)}  skipped cosmetic {cos.skipped}")
    print(f"scriptlet sites {len(scriptlets)}  calls {sum(map(len, scriptlets.values()))}")


if __name__ == "__main__":
    main()

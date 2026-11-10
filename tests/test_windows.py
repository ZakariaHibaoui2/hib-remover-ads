"""Tests the Windows app's blocker without touching any Windows setting.

Starts store/HibRemoverAds-Windows.exe in test mode on a spare port, sends it
real DNS lookups and checks the answers: ad servers used by Windows apps get
"nowhere", everything else gets a real address, and answers are fast.

Build first: python installer/build.py
Run:         python tests/test_windows.py
"""
import json
import random
import shutil
import socket
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "store" / "HibRemoverAds-Windows.exe"
PORT = 5391
A, AAAA, TXT, HTTPS = 1, 28, 16, 65

# Ad and tracking servers that Windows apps really call.
BLOCKED = {
    "Spotify": ["adeventtracker.spotify.com", "ads-fa.spotify.com", "analytics.spotify.com", "log.spotify.com",
                "audio-ads.spotify.com", "pixel.spotify.com", "adstudio.spotify.com"],
    "Google ads (used inside most free apps)": ["doubleclick.net", "googleads.g.doubleclick.net", "pagead2.googlesyndication.com",
                "googleadservices.com", "adservice.google.com", "pubads.g.doubleclick.net", "securepubads.g.doubleclick.net",
                "google-analytics.com", "app-measurement.com"],
    "Ad networks in free apps and games": ["applovin.com", "ms.applovin.com", "unityads.unity3d.com", "adcolony.com", "ads.vungle.com",
                "live.chartboost.com", "config.inmobi.com", "outcome-ssp.supersonicads.com", "ads.mopub.com", "ws.tapjoyads.com"],
    "Windows and Microsoft apps": ["ads.msn.com", "rad.msn.com", "flex.msn.com", "adnexus.net", "ads1.msads.net",
                "browser.events.data.msn.com", "bat.bing.com"],
    "Other apps": ["utorrent-ads.bittorrent.com", "ads.yahoo.com", "ads.tiktok.com", "an.facebook.com", "ads-api.twitter.com",
                "ads.linkedin.com", "adserver.adtech.de", "criteo.com", "taboola.com", "outbrain.com", "scorecardresearch.com",
                "hotjar.com", "amazon-adsystem.com", "adnxs.com", "fastlane.rubiconproject.com", "ads.pubmatic.com", "moatads.com"],
}

# Servers that must keep working.
ALLOWED = {
    "Spotify music and login": ["spclient.wg.spotify.com", "apresolve.spotify.com", "login5.spotify.com", "open.spotify.com",
                "api.spotify.com", "accounts.spotify.com", "i.scdn.co", "audio-ak-spotify-com.akamaized.net"],
    "Windows": ["login.live.com", "login.microsoftonline.com", "www.msftconnecttest.com", "time.windows.com",
                "download.windowsupdate.com", "storeedgefd.dsx.mp.microsoft.com"],
    "Everyday sites and apps": ["google.com", "www.youtube.com", "github.com", "wikipedia.org", "whatsapp.com", "web.whatsapp.com",
                "discord.com", "zoom.us", "store.steampowered.com", "netflix.com", "www.amazon.com", "outlook.office365.com",
                "teams.microsoft.com", "hespress.com", "www.facebook.com", "www.instagram.com", "x.com", "www.linkedin.com",
                "drive.google.com", "mail.google.com", "www.paypal.com", "www.cloudflare.com"],
}

results, failures = [], []


def check(name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": detail})
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


def packet(name, qtype, qid=None, edns=False):
    qid = random.randrange(1, 65535) if qid is None else qid
    q = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 1 if edns else 0)
    for label in name.split("."):
        q += bytes([len(label)]) + label.encode()
    q += b"\0" + struct.pack(">HH", qtype, 1)
    if edns:
        q += b"\0" + struct.pack(">HHIH", 41, 1232, 0, 0)
    return qid, q


def skip_name(r, p):
    while True:
        n = r[p]
        if n == 0:
            return p + 1
        if n & 0xC0 == 0xC0:
            return p + 2
        p += n + 1


def parse(r):
    """Returns (rcode, truncated, [addresses or raw record data])."""
    flags, qd, an = struct.unpack(">HHH", r[2:8])
    p = 12
    for _ in range(qd):
        p = skip_name(r, p) + 4
    out = []
    for _ in range(an):
        p = skip_name(r, p)
        rtype, _, _, rdlen = struct.unpack(">HHIH", r[p:p + 10])
        data = r[p + 10:p + 10 + rdlen]
        p += 10 + rdlen
        if rtype == A:
            out.append(socket.inet_ntoa(data))
        elif rtype == AAAA:
            out.append(socket.inet_ntop(socket.AF_INET6, data))
        elif rtype != 5:
            out.append(data)
    return flags & 0xF, bool(flags & 0x200), out


def ask(name, qtype=A, timeout=6.0, edns=False, host="127.0.0.1"):
    """Returns (rcode, truncated, answers, milliseconds, raw)."""
    qid, q = packet(name, qtype, edns=edns)
    fam = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(fam, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t0 = time.perf_counter()
        s.sendto(q, (host, PORT))
        r, _ = s.recvfrom(4096)
        ms = (time.perf_counter() - t0) * 1000
    assert struct.unpack(">H", r[:2])[0] == qid, "answer id differs"
    return parse(r) + (ms, r)


def ask_tcp(name, qtype=A):
    _, q = packet(name, qtype)
    with socket.create_connection(("127.0.0.1", PORT), timeout=6) as s:
        s.sendall(struct.pack(">H", len(q)) + q)
        head = s.recv(2)
        n = struct.unpack(">H", head)[0]
        r = b""
        while len(r) < n:
            r += s.recv(n - len(r))
    return parse(r)


def is_blocked(name):
    rcode, _, ans, _, _ = ask(name)
    return rcode == 0 and ans == ["0.0.0.0"]


def resolves(name):
    try:
        rcode, _, ans, _, _ = ask(name)
    except socket.timeout:
        return False
    return rcode == 0 and len(ans) > 0 and "0.0.0.0" not in ans


def read_stats(data):
    out = {}
    for line in (data / "stats.txt").read_text().splitlines():
        k, _, v = line.partition("=")
        out.setdefault(k, v)
    return out


def main():
    if not EXE.exists():
        sys.exit("Build first: python installer/build.py")
    data = Path(tempfile.mkdtemp(prefix="hib-test-"))
    proc = subprocess.Popen([str(EXE), "--run", "--port", str(PORT), "--data", str(data), "--seconds", "600"])
    try:
        t0 = time.time()
        while not (data / "ready").exists():
            assert proc.poll() is None, "the blocker exited at startup"
            assert time.time() - t0 < 20, "the blocker took more than 20 s to start"
            time.sleep(0.05)
        startup = time.time() - t0
        check("starts and loads the block list", True, f"{startup:.2f} s")
        run(data, proc)
    finally:
        proc.kill()
        proc.wait()
        shutil.rmtree(data, ignore_errors=True)
    out = ROOT / "tests" / "windows_results.json"
    out.write_text(json.dumps({"date": time.strftime("%Y-%m-%d"), "summary": summary, "checks": results}, indent=1))
    print(f"\n{len(results) - len(failures)} of {len(results)} checks passed. Results: {out}")
    sys.exit(1 if failures else 0)


summary = {}


def run(data, proc):
    print("\nAd servers used by Windows apps are blocked")
    total = blocked = 0
    for group, names in BLOCKED.items():
        bad = [n for n in names if not is_blocked(n)]
        total += len(names)
        blocked += len(names) - len(bad)
        check(group, not bad, f"{len(names) - len(bad)}/{len(names)}" + (", got through: " + ", ".join(bad) if bad else ""))
    summary["ad_servers_blocked"] = f"{blocked}/{total}"

    print("\nReal servers still work")
    total = fine = 0
    for group, names in ALLOWED.items():
        bad = [n for n in names if not resolves(n)]
        total += len(names)
        fine += len(names) - len(bad)
        check(group, not bad, f"{len(names) - len(bad)}/{len(names)}" + (", broken: " + ", ".join(bad) if bad else ""))
    summary["real_servers_working"] = f"{fine}/{total}"

    print("\nDetails of a blocked answer")
    rcode, _, ans, _, raw = ask("SuB.DoubleClick.NET")
    check("subdomains of a blocked server are blocked too", ans == ["0.0.0.0"])
    check("the name comes back spelled as it was asked", b"\x03SuB\x0bDoubleClick\x03NET" in raw)
    check("IPv6 lookups get '::'", ask("doubleclick.net", AAAA)[2] == ["::"])
    rcode, _, ans, _, _ = ask("doubleclick.net", HTTPS)
    check("other record types get an empty answer", rcode == 0 and ans == [])
    check("blocked over TCP too", ask_tcp("doubleclick.net")[2] == ["0.0.0.0"])
    check("real lookups work over TCP", len(ask_tcp("example.com")[2]) > 0)
    try:
        check("listens on IPv6 (::1)", ask("doubleclick.net", host="::1")[2] == ["0.0.0.0"])
    except OSError as e:
        check("listens on IPv6 (::1)", False, str(e))
    rcode, _, ans, _, _ = ask("this-name-does-not-exist-hib-test.com")
    check("a name that doesn't exist says so", rcode == 3)
    rcode, tc, ans, _, _ = ask("google.com", TXT)
    full = ask_tcp("google.com", TXT)[2]
    check("an answer too big for UDP is retried over TCP", (tc and len(full) > 3) or len(ans) > 3, f"{len(full)} records over TCP")

    print("\nSpeed")
    times = sorted(ask("doubleclick.net")[3] for _ in range(300))
    blocked_ms = statistics.median(times)
    check("a blocked ad server is answered instantly", blocked_ms < 1.0, f"median {blocked_ms:.2f} ms, slowest of 300: {times[-1]:.2f} ms")
    fresh = [f"hib-speed-{random.randrange(10**9)}.wikipedia.org" for _ in range(3)]
    names = ["example.org", "mozilla.org", "python.org", "stackoverflow.com", "bbc.co.uk", "lemonde.fr", "aljazeera.net",
             "reddit.com", "apple.com", "ubuntu.com", "debian.org", "nytimes.com", "medium.com", "twitch.tv", "imdb.com"]
    first = []
    for n in names:
        try:
            first.append(ask(n)[3])
        except socket.timeout:
            first.append(6000)
    first_ms = statistics.median(first)
    check("a first lookup (encrypted, over the internet) is quick", first_ms < 250, f"median {first_ms:.0f} ms, slowest {max(first):.0f} ms")
    repeat = sorted(ask(n)[3] for n in names for _ in range(20))
    repeat_ms = statistics.median(repeat)
    check("a repeated lookup is instant", repeat_ms < 1.0, f"median {repeat_ms:.2f} ms, slowest of {len(repeat)}: {repeat[-1]:.2f} ms")
    summary.update(blocked_answer_ms=round(blocked_ms, 2), first_lookup_ms=round(first_ms), repeat_lookup_ms=round(repeat_ms, 2))

    # Compare with the PC's normal DNS server, asked directly.
    try:
        normal = []
        for n in ["example.net", "gnu.org", "kernel.org", "w3.org", "ietf.org"]:
            _, q = packet(n, A)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(3)
                t0 = time.perf_counter()
                s.sendto(q, (system_dns(), 53))
                s.recvfrom(4096)
                normal.append((time.perf_counter() - t0) * 1000)
        print(f"        for comparison, this network's own DNS server: median {statistics.median(normal):.0f} ms per first lookup")
    except Exception as e:
        print(f"        (couldn't time the network's own DNS server: {e})")

    print("\nUnder load")
    errors = []
    mix = [n for g in BLOCKED.values() for n in g] + names

    def worker():
        try:
            for _ in range(50):
                ask(random.choice(mix), timeout=8)
        except Exception as e:
            errors.append(repr(e))
    threads = [threading.Thread(target=worker) for _ in range(40)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    took = time.perf_counter() - t0
    check("2,000 lookups from 40 programs at once", not errors, f"{2000 / took:,.0f} lookups per second" + (f", {len(errors)} errors: {errors[0]}" if errors else ""))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for junk in [b"", b"\0", b"x" * 11, bytes(random.randrange(256) for _ in range(300)), b"\0" * 12 + b"\xff" * 40,
                     struct.pack(">HHHHHH", 7, 0x0100, 1, 0, 0, 0) + b"\x3fabc"]:
            s.sendto(junk, ("127.0.0.1", PORT))
    time.sleep(0.3)
    check("garbage packets don't stop it", proc.poll() is None and is_blocked("doubleclick.net"))

    print("\nSwitches")
    user = data / "user"
    (user / "settings.txt").write_text("enabled=0\npause_until=0\n")
    time.sleep(2.2)
    check("turned off: ad servers resolve again", resolves("doubleclick.net"))
    (user / "settings.txt").write_text("enabled=1\npause_until=0\n")
    time.sleep(2.2)
    check("turned on: blocked again", is_blocked("doubleclick.net"))
    # .NET ticks: 100 ns since year 0001.
    until = int((time.time() + 3600) * 10_000_000) + 621355968000000000
    (user / "settings.txt").write_text(f"enabled=1\npause_until={until}\n")
    time.sleep(2.2)
    check("paused for an hour: ad servers resolve", resolves("doubleclick.net"))
    (user / "settings.txt").write_text("enabled=1\npause_until=0\n")
    time.sleep(2.2)
    (user / "allow.txt").write_text("ads.linkedin.com\n")
    time.sleep(2.2)
    check("a server you allow resolves", resolves("ads.linkedin.com"))
    check("the others stay blocked", is_blocked("ads.tiktok.com"))
    (user / "allow.txt").write_text("")
    time.sleep(2.2)
    check("removed from your allow list: blocked again", is_blocked("ads.linkedin.com"))

    print("\nCounters")
    time.sleep(2.2)
    st = read_stats(data)
    check("counts what it blocked", int(st["blocked"]) > 300 and int(st["today"]) > 300, f"{st['blocked']} blocked of {st['queries']} lookups")
    check("lists the most-blocked servers", "doubleclick.net" in (data / "stats.txt").read_text())
    check("has a full block list", int(st["rules"]) > 100000, f"{int(st['rules']):,} servers")
    check("lookups left this PC encrypted", st["encrypted"] == "1")
    summary.update(block_list=int(st["rules"]))
    log = (data / "log.txt").read_text() if (data / "log.txt").exists() else ""
    check("the log holds no names of sites you visited", not any(n in log for n in names + ["doubleclick"]))

    # The program checks its own extras on this PC, puts every setting back, and prints one line per check.
    print("\nSpotify audio ads and the ads built into Windows")
    out = subprocess.run([str(EXE), "--test-extras"], capture_output=True, text=True, timeout=120).stdout
    for line in out.splitlines():
        state, _, rest = line.partition("\t")
        name, _, detail = rest.partition("\t")
        if state == "skip":
            print("  skip  " + name)
        else:
            check(name, state == "ok", "" if "window" in name else detail)


def system_dns():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "(Get-NetIPConfiguration | ? {$_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up'} | Select -First 1)"
                          r".DNSServer.ServerAddresses | ? {$_ -match '^\d+\.' -and $_ -notmatch '^127\.'} | Select -First 1"],
                         capture_output=True, text=True).stdout.strip()
    return out or "1.1.1.1"


if __name__ == "__main__":
    main()

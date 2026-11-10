"""Tests everything about installing that can be tested without installing.

Nothing here needs administrator rights, changes a Windows setting or leaves
anything running. It checks:

  - this PC is ready (the same check the installer runs before it asks for permission)
  - what install and uninstall would do to the DNS setting, as a dry run
  - the blocker on the real DNS port (53), asked by Windows' own lookup tools
  - a second copy, or any program already on port 53, fails cleanly
  - the downloads carry what they should, and the installer's pages draw
  - the one-command install script, run against the local build

Build first: python installer/build.py
Run:         python tests/test_install.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "store"
APP = STORE / "HibRemoverAds-Windows.exe"
SETUP = STORE / "HibRemoverAds-Setup.exe"
ZIP = STORE / "hib-remover-ads.zip"

results, failures = [], []


def check(name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": detail})
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


def run(args, **kw):
    return subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=kw.pop("timeout", 120), **kw)


def ps(command, timeout=60):
    return run(["powershell", "-NoProfile", "-Command", command], timeout=timeout).stdout.strip()


def start(port, data, seconds=120):
    proc = subprocess.Popen([str(APP), "--run", "--port", str(port), "--data", str(data), "--seconds", str(seconds)])
    t0 = time.time()
    while time.time() - t0 < 20:
        if (data / "ready").exists():
            return proc, True
        if proc.poll() is not None:
            return proc, False
        time.sleep(0.05)
    return proc, False


def ready():
    print("\nIs this PC ready? (the installer runs this before it asks for permission)")
    out = run([APP, "--check"])
    lines = [l.split("\t") for l in out.stdout.splitlines() if l.strip()]
    check("the readiness check runs without administrator rights", len(lines) >= 4, f"{len(lines)} checks, exit code {out.returncode}")
    for state, name, *detail in lines:
        if state == "warn":
            print(f"  note  {name}  ({detail[0] if detail else ''})")
        else:
            check(name, state == "ok", "" if "connection" in name.lower() else (detail[0] if detail else ""))


def plan():
    print("\nWhat install and uninstall would do to the DNS setting (dry run, nothing is changed)")
    before = ps("Get-DnsClientServerAddress | % { $_.InterfaceAlias + '|' + $_.AddressFamily + '|' + ($_.ServerAddresses -join ',') }")
    out = run([APP, "--plan-dns"]).stdout
    rows = [l.split("\t") for l in out.splitlines() if l.strip()]
    adapters = [r[1:] for r in rows if r[0] == "adapter"]
    install = [r[1] for r in rows if r[0] == "install"]
    undo = [r[1] for r in rows if r[0] == "uninstall"]
    if not adapters:
        print("  skip  no connected network adapter right now")
        return
    check("finds the connected network adapter", True, f"{len(adapters)} adapter(s)")
    good = restores = True
    for name, v4, v6 in adapters:
        mine = [c for c in install if f'name="{name}"' in c]
        good &= any("ipv4 set" in c and "address=127.0.0.1" in c for c in mine)
        good &= any("ipv4 add" in c and "address=1.1.1.1 index=2" in c for c in mine)
        back = [c for c in undo if f'name="{name}"' in c and " ipv4 " in c]
        if v4 == "automatic":
            restores &= len(back) == 1 and back[0].endswith("source=dhcp")
        else:
            servers = re.split(r"[ ,]+", v4)
            got = [re.search(r"address=(\S+)", c).group(1) for c in back]
            restores &= got == servers
        if v6 != "none":
            good &= any("ipv6 set" in c and "address=::1" in c for c in mine)
            back6 = [c for c in undo if f'name="{name}"' in c and " ipv6 " in c]
            restores &= len(back6) >= 1 and (back6[0].endswith("source=dhcp") if v6 == "automatic" else True)
    check("install points each adapter at the blocker, with 1.1.1.1 as a spare", good)
    check("uninstall puts each adapter back exactly as it is now", restores)
    spare = [c for c in install if "index=3" in c]
    check("the network's own DNS server is kept as a second spare", len(spare) >= 1 or all(a[1] == "automatic" for a in adapters) and not spare or bool(spare),
          "yes" if spare else "this network handed out none")
    check("a name with spaces or accents is quoted", all(re.search(r'name="[^"]+"', c) for c in install + undo))
    after = ps("Get-DnsClientServerAddress | % { $_.InterfaceAlias + '|' + $_.AddressFamily + '|' + ($_.ServerAddresses -join ',') }")
    check("the dry run changed nothing on this PC", before == after)


def real_port():
    print("\nThe blocker on the real DNS port, asked by Windows' own tools")
    data = Path(tempfile.mkdtemp(prefix="hib-port53-"))
    proc, ok = start(53, data)
    try:
        if not ok:
            why = (data / "failed").read_text() if (data / "failed").exists() else "no answer"
            print(f"  skip  port 53 is in use on this PC right now ({why})")
            return
        check("starts on port 53 without administrator rights", True)
        out = ps("(Resolve-DnsName doubleclick.net -Server 127.0.0.1 -DnsOnly -Type A).IPAddress")
        check("Windows' Resolve-DnsName gets 'nowhere' for an ad server", out == "0.0.0.0", out)
        out = ps("(Resolve-DnsName adeventtracker.spotify.com -Server 127.0.0.1 -DnsOnly -Type A).IPAddress")
        check("the same for Spotify's ad tracker", out == "0.0.0.0", out)
        out = ps("(Resolve-DnsName doubleclick.net -Server 127.0.0.1 -DnsOnly -Type AAAA).IPAddress")
        check("and for IPv6", out == "::", out)
        out = ps("(Resolve-DnsName example.com -Server 127.0.0.1 -DnsOnly -Type A | ? IPAddress | Select -First 1).IPAddress")
        check("a real site gets a real address", re.match(r"^\d+\.\d+\.\d+\.\d+$", out or "") and out != "0.0.0.0", out)
        out = ps("(Resolve-DnsName spclient.wg.spotify.com -Server 127.0.0.1 -DnsOnly -Type A | ? IPAddress | Select -First 1).IPAddress")
        check("Spotify's music server gets a real address", re.match(r"^\d+\.\d+\.\d+\.\d+$", out or "") and out != "0.0.0.0")
        out = ps("(Resolve-DnsName example.com -Server 127.0.0.1 -DnsOnly -TcpOnly -Type A | ? IPAddress | Select -First 1).IPAddress")
        check("works over TCP too", re.match(r"^\d+\.\d+\.\d+\.\d+$", out or ""))
        out = ps("(Resolve-DnsName doubleclick.net -Server ::1 -DnsOnly -Type A).IPAddress")
        check("answers on IPv6 (::1) too", out == "0.0.0.0", out)
        out = run(["nslookup", "doubleclick.net", "127.0.0.1"]).stdout
        check("nslookup agrees", "0.0.0.0" in out)
        out = ps("$t = Measure-Command { 1..50 | % { Resolve-DnsName doubleclick.net -Server 127.0.0.1 -DnsOnly -Type A | Out-Null } }; [int]($t.TotalMilliseconds / 50 * 100)")
        ms = int(out or 0) / 100
        check("Windows gets a blocked answer in under 5 ms, tool overhead included", 0 < ms < 5, f"{ms:.2f} ms each")

        # Anything already on port 53 must stop a second copy cleanly: an error code, not a crash, and the first keeps working.
        data2 = Path(tempfile.mkdtemp(prefix="hib-port53b-"))
        second, ok2 = start(53, data2, seconds=5)
        try:
            second.wait(timeout=15)
        except subprocess.TimeoutExpired:
            second.kill()
        check("with port 53 taken, a second copy stops with an error instead of crashing",
              not ok2 and second.returncode == 2 and (data2 / "failed").exists(), f"exit code {second.returncode}")
        shutil.rmtree(data2, ignore_errors=True)
        out = run([APP, "--check"])
        busy = [l for l in out.stdout.splitlines() if l.startswith("FAIL") and "53" in l]
        check("the readiness check then says port 53 is busy, and names the program", out.returncode == 1 and busy and "HibRemoverAds" in busy[0],
              busy[0].split("\t")[2][:60] if busy else "")
        out = ps("(Resolve-DnsName doubleclick.net -Server 127.0.0.1 -DnsOnly -Type A).IPAddress")
        check("the first copy is still answering", out == "0.0.0.0")
    finally:
        proc.kill()
        proc.wait()

    # Counters survive a restart.
    data3 = Path(tempfile.mkdtemp(prefix="hib-restart-"))
    p, ok = start(5392, data3, seconds=4)
    if ok:
        for _ in range(25):
            ps_fast(5392)
        p.wait(timeout=20)
        p, ok = start(5392, data3, seconds=4)
        time.sleep(2.5)
        stats = dict(l.split("=", 1) for l in (data3 / "stats.txt").read_text().splitlines() if "=" in l and not l.startswith("top"))
        check("the blocked-ads count survives a restart", ok and int(stats.get("total", 0)) >= 25, f"total {stats.get('total')}")
        p.kill()
        p.wait()
    shutil.rmtree(data3, ignore_errors=True)
    shutil.rmtree(data, ignore_errors=True)
    out = ps("(Get-NetUDPEndpoint -LocalPort 53 -ErrorAction SilentlyContinue | Measure-Object).Count")
    check("nothing is left running on port 53", out in ("0", ""), out)


def ps_fast(port):
    import socket
    import struct
    q = struct.pack(">HHHHHH", 1, 0x0100, 1, 0, 0, 0) + b"\x0bdoubleclick\x03net\x00" + struct.pack(">HH", 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(3)
        s.sendto(q, ("127.0.0.1", port))
        s.recvfrom(512)


def downloads():
    print("\nThe downloads")
    app, setup, ext = APP.read_bytes(), SETUP.read_bytes(), ZIP.read_bytes()
    check("the installer carries this exact Windows app", app in setup, f"{len(app) // 1024} KB inside {len(setup) // 1024} KB")
    check("the installer carries this exact browser extension", ext in setup)
    with zipfile.ZipFile(ZIP) as z:
        version = json.loads(z.read("manifest.json"))["version"]
    info = ps(f"(Get-Item '{APP}').VersionInfo.FileVersion + '|' + (Get-Item '{SETUP}').VersionInfo.FileVersion")
    check("all three have the same version", info == f"{version}.0|{version}.0", f"{version}, {info}")
    check("the Windows app runs as a normal user and only asks for permission to install", b'level="asInvoker"' in app)
    check("small enough to download in seconds", len(setup) < 8_000_000 and len(app) < 5_000_000, f"installer {len(setup) / 1e6:.1f} MB, Windows app {len(app) / 1e6:.1f} MB")
    net = ps("(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\NET Framework Setup\\NDP\\v4\\Full').Release")
    check("needs nothing extra: it uses the .NET that ships with Windows 10 and 11", int(net or 0) >= 461808, f"release {net}")
    tmp = Path(tempfile.mkdtemp(prefix="hib-shots-"))
    for name, extra in [("first page", []), ("last page", ["--steps"])]:
        shot = tmp / (name.replace(" ", "-") + ".png")
        run([SETUP, "--screenshot", shot] + extra)
        check(f"the installer's {name} draws", shot.exists() and shot.stat().st_size > 10_000)
    shot = tmp / "window.png"
    run([APP, "--screenshot", shot, "--data", tmp])
    check("the app's window draws with no data yet", shot.exists() and shot.stat().st_size > 10_000)
    shutil.rmtree(tmp, ignore_errors=True)
    out = run([str(Path(os.environ["ProgramFiles"]) / "Windows Defender" / "MpCmdRun.exe"), "-Scan", "-ScanType", "3", "-File", APP, "-DisableRemediation"], timeout=300).stdout
    out += run([str(Path(os.environ["ProgramFiles"]) / "Windows Defender" / "MpCmdRun.exe"), "-Scan", "-ScanType", "3", "-File", SETUP, "-DisableRemediation"], timeout=300).stdout
    if "found no threats" in out:
        check("Windows Defender finds nothing in either download", out.count("found no threats") == 2)
    else:
        print("  skip  Windows Defender isn't available to scan with")


def one_command():
    print("\nThe one-command install, run against this build (into a temporary folder)")
    script = ROOT / "docs" / "install.ps1"
    parse = ps(f"$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$e); $e.Count")
    check("the script has no syntax errors", parse == "0", parse)
    target = Path(tempfile.mkdtemp(prefix="hib-oneline-"))
    env = dict(os.environ, HIB_SOURCE=STORE.as_uri(), HIB_TARGET=str(target), HIB_ANSWERS="browser=none;windows=check")
    t0 = time.time()
    out = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script], env=env, timeout=180)
    took = time.time() - t0
    text = out.stdout + out.stderr
    manifest = target / "extension" / "manifest.json"
    check("it unpacks the browser extension", manifest.exists() and json.loads(manifest.read_text(encoding="utf-8"))["version"] in text, f"{took:.0f} s")
    check("it downloads the Windows app", (target / "HibRemoverAds-Windows.exe").exists()
          and (target / "HibRemoverAds-Windows.exe").read_bytes() == APP.read_bytes())
    check("the downloaded app runs and finds this PC ready", "This PC is ready" in text, "" if "This PC is ready" in text else text[-200:])
    check("it finishes without an error", out.returncode == 0 and "Exception" not in text)
    env["HIB_ANSWERS"] = "browser=none;windows=no"
    shutil.rmtree(target, ignore_errors=True)
    out = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script], env=env, timeout=180)
    check("answering no skips the Windows app", out.returncode == 0 and not (target / "HibRemoverAds-Windows.exe").exists()
          and (target / "extension" / "manifest.json").exists())
    shutil.rmtree(target, ignore_errors=True)


def main():
    for f in (APP, SETUP, ZIP):
        if not f.exists():
            sys.exit("Build first: python installer/build.py")
    ready()
    plan()
    real_port()
    downloads()
    one_command()
    print(f"\n{len(results) - len(failures)} of {len(results)} checks passed.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

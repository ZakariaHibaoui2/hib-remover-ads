// Hib Remover Ads for Windows: the Windows service, install and uninstall, and the entry point.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Principal;
using System.ServiceProcess;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("Hib Remover Ads for Windows")]
[assembly: AssemblyProduct("Hib Remover Ads")]
[assembly: AssemblyDescription("Blocks ads and trackers in every Windows app")]
[assembly: AssemblyCompany("Zakaria Hibaoui")]
[assembly: AssemblyVersion("2.2.0.0")]
[assembly: AssemblyFileVersion("2.2.0.0")]

namespace Hib
{
    /// <summary>
    /// Points this PC's DNS setting at the blocker and puts it back.
    /// 1.1.1.1 and the network's own server are kept as spares: if the blocker ever
    /// stops answering, Windows moves on to them by itself, so the internet keeps working.
    /// </summary>
    static class DnsConfig
    {
        const string Ours4 = "127.0.0.1", Spare4 = "1.1.1.1", Ours6 = "::1", Spare6 = "2606:4700:4700::1111";
        static readonly object gate = new object();
        // Dry run: nothing is changed, the commands are only written down (see --plan-dns).
        public static bool DryRun;
        public static readonly List<string> Planned = new List<string>();
        static Dictionary<string, string> dryBackup = new Dictionary<string, string>();
        static string BackupFile { get { return Path.Combine(Paths.Data, "dns-backup.txt"); } }

        static Dictionary<string, string> ReadBackup()
        {
            var d = new Dictionary<string, string>();
            if (DryRun) return new Dictionary<string, string>(dryBackup);
            try
            {
                foreach (var line in File.ReadAllLines(BackupFile))
                {
                    int bar = line.LastIndexOf('=');
                    if (bar > 0) d[line.Substring(0, bar)] = line.Substring(bar + 1);
                }
            }
            catch { }
            return d;
        }

        static void WriteBackup(Dictionary<string, string> d)
        {
            if (DryRun) { dryBackup = new Dictionary<string, string>(d); return; }
            var lines = new List<string>();
            foreach (var kv in d) lines.Add(kv.Key + "=" + kv.Value);
            File.WriteAllLines(BackupFile, lines.ToArray());
        }

        static string Current(string id, bool v6)
        {
            using (var k = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\" + (v6 ? "Tcpip6" : "Tcpip") + @"\Parameters\Interfaces\" + id))
                return k == null ? "" : ((k.GetValue("NameServer") as string) ?? "").Trim();
        }

        // The DNS server this network used before us: what you had set, or what the router handed out.
        static string NetworkOwn(string id, Dictionary<string, string> backup)
        {
            string list;
            backup.TryGetValue(id + "|4", out list);
            if (string.IsNullOrEmpty(list))
                using (var k = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\" + id))
                    list = k == null ? "" : (k.GetValue("DhcpNameServer") as string) ?? "";
            foreach (string part in list.Split(new[] { ',', ' ' }, StringSplitOptions.RemoveEmptyEntries))
            {
                IPAddress a;
                if (IPAddress.TryParse(part, out a) && a.AddressFamily == AddressFamily.InterNetwork && !IPAddress.IsLoopback(a) && part != Spare4) return part;
            }
            return null;
        }

        static bool Eligible(NetworkInterface nic)
        {
            if (nic.OperationalStatus != OperationalStatus.Up) return false;
            var t = nic.NetworkInterfaceType;
            if (t != NetworkInterfaceType.Ethernet && t != NetworkInterfaceType.Wireless80211 && t != NetworkInterfaceType.GigabitEthernet
                && t != NetworkInterfaceType.FastEthernetT && t != NetworkInterfaceType.FastEthernetFx && t != NetworkInterfaceType.Ethernet3Megabit) return false;
            // Only adapters that lead to the internet. Virtual switches and VPN adapters are left alone.
            return nic.GetIPProperties().GatewayAddresses.Count > 0;
        }

        /// <summary>Sets the DNS of every connected adapter. With force, sets it again even if it is already ours.</summary>
        public static void Apply(bool v6, bool force)
        {
            lock (gate)
            {
                var backup = ReadBackup();
                bool changed = false;
                foreach (var nic in NetworkInterface.GetAllNetworkInterfaces())
                {
                    try
                    {
                        if (!Eligible(nic)) continue;
                        string cur = Current(nic.Id, false);
                        bool ours = cur.StartsWith(Ours4);
                        if (!ours) { backup[nic.Id + "|4"] = cur; changed = true; }
                        if (!ours || force)
                        {
                            Netsh("interface ipv4 set dnsservers name=\"" + nic.Name + "\" source=static address=" + Ours4 + " register=primary validate=no");
                            Netsh("interface ipv4 add dnsservers name=\"" + nic.Name + "\" address=" + Spare4 + " index=2 validate=no");
                            string own = NetworkOwn(nic.Id, backup);
                            if (own != null) Netsh("interface ipv4 add dnsservers name=\"" + nic.Name + "\" address=" + own + " index=3 validate=no");
                        }
                        if (!v6 || !nic.Supports(NetworkInterfaceComponent.IPv6)) continue;
                        cur = Current(nic.Id, true);
                        ours = cur.StartsWith(Ours6);
                        if (!ours) { backup[nic.Id + "|6"] = cur; changed = true; }
                        if (!ours || force)
                        {
                            Netsh("interface ipv6 set dnsservers name=\"" + nic.Name + "\" source=static address=" + Ours6 + " register=primary validate=no");
                            Netsh("interface ipv6 add dnsservers name=\"" + nic.Name + "\" address=" + Spare6 + " index=2 validate=no");
                        }
                    }
                    catch (Exception ex) { Log.Write("DNS apply: " + ex.Message); }
                }
                if (changed) try { WriteBackup(backup); } catch (Exception ex) { Log.Write("DNS backup: " + ex.Message); }
            }
        }

        /// <summary>Puts every adapter back exactly as it was before.</summary>
        public static void Restore()
        {
            lock (gate)
            {
                var backup = ReadBackup();
                if (backup.Count == 0) return;
                var names = new Dictionary<string, string>();
                foreach (var nic in NetworkInterface.GetAllNetworkInterfaces()) names[nic.Id] = nic.Name;
                foreach (var kv in backup)
                {
                    try
                    {
                        string id = kv.Key.Substring(0, kv.Key.Length - 2);
                        bool v6 = kv.Key.EndsWith("|6");
                        string name, ip = v6 ? "ipv6" : "ipv4";
                        if (!names.TryGetValue(id, out name)) continue;
                        if (!DryRun && !Current(id, v6).StartsWith(v6 ? Ours6 : Ours4)) continue;   // changed by someone else since: leave it
                        var servers = kv.Value.Split(new[] { ',', ' ' }, StringSplitOptions.RemoveEmptyEntries);
                        if (servers.Length == 0)
                            Netsh("interface " + ip + " set dnsservers name=\"" + name + "\" source=dhcp");
                        else
                        {
                            Netsh("interface " + ip + " set dnsservers name=\"" + name + "\" source=static address=" + servers[0] + " register=primary validate=no");
                            for (int i = 1; i < servers.Length; i++)
                                Netsh("interface " + ip + " add dnsservers name=\"" + name + "\" address=" + servers[i] + " index=" + (i + 1) + " validate=no");
                        }
                    }
                    catch (Exception ex) { Log.Write("DNS restore: " + ex.Message); }
                }
                if (DryRun) return;
                try { File.Delete(BackupFile); } catch { }
                Program.Run("ipconfig.exe", "/flushdns");
            }
        }

        static void Netsh(string args)
        {
            if (DryRun) Planned.Add("netsh " + args);
            else Program.Run("netsh.exe", args);
        }

        /// <summary>The adapters that would be changed, with their DNS setting as it is now.</summary>
        public static List<string> Describe()
        {
            var list = new List<string>();
            foreach (var nic in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (!Eligible(nic)) continue;
                string v4 = Current(nic.Id, false), v6 = Current(nic.Id, true);
                list.Add(nic.Name + "\t" + (v4.Length == 0 ? "automatic" : v4) + "\t"
                    + (!nic.Supports(NetworkInterfaceComponent.IPv6) ? "none" : v6.Length == 0 ? "automatic" : v6));
            }
            return list;
        }
    }

    class Service : ServiceBase
    {
        Engine engine;
        public Service() { ServiceName = Paths.ServiceName; CanShutdown = true; }

        protected override void OnStart(string[] args)
        {
            // If port 53 is taken this throws, the service doesn't start, and no setting is touched.
            engine = new Engine { IsService = true };
            engine.Start();
            if (!Program.Probe(53, 3000)) { engine.Stop(); throw new InvalidOperationException("The blocker didn't answer its own test lookup."); }
            bool v6 = engine.Listening6;
            DnsConfig.Apply(v6, true);
            engine.NetworkChanged = delegate { DnsConfig.Apply(v6, false); };
        }

        protected override void OnStop()
        {
            DnsConfig.Restore();
            if (engine != null) engine.Stop();
        }

        // Windows is shutting down: keep the DNS setting, the service starts again at boot.
        protected override void OnShutdown() { if (engine != null) engine.Stop(); }
    }

    static class Program
    {
        public static string Self { get { return Assembly.GetExecutingAssembly().Location; } }

        public static bool IsAdmin()
        {
            using (var id = WindowsIdentity.GetCurrent()) return new WindowsPrincipal(id).IsInRole(WindowsBuiltInRole.Administrator);
        }

        public static int Run(string exe, string args)
        {
            try
            {
                var psi = new ProcessStartInfo(exe, args) { UseShellExecute = false, CreateNoWindow = true };
                using (var p = Process.Start(psi))
                {
                    if (!p.WaitForExit(20000)) { try { p.Kill(); } catch { } return -1; }
                    return p.ExitCode;
                }
            }
            catch (Exception ex) { Log.Write(exe + ": " + ex.Message); return -1; }
        }

        public static bool ServiceInstalled()
        {
            foreach (var s in ServiceController.GetServices()) if (s.ServiceName == Paths.ServiceName) return true;
            return false;
        }

        /// <summary>Asks the blocker for a well-known ad server and checks that the answer is "nowhere".</summary>
        public static bool Probe(int port, int timeoutMs)
        {
            byte[] q = { 0x48, 0x42, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0,
                11, (byte)'d', (byte)'o', (byte)'u', (byte)'b', (byte)'l', (byte)'e', (byte)'c', (byte)'l', (byte)'i', (byte)'c', (byte)'k',
                3, (byte)'n', (byte)'e', (byte)'t', 0, 0, 1, 0, 1 };
            var until = DateTime.UtcNow.AddMilliseconds(timeoutMs);
            while (DateTime.UtcNow < until)
            {
                try
                {
                    using (var s = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp))
                    {
                        s.ReceiveTimeout = 500;
                        s.Connect(IPAddress.Loopback, port);
                        s.Send(q);
                        var r = new byte[512];
                        int n = s.Receive(r);
                        if (n == q.Length + 16 && r[0] == 0x48 && r[n - 1] == 0 && r[n - 2] == 0 && r[n - 3] == 0 && r[n - 4] == 0) return true;
                    }
                }
                catch { }
                Thread.Sleep(200);
            }
            return false;
        }

        // ---------- is this PC ready? ----------

        /// <summary>
        /// Checks, without changing anything and without administrator rights, that the blocker
        /// can work on this PC. Each entry is { "ok" | "warn" | "FAIL", what was checked, detail }.
        /// </summary>
        public static List<string[]> Preflight()
        {
            var r = new List<string[]>();
            var os = Environment.OSVersion.Version;
            r.Add(new[] { os.Major >= 10 ? "ok" : "FAIL", "Windows 10 or 11", "Windows " + os.Major + "." + os.Minor + " build " + os.Build });

            bool ours = false;
            try
            {
                if (ServiceInstalled())
                    using (var sc = new ServiceController(Paths.ServiceName)) ours = sc.Status == ServiceControllerStatus.Running;
            }
            catch { }
            if (ours) r.Add(new[] { "ok", "Port 53 on this PC", "already used by Hib Remover Ads itself" });
            else
            {
                string busy = TryBind(IPAddress.Loopback);
                r.Add(busy == null ? new[] { "ok", "Port 53 on this PC is free", "" }
                    : new[] { "FAIL", "Port 53 on this PC is free", "It is used by " + PortOwner() + ". Close or remove that program first, then run this again." });
                busy = TryBind(IPAddress.IPv6Loopback);
                r.Add(new[] { busy == null ? "ok" : "warn", "IPv6 on this PC", busy == null ? "" : "not available; IPv4 only" });
            }

            try { ServicePointManager.SecurityProtocol = (SecurityProtocolType)(3072 | 12288); }
            catch { ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072; }
            ServicePointManager.Expect100Continue = false;
            byte[] q = { 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 7, (byte)'e', (byte)'x', (byte)'a', (byte)'m', (byte)'p', (byte)'l', (byte)'e',
                3, (byte)'c', (byte)'o', (byte)'m', 0, 0, 1, 0, 1 };
            string via = null;
            var watch = Stopwatch.StartNew();
            foreach (string url in Engine.Doh)
            {
                bool reached;
                if (Engine.AskHttps(url, q, q.Length, 3000, out reached) != null) { via = new Uri(url).Host; break; }
            }
            r.Add(via != null ? new[] { "ok", "Encrypted lookups reach the internet", "through " + via + " in " + watch.ElapsedMilliseconds + " ms" }
                : new[] { "warn", "Encrypted lookups reach the internet", "blocked on this network; lookups will use the network's own DNS server instead" });

            int adapters = DnsConfig.Describe().Count;
            r.Add(adapters > 0 ? new[] { "ok", "Network connection found", adapters + " connected adapter(s)" }
                : new[] { "warn", "Network connection found", "none right now; blocking starts when you connect" });
            return r;
        }

        static string TryBind(IPAddress address)
        {
            try
            {
                using (var s = new Socket(address.AddressFamily, SocketType.Dgram, ProtocolType.Udp)) s.Bind(new IPEndPoint(address, 53));
                var l = new TcpListener(address, 53);
                l.Start(); l.Stop();
                return null;
            }
            catch (Exception ex) { return ex.Message; }
        }

        // Names the program that holds port 53, so the message can say what to close.
        static string PortOwner()
        {
            try
            {
                var psi = new ProcessStartInfo("netstat.exe", "-ano") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true };
                using (var p = Process.Start(psi))
                {
                    string text = p.StandardOutput.ReadToEnd();
                    foreach (string line in text.Split('\n'))
                    {
                        var parts = line.Split(new[] { ' ', '\t', '\r' }, StringSplitOptions.RemoveEmptyEntries);
                        if (parts.Length < 4 || !(parts[1].EndsWith(":53"))) continue;
                        if (!parts[1].StartsWith("0.0.0.0") && !parts[1].StartsWith("127.0.0.1") && !parts[1].StartsWith("[::]") && !parts[1].StartsWith("[::1]")) continue;
                        int pid;
                        if (!int.TryParse(parts[parts.Length - 1], out pid)) continue;
                        try { return "\"" + Process.GetProcessById(pid).ProcessName + "\""; } catch { return "another program (process " + pid + ")"; }
                    }
                }
            }
            catch { }
            return "another program";
        }

        /// <summary>Stops before the administrator prompt if this PC isn't ready, and says why.</summary>
        static bool ReadyOrExplain(bool quiet)
        {
            var problems = new List<string>();
            foreach (var c in Preflight()) if (c[0] == "FAIL") problems.Add(c[1] + ": " + c[2]);
            if (problems.Count == 0) return true;
            Say(quiet, "Hib Remover Ads can't be installed yet. Nothing was changed.\n\n" + string.Join("\n\n", problems.ToArray()), MessageBoxIcon.Warning);
            return false;
        }

        // ---------- install ----------

        static string Install()
        {
            Directory.CreateDirectory(Paths.InstallDir);
            Directory.CreateDirectory(Paths.User);
            if (ServiceInstalled()) StopService();
            KillOthers();
            if (!string.Equals(Self, Paths.InstalledExe, StringComparison.OrdinalIgnoreCase))
            {
                for (int i = 0; ; i++)
                {
                    try { File.Copy(Self, Paths.InstalledExe, true); break; }
                    catch { if (i == 10) throw; Thread.Sleep(300); }
                }
            }
            // Any user of this PC may flip the on/off switch and edit the allow list. Nothing else.
            Run("icacls.exe", "\"" + Paths.User + "\" /grant *S-1-5-32-545:(OI)(CI)M /T /Q");
            // A list downloaded by an older copy would hide the newer one built into this copy.
            foreach (string f in new[] { "block.txt", "allow.txt" }) try { File.Delete(Path.Combine(Paths.Data, f)); } catch { }

            if (!ServiceInstalled())
                Run("sc.exe", "create " + Paths.ServiceName + " binPath= \"\\\"" + Paths.InstalledExe + "\\\" --service\" start= auto DisplayName= \"Hib Remover Ads\"");
            Run("sc.exe", "description " + Paths.ServiceName + " \"Blocks ads and trackers in every app on this PC. If it stops, Windows uses its spare DNS server and the internet keeps working.\"");
            Run("sc.exe", "failure " + Paths.ServiceName + " reset= 3600 actions= restart/1000/restart/1000/restart/10000");
            Run("sc.exe", "start " + Paths.ServiceName);
            if (!Probe(53, 20000))
            {
                StopService();
                Run("sc.exe", "delete " + Paths.ServiceName);
                return "The blocker couldn't start, so nothing was changed. Another program is probably using port 53 "
                    + "(a local DNS server, or Internet Connection Sharing). Details: " + Paths.LogFile;
            }

            using (var k = Registry.LocalMachine.CreateSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"))
                k.SetValue(Paths.Product, "\"" + Paths.InstalledExe + "\" --tray");
            using (var k = Registry.LocalMachine.CreateSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\" + Paths.ServiceName))
            {
                k.SetValue("DisplayName", "Hib Remover Ads for Windows");
                k.SetValue("DisplayVersion", Assembly.GetExecutingAssembly().GetName().Version.ToString(3));
                k.SetValue("Publisher", "Zakaria Hibaoui");
                k.SetValue("DisplayIcon", Paths.InstalledExe);
                k.SetValue("UninstallString", "\"" + Paths.InstalledExe + "\" --uninstall");
                k.SetValue("URLInfoAbout", Paths.Repo);
                k.SetValue("InstallLocation", Paths.InstallDir);
                k.SetValue("NoModify", 1, RegistryValueKind.DWord);
                k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                k.SetValue("EstimatedSize", (int)(new FileInfo(Paths.InstalledExe).Length / 1024), RegistryValueKind.DWord);
            }
            try
            {
                var shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
                var link = shell.GetType().InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { ShortcutPath() });
                link.GetType().InvokeMember("TargetPath", BindingFlags.SetProperty, null, link, new object[] { Paths.InstalledExe });
                link.GetType().InvokeMember("Description", BindingFlags.SetProperty, null, link, new object[] { "Blocks ads in every Windows app" });
                link.GetType().InvokeMember("Save", BindingFlags.InvokeMethod, null, link, null);
            }
            catch (Exception ex) { Log.Write("Shortcut: " + ex.Message); }
            return null;
        }

        static string ShortcutPath()
        {
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonPrograms), "Hib Remover Ads.lnk");
        }

        static void StopService()
        {
            try
            {
                using (var sc = new ServiceController(Paths.ServiceName))
                {
                    if (sc.Status != ServiceControllerStatus.Stopped && sc.Status != ServiceControllerStatus.StopPending) sc.Stop();
                    sc.WaitForStatus(ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(30));
                }
            }
            catch { }
        }

        static void KillOthers()
        {
            int me = Process.GetCurrentProcess().Id;
            foreach (var p in Process.GetProcessesByName("HibRemoverAds"))
            {
                try
                {
                    if (p.Id != me && p.SessionId != 0) { p.Kill(); p.WaitForExit(3000); }
                }
                catch { }
            }
        }

        static void Uninstall()
        {
            StopService();              // the service puts the DNS setting back as it stops
            DnsConfig.Restore();        // and again here, in case the service wasn't running
            Run("sc.exe", "delete " + Paths.ServiceName);
            KillOthers();
            try { using (var k = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", true)) k.DeleteValue(Paths.Product, false); } catch { }
            try { Registry.LocalMachine.DeleteSubKeyTree(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\" + Paths.ServiceName, false); } catch { }
            try { File.Delete(ShortcutPath()); } catch { }
            try { Directory.Delete(Paths.Data, true); } catch { }
            // This program can't delete its own file while it runs; a helper does it two seconds later.
            try
            {
                Process.Start(new ProcessStartInfo("cmd.exe", "/c ping -n 3 127.0.0.1 >nul & rmdir /s /q \"" + Paths.InstallDir + "\"")
                    { UseShellExecute = false, CreateNoWindow = true });
            }
            catch { }
        }

        static bool Elevate(string args)
        {
            try
            {
                using (var p = Process.Start(new ProcessStartInfo(Self, args) { UseShellExecute = true, Verb = "runas" }))
                {
                    p.WaitForExit();
                    return p.ExitCode == 0;
                }
            }
            catch { return false; }   // the administrator prompt was declined
        }

        static void Say(bool quiet, string text, MessageBoxIcon icon)
        {
            if (!quiet) MessageBox.Show(text, "Hib Remover Ads", MessageBoxButtons.OK, icon);
        }

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        static extern bool SetProcessDPIAware();

        [STAThread]
        static int Main(string[] args)
        {
            var a = new List<string>(args);
            bool quiet = a.Contains("--quiet");

            if (a.Contains("--service")) { ServiceBase.Run(new Service()); return 0; }

            // Test mode: python tests/test_windows.py. Runs the blocker on a spare port
            // without touching any Windows setting. Stops when its parent closes the pipe.
            if (a.Contains("--run"))
            {
                var engine = new Engine { Port = 5353 };
                int i = a.IndexOf("--port");
                if (i >= 0) engine.Port = int.Parse(a[i + 1]);
                i = a.IndexOf("--data");
                if (i >= 0) Paths.Data = Path.GetFullPath(a[i + 1]);
                Directory.CreateDirectory(Paths.User);
                try { engine.Start(); }
                catch (Exception ex)
                {
                    File.WriteAllText(Path.Combine(Paths.Data, "failed"), ex.Message);
                    return 2;
                }
                File.WriteAllText(Path.Combine(Paths.Data, "ready"), "1");
                i = a.IndexOf("--seconds");
                Thread.Sleep(i >= 0 ? int.Parse(a[i + 1]) * 1000 : Timeout.Infinite);
                engine.Stop();
                return 0;
            }

            try { SetProcessDPIAware(); } catch { }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            if (a.Contains("--install"))
            {
                if (!IsAdmin())
                {
                    if (!ReadyOrExplain(quiet)) return 1;
                    return Elevate("--install" + (quiet ? " --quiet" : "") + (a.Contains("--no-open") ? " --no-open" : "")) ? 0 : 1;
                }
                string error;
                try { error = Install(); } catch (Exception ex) { error = "Install failed: " + ex.Message; }
                if (error != null) { Log.Write(error); Say(quiet, error, MessageBoxIcon.Error); return 1; }
                // Open the window as the normal user, not as administrator.
                if (!a.Contains("--no-open")) try { Process.Start("explorer.exe", "\"" + Paths.InstalledExe + "\""); } catch { }
                return 0;
            }

            if (a.Contains("--uninstall"))
            {
                if (!quiet && !a.Contains("--confirmed") && MessageBox.Show(
                    "Remove Hib Remover Ads for Windows?\n\nYour network settings go back to exactly what they were before. The browser extension is not affected.",
                    "Hib Remover Ads", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK) return 1;
                if (!IsAdmin()) return Elevate("--uninstall --confirmed" + (quiet ? " --quiet" : "")) ? 0 : 1;
                try { Uninstall(); } catch (Exception ex) { Say(quiet, "Uninstall failed: " + ex.Message, MessageBoxIcon.Error); return 1; }
                Say(quiet, "Hib Remover Ads for Windows was removed. Your network settings are back as they were.", MessageBoxIcon.Information);
                return 0;
            }

            // For the README picture and the tests: draws the window from a folder of counters
            // (--data), without the service, the tray icon or any change to this PC.
            int at = a.IndexOf("--screenshot");
            if (at >= 0)
            {
                int d = a.IndexOf("--data");
                if (d >= 0) Paths.Data = Path.GetFullPath(a[d + 1]);
                Tray.Screenshot(a[at + 1]);
                return 0;
            }
            if (a.Contains("--test-extras")) return ExtrasTest.Run();

            // "Is this PC ready?" Changes nothing, needs no administrator rights.
            if (a.Contains("--check"))
            {
                bool ready = true;
                foreach (var c in Preflight())
                {
                    Console.WriteLine(c[0] + "\t" + c[1] + "\t" + c[2]);
                    if (c[0] == "FAIL") ready = false;
                }
                return ready ? 0 : 1;
            }

            // Prints what install and uninstall would do to the DNS setting of this PC, and does none of it.
            if (a.Contains("--plan-dns"))
            {
                DnsConfig.DryRun = true;
                foreach (string line in DnsConfig.Describe()) Console.WriteLine("adapter\t" + line);
                DnsConfig.Apply(true, true);
                foreach (string line in DnsConfig.Planned) Console.WriteLine("install\t" + line);
                DnsConfig.Planned.Clear();
                DnsConfig.Restore();
                foreach (string line in DnsConfig.Planned) Console.WriteLine("uninstall\t" + line);
                return 0;
            }

            if (!ServiceInstalled())
            {
                if (!ReadyOrExplain(false)) return 1;
                if (MessageBox.Show(
                    "Block ads and trackers in every app on this PC?\n\n"
                    + "Hib Remover Ads will answer this PC's server lookups (DNS) and refuse the ones for ad servers. "
                    + "It works in Spotify, free games, Windows itself and every browser.\n\n"
                    + "It needs administrator permission once. You can remove it any time from Settings > Apps, and your network settings go back as they were.",
                    "Hib Remover Ads", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK) return 1;
                return Elevate("--install") ? 0 : 1;
            }

            return Tray.RunApp(a.Contains("--tray"));
        }
    }
}

// Hib Remover Ads for Windows: the blocking engine.
//
// A small DNS server that listens on this PC only (127.0.0.1 and ::1). Every
// program asks it where a server is before connecting. Ad and tracker servers
// get the answer "nowhere" (0.0.0.0), so the ad never downloads. Every other
// lookup is passed on over HTTPS and remembered, so repeat lookups are instant.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using Microsoft.Win32;

namespace Hib
{
    static class Paths
    {
        public const string Product = "Hib Remover Ads";
        public const string ServiceName = "HibRemoverAds";
        public const string Repo = "https://github.com/ZakariaHibaoui2/hib-remover-ads";
        public const string ListUrl = "https://raw.githubusercontent.com/ZakariaHibaoui2/hib-remover-ads/main/windows/lists/";

        // Written by the service (administrators only). Everyone can read it.
        public static string Data = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), Product);
        // Written by the tray app of any user: the on/off switch and the allow list.
        public static string User { get { return Path.Combine(Data, "user"); } }
        public static string Settings { get { return Path.Combine(User, "settings.txt"); } }
        public static string UserAllow { get { return Path.Combine(User, "allow.txt"); } }
        public static string Stats { get { return Path.Combine(Data, "stats.txt"); } }
        public static string Counters { get { return Path.Combine(Data, "counters.txt"); } }
        public static string LogFile { get { return Path.Combine(Data, "log.txt"); } }
        public static string InstallDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), Product);
        public static string InstalledExe { get { return Path.Combine(InstallDir, "HibRemoverAds.exe"); } }
    }

    static class Log
    {
        static readonly object gate = new object();
        // Errors and start/stop only. Never the names of the sites or servers you visit.
        public static void Write(string text)
        {
            string line = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + text;
            try
            {
                lock (gate)
                {
                    var f = new FileInfo(Paths.LogFile);
                    if (f.Exists && f.Length > 200000) f.Delete();
                    File.AppendAllText(Paths.LogFile, line + "\r\n");
                }
            }
            catch { }
        }
    }

    /// <summary>The set of blocked and allowed domains, stored as 64-bit hashes to stay small.</summary>
    class DomainSet
    {
        HashSet<ulong> items = new HashSet<ulong>();
        public int Count { get { return items.Count; } }

        public static ulong Hash(string s, int start)
        {
            ulong h = 14695981039346656037UL;
            for (int i = start; i < s.Length; i++) { h ^= s[i]; h *= 1099511628211UL; }
            return h;
        }

        public void Load(TextReader reader)
        {
            var set = new HashSet<ulong>();
            string line;
            while ((line = reader.ReadLine()) != null)
            {
                line = line.Trim().ToLowerInvariant();
                if (line.Length < 3 || line[0] == '#' || line.IndexOf('.') < 0) continue;
                set.Add(Hash(line, 0));
            }
            items = set;
        }

        public bool Has(string name, int start) { return items.Contains(Hash(name, start)); }
    }

    class CacheEntry
    {
        public byte[] Data;        // the answer, with message id 0
        public int[] TtlOffsets;   // where each record's time-to-live sits
        public long Stored;        // Engine.Now() when stored
        public int Ttl;            // seconds the answer stays fresh
        public int Refreshing;     // 1 while a background refresh is running
    }

    class Engine
    {
        public int Port = 53;
        public bool IsService;
        public bool Listening6;

        readonly DomainSet block = new DomainSet();
        readonly DomainSet allow = new DomainSet();
        volatile DomainSet userAllow = new DomainSet();
        volatile bool enabled = true;
        long pauseUntil;                       // UTC ticks; blocking is paused before this time
        DateTime settingsStamp, allowStamp;

        readonly Dictionary<string, CacheEntry> cache = new Dictionary<string, CacheEntry>(4096);
        readonly Stopwatch clock = Stopwatch.StartNew();
        readonly List<Socket> udp = new List<Socket>();
        readonly List<TcpListener> tcp = new List<TcpListener>();
        volatile bool running;

        // Counters shown in the tray window.
        long queries, blocked, cacheHits, upstreamCount, upstreamMs, total, today;
        string day = DateTime.Now.ToString("yyyy-MM-dd");
        readonly Dictionary<string, int> topBlocked = new Dictionary<string, int>();
        long lastStatsQueries = -1;

        // Where lookups are passed on. Addresses, not names, so no lookup is needed to reach them.
        static readonly string[] Doh = {
            "https://1.1.1.1/dns-query", "https://1.0.0.1/dns-query", "https://9.9.9.9/dns-query" };
        int dohIndex;
        long dohDownUntil;
        long lastClientQuery;
        volatile IPAddress[] systemDns = new IPAddress[0];
        volatile string[] localSuffixes = new string[0];

        long Now() { return clock.ElapsedMilliseconds; }

        bool Active
        {
            get { return enabled && DateTime.UtcNow.Ticks >= Interlocked.Read(ref pauseUntil); }
        }

        // ---------- start and stop ----------

        public void Start()
        {
            ServicePointManager.DefaultConnectionLimit = 16;
            ServicePointManager.Expect100Continue = false;
            ServicePointManager.UseNagleAlgorithm = false;
            ServicePointManager.MaxServicePointIdleTime = 300000;
            try { ServicePointManager.SecurityProtocol = (SecurityProtocolType)(3072 | 12288); }
            catch { ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072; }
            ThreadPool.SetMinThreads(32, 32);

            Directory.CreateDirectory(Paths.Data);
            LoadLists();
            LoadCounters();
            ReadSettings(true);
            RefreshNetwork();

            Bind(IPAddress.Loopback);   // throws if port 53 is taken, before anything is changed
            try { Bind(IPAddress.IPv6Loopback); Listening6 = true; }
            catch (Exception ex) { Log.Write("IPv6 not available: " + ex.Message); }
            running = true;
            foreach (var s in udp) { var sock = s; StartThread(delegate { UdpLoop(sock); }, "udp"); }
            foreach (var l in tcp) { var lis = l; StartThread(delegate { TcpLoop(lis); }, "tcp"); }
            StartThread(Housekeeping, "housekeeping");
            NetworkChange.NetworkAddressChanged += delegate { ThreadPool.QueueUserWorkItem(delegate { RefreshNetwork(); OnNetworkChanged(); }); };
            Log.Write("Started on port " + Port + ", " + block.Count + " blocked domains.");
            // Open the first connection now so the first real lookup doesn't wait for it.
            ThreadPool.QueueUserWorkItem(delegate { Warm(); });
        }

        public Action NetworkChanged;
        void OnNetworkChanged() { var h = NetworkChanged; if (h != null) try { h(); } catch { } }

        public void Stop()
        {
            running = false;
            foreach (var s in udp) try { s.Close(); } catch { }
            foreach (var l in tcp) try { l.Stop(); } catch { }
            SaveCounters();
            WriteStats(true);
            Log.Write("Stopped.");
        }

        static void StartThread(ThreadStart body, string name)
        {
            var t = new Thread(body) { IsBackground = true, Name = name };
            t.Start();
        }

        void Bind(IPAddress address)
        {
            var s = new Socket(address.AddressFamily, SocketType.Dgram, ProtocolType.Udp);
            // Without this, Windows reports a closed client port as an error on our socket.
            try { s.IOControl(-1744830452, new byte[] { 0, 0, 0, 0 }, null); } catch { }
            s.ReceiveBufferSize = 1 << 20;
            s.Bind(new IPEndPoint(address, Port));
            udp.Add(s);
            var l = new TcpListener(address, Port);
            l.Start();
            tcp.Add(l);
        }

        // ---------- lists and settings ----------

        void LoadLists()
        {
            LoadList(block, "block.txt");
            LoadList(allow, "allow.txt");
        }

        // A list downloaded by the weekly update wins over the one built into the program.
        static void LoadList(DomainSet set, string name)
        {
            string updated = Path.Combine(Paths.Data, name);
            try
            {
                if (File.Exists(updated) && File.GetLastWriteTimeUtc(updated) > BuildTime())
                {
                    using (var r = new StreamReader(updated)) set.Load(r);
                    if (set.Count > 0) return;
                }
            }
            catch { }
            using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream(name + ".gz"))
            using (var gz = new GZipStream(s, CompressionMode.Decompress))
            using (var r = new StreamReader(gz))
                set.Load(r);
        }

        static DateTime BuildTime()
        {
            try { return File.GetLastWriteTimeUtc(Assembly.GetExecutingAssembly().Location); }
            catch { return DateTime.MinValue; }
        }

        void ReadSettings(bool first)
        {
            try
            {
                var stamp = File.Exists(Paths.Settings) ? File.GetLastWriteTimeUtc(Paths.Settings) : DateTime.MinValue;
                if (first || stamp != settingsStamp)
                {
                    settingsStamp = stamp;
                    bool was = Active;
                    bool on = true; long pause = 0;
                    if (File.Exists(Paths.Settings))
                    {
                        foreach (var line in File.ReadAllLines(Paths.Settings))
                        {
                            int eq = line.IndexOf('=');
                            if (eq < 0) continue;
                            string k = line.Substring(0, eq).Trim(), v = line.Substring(eq + 1).Trim();
                            if (k == "enabled") on = v != "0";
                            else if (k == "pause_until") long.TryParse(v, out pause);
                        }
                    }
                    enabled = on;
                    Interlocked.Exchange(ref pauseUntil, pause);
                    if (!first && was != Active) FlushWindowsCache();
                }
                stamp = File.Exists(Paths.UserAllow) ? File.GetLastWriteTimeUtc(Paths.UserAllow) : DateTime.MinValue;
                if (first || stamp != allowStamp)
                {
                    allowStamp = stamp;
                    var set = new DomainSet();
                    if (File.Exists(Paths.UserAllow))
                        using (var r = new StreamReader(Paths.UserAllow)) set.Load(r);
                    userAllow = set;
                    if (!first) FlushWindowsCache();
                }
            }
            catch (Exception ex) { Log.Write("Settings: " + ex.Message); }
        }

        [DllImport("dnsapi.dll", EntryPoint = "DnsFlushResolverCache")]
        static extern uint DnsFlushResolverCache();

        // Windows remembers answers too. Forget them when blocking is switched, so the switch is immediate.
        void FlushWindowsCache()
        {
            lock (cache) cache.Clear();
            if (IsService) try { DnsFlushResolverCache(); } catch { }
        }

        /// <summary>The most specific rule wins: a name you allowed, then the allow list, then the block list.</summary>
        public bool IsBlocked(string name)
        {
            var mine = userAllow;
            if (mine.Count > 0)
                for (int i = 0; i >= 0 && i < name.Length; i = Next(name, i))
                    if (mine.Has(name, i)) return false;
            for (int i = 0; i >= 0 && i < name.Length; i = Next(name, i))
            {
                if (allow.Has(name, i)) return false;
                if (block.Has(name, i)) return true;
            }
            return false;
        }

        static int Next(string name, int i)
        {
            int dot = name.IndexOf('.', i);
            return dot < 0 ? -1 : dot + 1;
        }

        // ---------- the network this PC is on ----------

        /// <summary>The DNS servers the network handed out. Used for local names and when HTTPS lookups can't get out.</summary>
        void RefreshNetwork()
        {
            var servers = new List<IPAddress>();
            var suffixes = new List<string>();
            try
            {
                foreach (var nic in NetworkInterface.GetAllNetworkInterfaces())
                {
                    if (nic.OperationalStatus != OperationalStatus.Up || nic.NetworkInterfaceType == NetworkInterfaceType.Loopback) continue;
                    var props = nic.GetIPProperties();
                    if (!string.IsNullOrEmpty(props.DnsSuffix)) suffixes.Add("." + props.DnsSuffix.ToLowerInvariant());
                    foreach (var a in props.DnsAddresses) AddServer(servers, a);
                    // Once this PC points at us, the network's own servers are only in the registry.
                    foreach (string key in new[] { "Tcpip", "Tcpip6" })
                    {
                        using (var k = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\" + key + @"\Parameters\Interfaces\" + nic.Id))
                        {
                            if (k == null) continue;
                            foreach (string part in ((k.GetValue("DhcpNameServer") as string) ?? "").Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries))
                            {
                                IPAddress a;
                                if (IPAddress.TryParse(part, out a)) AddServer(servers, a);
                            }
                        }
                    }
                }
            }
            catch (Exception ex) { Log.Write("Network: " + ex.Message); }
            systemDns = servers.ToArray();
            localSuffixes = suffixes.ToArray();
        }

        static void AddServer(List<IPAddress> list, IPAddress a)
        {
            if (IPAddress.IsLoopback(a) || a.IsIPv6SiteLocal || a.ToString() == "1.1.1.1" || a.ToString().StartsWith("2606:4700:4700")) return;
            if (!list.Contains(a)) list.Add(a);
        }

        // Names that only the local network knows: printers, routers, company servers.
        bool IsLocalName(string name)
        {
            if (name.IndexOf('.') < 0) return true;
            if (name.EndsWith(".local") || name.EndsWith(".lan") || name.EndsWith(".home") || name.EndsWith(".internal")
                || name.EndsWith(".corp") || name.EndsWith(".home.arpa") || name.EndsWith(".localdomain")) return true;
            if (name.EndsWith(".in-addr.arpa"))
                return name.EndsWith(".10.in-addr.arpa") || name.EndsWith(".168.192.in-addr.arpa")
                    || name.EndsWith(".254.169.in-addr.arpa") || name.Contains(".172.in-addr.arpa");
            foreach (var s in localSuffixes) if (name.EndsWith(s)) return true;
            return false;
        }

        // ---------- listening ----------

        void UdpLoop(Socket s)
        {
            var buf = new byte[4096];
            EndPoint any = s.AddressFamily == AddressFamily.InterNetwork
                ? new IPEndPoint(IPAddress.Any, 0) : new IPEndPoint(IPAddress.IPv6Any, 0);
            while (running)
            {
                try
                {
                    EndPoint from = any;
                    int n = s.ReceiveFrom(buf, ref from);
                    // Blocked names and remembered answers are sent back right here, with no waiting.
                    byte[] quick = Answer(buf, n, false, true);
                    if (quick != null) { s.SendTo(quick, from); continue; }
                    var q = new byte[n];
                    Buffer.BlockCopy(buf, 0, q, 0, n);
                    ThreadPool.QueueUserWorkItem(delegate
                    {
                        try
                        {
                            byte[] r = Answer(q, q.Length, false, false);
                            if (r != null) s.SendTo(r, from);
                        }
                        catch { }
                    });
                }
                catch (ObjectDisposedException) { return; }
                catch (SocketException) { if (!running) return; }
                catch (Exception ex) { Log.Write("UDP: " + ex.Message); }
            }
        }

        void TcpLoop(TcpListener l)
        {
            while (running)
            {
                try
                {
                    var client = l.AcceptTcpClient();
                    ThreadPool.QueueUserWorkItem(delegate { ServeTcp(client); });
                }
                catch { if (!running) return; }
            }
        }

        void ServeTcp(TcpClient client)
        {
            try
            {
                using (client)
                {
                    client.ReceiveTimeout = 5000; client.SendTimeout = 5000; client.NoDelay = true;
                    var stream = client.GetStream();
                    var head = new byte[2];
                    while (ReadFull(stream, head, 2))
                    {
                        int len = (head[0] << 8) | head[1];
                        var q = new byte[len];
                        if (len < 12 || !ReadFull(stream, q, len)) return;
                        byte[] r = Answer(q, len, true, false);
                        if (r == null) return;
                        var o = new byte[r.Length + 2];
                        o[0] = (byte)(r.Length >> 8); o[1] = (byte)r.Length;
                        Buffer.BlockCopy(r, 0, o, 2, r.Length);
                        stream.Write(o, 0, o.Length);
                    }
                }
            }
            catch { }
        }

        static bool ReadFull(Stream s, byte[] b, int n)
        {
            int got = 0;
            while (got < n)
            {
                int r = s.Read(b, got, n - got);
                if (r <= 0) return false;
                got += r;
            }
            return true;
        }

        // ---------- answering one lookup ----------

        /// <summary>
        /// Returns the answer for one lookup. With quickOnly, returns null when the answer
        /// isn't already known, so the caller can finish it on another thread.
        /// </summary>
        byte[] Answer(byte[] q, int len, bool overTcp, bool quickOnly)
        {
            if (len < 12 || (q[2] & 0x80) != 0) return null;
            int qd = (q[4] << 8) | q[5];
            string name = null; int qEnd = 12, qtype = 0, qclass = 0;
            if (qd == 1 && ReadName(q, len, out name, out qEnd) && qEnd + 4 <= len)
            {
                qtype = (q[qEnd] << 8) | q[qEnd + 1];
                qclass = (q[qEnd + 2] << 8) | q[qEnd + 3];
                qEnd += 4;
            }
            else name = null;

            // Not a lookup we can read (damaged, or more than one question): refuse it rather than pass it on.
            if (name == null) return Refuse(q, len);

            if (quickOnly)
            {
                Interlocked.Increment(ref queries);
                Interlocked.Exchange(ref lastClientQuery, Now());
            }
            if (Active && qclass == 1 && IsBlocked(name))
            {
                CountBlocked(name);
                return Blocked(q, qEnd, qtype);
            }

            int maxUdp = 512; bool dnssec = false;
            ReadEdns(q, len, qEnd, ref maxUdp, ref dnssec);
            string key = name + "|" + qtype + "|" + qclass + (dnssec ? "|d" : "");
            byte[] answer = FromCache(key, q, len, qEnd);
            if (answer != null) Interlocked.Increment(ref cacheHits);
            else
            {
                if (quickOnly) return null;
                long t0 = Now();
                byte[] fresh = Resolve(q, len, name);
                if (fresh == null) return Fail(q, len, qEnd);
                Interlocked.Increment(ref upstreamCount);
                Interlocked.Add(ref upstreamMs, Now() - t0);
                Store(key, fresh);
                answer = Finish(fresh, q, qEnd, -1);
            }
            if (!overTcp && answer.Length > maxUdp) return Truncated(q, qEnd);
            return answer;
        }

        static bool ReadName(byte[] q, int len, out string name, out int end)
        {
            var sb = new StringBuilder(64);
            int p = 12; name = null; end = 0;
            while (true)
            {
                if (p >= len) return false;
                int l = q[p++];
                if (l == 0) break;
                if (l > 63 || p + l > len) return false;
                if (sb.Length > 0) sb.Append('.');
                for (int i = 0; i < l; i++)
                {
                    char c = (char)q[p + i];
                    if (c >= 'A' && c <= 'Z') c = (char)(c + 32);
                    sb.Append(c);
                }
                p += l;
            }
            name = sb.ToString(); end = p;
            return true;
        }

        // Reads how big an answer the program accepts, and whether it asked for signatures.
        static void ReadEdns(byte[] q, int len, int p, ref int maxUdp, ref bool dnssec)
        {
            int extra = (q[10] << 8) | q[11];
            if (((q[6] << 8) | q[7]) != 0 || ((q[8] << 8) | q[9]) != 0) return;
            for (int i = 0; i < extra && p < len; i++)
            {
                while (p < len && q[p] != 0) { if ((q[p] & 0xC0) == 0xC0) { p++; break; } p += q[p] + 1; }
                p++;
                if (p + 10 > len) return;
                int type = (q[p] << 8) | q[p + 1];
                if (type == 41)
                {
                    maxUdp = Math.Max(512, Math.Min(4096, (q[p + 2] << 8) | q[p + 3]));
                    dnssec = (q[p + 6] & 0x80) != 0;
                    return;
                }
                p += 10 + ((q[p + 8] << 8) | q[p + 9]);
            }
        }

        /// <summary>"Nowhere": 0.0.0.0 for an address lookup, an empty answer for anything else.</summary>
        static byte[] Blocked(byte[] q, int qEnd, int qtype)
        {
            int rd = qtype == 1 ? 4 : qtype == 28 ? 16 : 0;
            var r = new byte[qEnd + (rd > 0 ? 12 + rd : 0)];
            Buffer.BlockCopy(q, 0, r, 0, qEnd);
            r[2] = (byte)(0x80 | (q[2] & 0x79)); r[3] = 0x80;
            r[6] = 0; r[7] = (byte)(rd > 0 ? 1 : 0);
            r[8] = r[9] = r[10] = r[11] = 0;
            if (rd > 0)
            {
                int p = qEnd;
                r[p] = 0xC0; r[p + 1] = 0x0C;
                r[p + 2] = (byte)(qtype >> 8); r[p + 3] = (byte)qtype;
                r[p + 5] = 1;
                r[p + 9] = 60;                 // remembered by Windows for one minute
                r[p + 11] = (byte)rd;
            }
            return r;
        }

        static byte[] Fail(byte[] q, int len, int qEnd)
        {
            var r = new byte[qEnd];
            Buffer.BlockCopy(q, 0, r, 0, qEnd);
            r[2] = (byte)(0x80 | (q[2] & 0x79)); r[3] = 0x82;   // "server failure": Windows tries its next server
            r[6] = r[7] = r[8] = r[9] = r[10] = r[11] = 0;
            if (qEnd == len && ((q[4] << 8) | q[5]) != 1) { r[4] = q[4]; r[5] = q[5]; }
            return r;
        }

        // Too big for this program's buffer: tell it to ask again over TCP.
        static byte[] Truncated(byte[] q, int qEnd)
        {
            var r = new byte[qEnd];
            Buffer.BlockCopy(q, 0, r, 0, qEnd);
            r[2] = (byte)(0x82 | (q[2] & 0x79)); r[3] = 0x80;
            r[6] = r[7] = r[8] = r[9] = r[10] = r[11] = 0;
            return r;
        }

        static byte[] Refuse(byte[] q, int len)
        {
            var r = new byte[12];
            r[0] = q[0]; r[1] = q[1];
            r[2] = (byte)(0x80 | (q[2] & 0x79)); r[3] = 0x81;   // "format error"
            return r;
        }

        // ---------- remembering answers ----------

        /// <summary>Copies a stored answer for this program: its message id, its spelling of the name, and the time left.</summary>
        static byte[] Finish(byte[] stored, byte[] q, int qEnd, int ttl)
        {
            var r = new byte[stored.Length];
            Buffer.BlockCopy(stored, 0, r, 0, stored.Length);
            r[0] = q[0]; r[1] = q[1];
            if (stored.Length >= qEnd) Buffer.BlockCopy(q, 12, r, 12, qEnd - 12);
            return r;
        }

        byte[] FromCache(string key, byte[] q, int len, int qEnd)
        {
            CacheEntry e;
            lock (cache) if (!cache.TryGetValue(key, out e)) return null;
            long age = (Now() - e.Stored) / 1000;
            byte[] r = Finish(e.Data, q, qEnd, 0);
            if (age < e.Ttl)
            {
                foreach (int o in e.TtlOffsets)
                {
                    long left = Math.Max(1, ReadTtl(r, o) - age);
                    WriteTtl(r, o, (uint)left);
                }
                return r;
            }
            // Out of date but recent: answer now with the old address and look it up again
            // in the background, so nothing waits. Addresses rarely change that fast.
            if (age > e.Ttl + 6 * 3600) { lock (cache) cache.Remove(key); return null; }
            foreach (int o in e.TtlOffsets) WriteTtl(r, o, 30);
            if (Interlocked.Exchange(ref e.Refreshing, 1) == 0)
            {
                var copy = new byte[len];
                Buffer.BlockCopy(q, 0, copy, 0, len);
                string name = key.Substring(0, key.IndexOf('|'));
                ThreadPool.QueueUserWorkItem(delegate
                {
                    byte[] fresh = Resolve(copy, copy.Length, name);
                    if (fresh != null) Store(key, fresh); else e.Refreshing = 0;
                });
            }
            return r;
        }

        static long ReadTtl(byte[] b, int o) { return ((long)b[o] << 24) | ((long)b[o + 1] << 16) | ((long)b[o + 2] << 8) | b[o + 3]; }
        static void WriteTtl(byte[] b, int o, uint v) { b[o] = (byte)(v >> 24); b[o + 1] = (byte)(v >> 16); b[o + 2] = (byte)(v >> 8); b[o + 3] = (byte)v; }

        void Store(string key, byte[] r)
        {
            int rcode = r[3] & 0x0F;
            if (rcode != 0 && rcode != 3) return;      // only real answers and "no such name"
            var offsets = new List<int>();
            long min = long.MaxValue;
            try
            {
                int p = 12;
                int qd = (r[4] << 8) | r[5];
                int records = ((r[6] << 8) | r[7]) + ((r[8] << 8) | r[9]) + ((r[10] << 8) | r[11]);
                for (int i = 0; i < qd; i++) p = SkipName(r, p) + 4;
                for (int i = 0; i < records; i++)
                {
                    p = SkipName(r, p);
                    int type = (r[p] << 8) | r[p + 1];
                    if (type != 41) { offsets.Add(p + 4); min = Math.Min(min, ReadTtl(r, p + 4)); }
                    p += 10 + ((r[p + 8] << 8) | r[p + 9]);
                }
                if (p != r.Length) return;
            }
            catch { return; }
            var e = new CacheEntry { Data = (byte[])r.Clone(), TtlOffsets = offsets.ToArray(), Stored = Now() };
            e.Data[0] = e.Data[1] = 0;
            e.Ttl = (int)Math.Max(rcode == 3 ? 30 : 20, Math.Min(3600, min == long.MaxValue ? 30 : min));
            lock (cache)
            {
                if (cache.Count > 20000) cache.Clear();
                cache[key] = e;
            }
        }

        static int SkipName(byte[] b, int p)
        {
            while (true)
            {
                int l = b[p];
                if (l == 0) return p + 1;
                if ((l & 0xC0) == 0xC0) return p + 2;
                p += l + 1;
            }
        }

        // ---------- passing a lookup on ----------

        byte[] Resolve(byte[] q, int len, string name)
        {
            var servers = systemDns;
            if (name.Length > 0 && IsLocalName(name))
            {
                byte[] local = AskUdp(q, len, servers, 1500);
                if (local != null) return local;
            }
            byte[] r = null;
            if (Now() >= Interlocked.Read(ref dohDownUntil))
            {
                bool reached = false;
                for (int i = 0; i < Doh.Length && r == null && !reached; i++)
                {
                    int idx = (dohIndex + i) % Doh.Length;
                    r = AskHttps(Doh[idx], q, len, i == 0 ? 2500 : 1500, out reached);
                    if (r != null) dohIndex = idx;
                }
                // The server answered but refused this one lookup: that's about the lookup, not the connection.
                if (r == null && reached) return null;
                // Encrypted lookups can't get out (hotel or airport sign-in page, strict firewall).
                // Use the network's own servers for the next 15 seconds, then try again.
                if (r == null) Interlocked.Exchange(ref dohDownUntil, Now() + 15000);
            }
            if (r == null) return AskUdp(q, len, servers.Length > 0 ? servers : new[] { IPAddress.Parse("1.1.1.1") }, 2000);
            // "No such name" from the internet may still be a name the local network knows.
            if ((r[3] & 0x0F) == 3 && servers.Length > 0 && name.Length > 0 && localSuffixes.Length > 0)
            {
                byte[] local = AskUdp(q, len, servers, 800);
                if (local != null && (local[3] & 0x0F) == 0) return local;
            }
            return r;
        }

        static byte[] AskHttps(string url, byte[] q, int len, int timeout, out bool reached)
        {
            reached = false;
            try
            {
                var req = (HttpWebRequest)WebRequest.Create(url);
                req.Method = "POST";
                req.ContentType = "application/dns-message";
                req.Accept = "application/dns-message";
                req.Proxy = null;
                req.KeepAlive = true;
                req.Timeout = timeout;
                req.ReadWriteTimeout = timeout;
                req.ContentLength = len;
                req.AllowAutoRedirect = false;
                var body = new byte[len];
                Buffer.BlockCopy(q, 0, body, 0, len);
                body[0] = body[1] = 0;          // no message id: nothing to tell one lookup from another
                using (var s = req.GetRequestStream()) s.Write(body, 0, len);
                using (var resp = (HttpWebResponse)req.GetResponse())
                using (var s = resp.GetResponseStream())
                using (var ms = new MemoryStream(512))
                {
                    if (resp.StatusCode != HttpStatusCode.OK) return null;
                    s.CopyTo(ms);
                    var r = ms.ToArray();
                    reached = true;
                    return r.Length >= 12 ? r : null;
                }
            }
            catch (WebException ex)
            {
                reached = ex.Status == WebExceptionStatus.ProtocolError;   // an HTTP error page: the server is there
                return null;
            }
            catch { return null; }
        }

        static byte[] AskUdp(byte[] q, int len, IPAddress[] servers, int timeout)
        {
            foreach (var server in servers)
            {
                try
                {
                    using (var s = new Socket(server.AddressFamily, SocketType.Dgram, ProtocolType.Udp))
                    {
                        s.ReceiveTimeout = timeout;
                        s.Connect(server, 53);
                        s.Send(q, len, SocketFlags.None);
                        var buf = new byte[4096];
                        int n = s.Receive(buf);
                        if (n < 12 || buf[0] != q[0] || buf[1] != q[1]) continue;
                        var r = new byte[n];
                        Buffer.BlockCopy(buf, 0, r, 0, n);
                        return r;
                    }
                }
                catch { }
            }
            return null;
        }

        // A tiny lookup that keeps the encrypted connection open, so real lookups never wait for a new one.
        void Warm()
        {
            byte[] q = { 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 1 };   // root name servers
            bool reached;
            if (Now() >= Interlocked.Read(ref dohDownUntil)) AskHttps(Doh[dohIndex], q, q.Length, 2500, out reached);
        }

        // ---------- counters ----------

        void CountBlocked(string name)
        {
            Interlocked.Increment(ref blocked);
            Interlocked.Increment(ref total);
            Interlocked.Increment(ref today);
            lock (topBlocked)
            {
                int n;
                topBlocked.TryGetValue(name, out n);
                if (n == 0 && topBlocked.Count > 3000) topBlocked.Clear();
                topBlocked[name] = n + 1;
            }
        }

        void LoadCounters()
        {
            try
            {
                foreach (var line in File.ReadAllLines(Paths.Counters))
                {
                    var p = line.Split('=');
                    if (p.Length != 2) continue;
                    if (p[0] == "total") long.TryParse(p[1], out total);
                    else if (p[0] == "day") day = p[1];
                    else if (p[0] == "today") long.TryParse(p[1], out today);
                }
            }
            catch { }
            RollDay();
        }

        void RollDay()
        {
            string now = DateTime.Now.ToString("yyyy-MM-dd");
            if (now != day) { day = now; Interlocked.Exchange(ref today, 0); }
        }

        void SaveCounters()
        {
            try { File.WriteAllText(Paths.Counters, "total=" + Interlocked.Read(ref total) + "\nday=" + day + "\ntoday=" + Interlocked.Read(ref today) + "\n"); }
            catch { }
        }

        /// <summary>What the tray window shows. Blocked ad-server names stay in memory only and are gone at restart.</summary>
        void WriteStats(bool stopping)
        {
            long q = Interlocked.Read(ref queries);
            if (!stopping && q == lastStatsQueries && File.Exists(Paths.Stats)
                && (DateTime.UtcNow - File.GetLastWriteTimeUtc(Paths.Stats)).TotalSeconds < 20) return;
            lastStatsQueries = q;
            var sb = new StringBuilder();
            long up = Interlocked.Read(ref upstreamCount);
            sb.Append("running=").Append(stopping ? 0 : 1).Append('\n');
            sb.Append("active=").Append(Active ? 1 : 0).Append('\n');
            sb.Append("enabled=").Append(enabled ? 1 : 0).Append('\n');
            sb.Append("pause_until=").Append(Interlocked.Read(ref pauseUntil)).Append('\n');
            sb.Append("rules=").Append(block.Count).Append('\n');
            sb.Append("queries=").Append(q).Append('\n');
            sb.Append("blocked=").Append(Interlocked.Read(ref blocked)).Append('\n');
            sb.Append("today=").Append(Interlocked.Read(ref today)).Append('\n');
            sb.Append("total=").Append(Interlocked.Read(ref total)).Append('\n');
            sb.Append("cache_hits=").Append(Interlocked.Read(ref cacheHits)).Append('\n');
            sb.Append("lookup_ms=").Append(up == 0 ? 0 : Interlocked.Read(ref upstreamMs) / up).Append('\n');
            sb.Append("encrypted=").Append(Now() >= Interlocked.Read(ref dohDownUntil) ? 1 : 0).Append('\n');
            var top = new List<KeyValuePair<string, int>>();
            lock (topBlocked) top.AddRange(topBlocked);
            top.Sort(delegate(KeyValuePair<string, int> a, KeyValuePair<string, int> b) { return b.Value.CompareTo(a.Value); });
            for (int i = 0; i < top.Count && i < 40; i++) sb.Append("top=").Append(top[i].Key).Append(' ').Append(top[i].Value).Append('\n');
            try
            {
                string tmp = Paths.Stats + ".tmp";
                File.WriteAllText(tmp, sb.ToString());
                File.Copy(tmp, Paths.Stats, true);
            }
            catch { }
        }

        // ---------- once a second ----------

        void Housekeeping()
        {
            int tick = 0;
            long nextUpdate = Now() + 5 * 60000;
            while (running)
            {
                Thread.Sleep(1000);
                tick++;
                try
                {
                    ReadSettings(false);
                    if (tick % 2 == 0) { RollDay(); WriteStats(false); }
                    if (tick % 60 == 0) SaveCounters();
                    if (tick % 30 == 0) RefreshNetwork();
                    // Keep the encrypted connection warm while programs are looking things up.
                    if (tick % 25 == 0 && Now() - Interlocked.Read(ref lastClientQuery) < 600000) Warm();
                    if (IsService && Now() > nextUpdate)
                    {
                        nextUpdate = Now() + 6 * 3600000;
                        UpdateLists();
                    }
                }
                catch (Exception ex) { Log.Write("Housekeeping: " + ex.Message); }
            }
        }

        /// <summary>
        /// Once a week, downloads the newest block list from this project's GitHub page.
        /// It is a list of names only, never a program, and it is checked before it replaces the old one.
        /// </summary>
        void UpdateLists()
        {
            string target = Path.Combine(Paths.Data, "block.txt");
            DateTime have = File.Exists(target) ? File.GetLastWriteTimeUtc(target) : BuildTime();
            if ((DateTime.UtcNow - have).TotalDays < 7) return;
            try
            {
                foreach (string name in new[] { "allow.txt", "block.txt" })
                {
                    var req = (HttpWebRequest)WebRequest.Create(Paths.ListUrl + name);
                    req.Proxy = null; req.Timeout = 30000; req.ReadWriteTimeout = 30000;
                    req.AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate;
                    req.UserAgent = "hib-remover-ads";
                    string text;
                    using (var resp = req.GetResponse())
                    using (var r = new StreamReader(resp.GetResponseStream(), Encoding.ASCII)) text = r.ReadToEnd();
                    int lines = 0;
                    foreach (char c in text)
                    {
                        if (c == '\n') lines++;
                        else if (!(c >= 'a' && c <= 'z') && !(c >= '0' && c <= '9') && c != '.' && c != '-' && c != '_' && c != '\r')
                            throw new InvalidDataException("unexpected character in " + name);
                    }
                    if (name == "block.txt" && (lines < 50000 || lines > 2000000)) throw new InvalidDataException("block list has " + lines + " lines");
                    File.WriteAllText(Path.Combine(Paths.Data, name + ".new"), text);
                }
                foreach (string name in new[] { "allow.txt", "block.txt" })
                {
                    string final = Path.Combine(Paths.Data, name);
                    if (File.Exists(final)) File.Delete(final);
                    File.Move(final + ".new", final);
                }
                LoadLists();
                lock (cache) cache.Clear();
                Log.Write("Block list updated: " + block.Count + " domains.");
            }
            catch (Exception ex) { Log.Write("List update skipped: " + ex.Message); }
        }
    }
}

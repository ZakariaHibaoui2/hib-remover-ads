// Hib Remover Ads for Windows: the two things blocking ad servers can't do.
//
//   WindowsAds   switches off the ads Windows shows from its own settings.
//   SpotifyMute  mutes Spotify while it plays an audio ad. Spotify sends those
//                from the same servers as the music, so they can't be blocked
//                without stopping the music. Spotify itself is never modified.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using Microsoft.Win32;

namespace Hib
{
    class Tweak
    {
        public string Label;
        public string[] Values;   // "key path|value name", all set to 0 to switch the ad off
        public Tweak(string label, params string[] values) { Label = label; Values = values; }
    }

    /// <summary>Official per-user Windows settings, the same ones behind the switches in the Settings app.</summary>
    static class WindowsAds
    {
        const string Cdm = @"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager|";
        const string Adv = @"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced|";
        const string Backup = @"Software\Hib Remover Ads\Before";

        public static readonly Tweak[] All = {
            new Tweak("Suggested apps and promotions in the Start menu",
                Cdm + "SystemPaneSuggestionsEnabled", Cdm + "SubscribedContent-338388Enabled", Cdm + "SilentInstalledAppsEnabled", Adv + "Start_IrisRecommendations"),
            new Tweak("Ads and tips on the lock screen",
                Cdm + "RotatingLockScreenOverlayEnabled", Cdm + "SubscribedContent-338387Enabled"),
            new Tweak("Promotions inside File Explorer",
                Adv + "ShowSyncProviderNotifications"),
            new Tweak("\"Tips and suggestions\" notifications",
                Cdm + "SubscribedContent-338389Enabled", Cdm + "SoftLandingEnabled", Cdm + "SubscribedContent-310093Enabled",
                @"Software\Microsoft\Windows\CurrentVersion\UserProfileEngagement|ScoobeSystemSettingEnabled"),
            new Tweak("Suggested content in the Settings app",
                Cdm + "SubscribedContent-338393Enabled", Cdm + "SubscribedContent-353694Enabled", Cdm + "SubscribedContent-353696Enabled"),
            new Tweak("Advertising ID and ads based on your activity",
                @"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo|Enabled",
                @"Software\Microsoft\Windows\CurrentVersion\Privacy|TailoredExperiencesWithDiagnosticDataEnabled"),
        };

        public static bool IsOff(Tweak t)
        {
            foreach (string v in t.Values)
            {
                string[] p = v.Split('|');
                using (var k = Registry.CurrentUser.OpenSubKey(p[0]))
                {
                    object cur = k == null ? null : k.GetValue(p[1]);
                    if (!(cur is int) || (int)cur != 0) return false;
                }
            }
            return true;
        }

        /// <summary>Switches one kind of Windows ad off, or puts the setting back as it was.</summary>
        public static void Set(Tweak t, bool off)
        {
            using (var before = Registry.CurrentUser.CreateSubKey(Backup))
            {
                foreach (string v in t.Values)
                {
                    string[] p = v.Split('|');
                    using (var k = Registry.CurrentUser.CreateSubKey(p[0]))
                    {
                        if (off)
                        {
                            object cur = k.GetValue(p[1]);
                            if (before.GetValue(v) == null) before.SetValue(v, cur is int ? cur.ToString() : "none");
                            k.SetValue(p[1], 0, RegistryValueKind.DWord);
                        }
                        else
                        {
                            string old = before.GetValue(v) as string;
                            int n;
                            // Windows treats a missing value as "on", so removing it is also a correct undo.
                            if (old != null && int.TryParse(old, out n) && n != 0) k.SetValue(p[1], n, RegistryValueKind.DWord);
                            else k.DeleteValue(p[1], false);
                            before.DeleteValue(v, false);
                        }
                    }
                }
            }
        }
    }

    /// <summary>
    /// Watches Spotify's window title. While a song plays it reads "Artist - Song".
    /// While an ad plays it reads "Advertisement", the advertiser's name or just "Spotify".
    /// During an ad, Spotify's volume (only Spotify's) is muted, and unmuted when the music is back.
    /// </summary>
    class SpotifyMute
    {
        public volatile bool Enabled;
        public long AdsMuted;
        bool mutedByUs;
        int oddTitleTicks;
        Thread thread;

        public void Start()
        {
            thread = new Thread(Loop) { IsBackground = true, Name = "spotify" };
            thread.SetApartmentState(ApartmentState.MTA);
            thread.Start();
        }

        /// <summary>What Spotify is doing, judged from its window title alone.</summary>
        public static string Judge(string title)
        {
            if (string.IsNullOrEmpty(title)) return "closed";
            if (title.Contains(" - ")) return "music";
            if (title == "Spotify Free" || title == "Spotify Premium" || title == "Spotify") return "idle";
            return "ad";
        }

        [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc callback, IntPtr param);
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr window, System.Text.StringBuilder text, int max);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr window, System.Text.StringBuilder text, int max);
        delegate bool EnumProc(IntPtr window, IntPtr param);

        /// <summary>The title of Spotify's main window, also when it is minimized or hidden in the tray.</summary>
        public static string Title()
        {
            var ids = new HashSet<uint>();
            foreach (var p in Process.GetProcessesByName("Spotify")) { ids.Add((uint)p.Id); p.Dispose(); }
            if (ids.Count == 0) return "";
            string best = "";
            var sb = new System.Text.StringBuilder(512);
            EnumWindows(delegate(IntPtr w, IntPtr x)
            {
                uint pid;
                GetWindowThreadProcessId(w, out pid);
                if (!ids.Contains(pid)) return true;
                sb.Length = 0; GetClassName(w, sb, 256);
                if (!sb.ToString().StartsWith("Chrome_WidgetWin")) return true;
                sb.Length = 0; GetWindowText(w, sb, 512);
                string t = sb.ToString();
                // The main window is the one whose title follows the song; prefer it over helper windows.
                if (t.Length > 0 && (best.Length == 0 || Judge(t) == "music" || (Judge(t) == "ad" && Judge(best) == "idle"))) best = t;
                return true;
            }, IntPtr.Zero);
            return best;
        }

        void Loop()
        {
            while (true)
            {
                Thread.Sleep(mutedByUs ? 250 : 500);
                try { Tick(); } catch { }
            }
        }

        void Tick()
        {
            if (!Enabled)
            {
                if (mutedByUs) { Mute(false); mutedByUs = false; }
                return;
            }
            string title = Title();
            string state = Judge(title);
            // "idle" with sound coming out is an ad too: some ads leave the title as "Spotify Free".
            bool ad = state == "ad" || (state == "idle" && !mutedByUs && Mute(null) > 0.001f);
            if (state == "idle" && mutedByUs) ad = true;       // still in the ad break (or paused during it)
            if (ad)
            {
                // One odd reading can be a title that is halfway through changing; two in a row is an ad.
                if (++oddTitleTicks >= 2 && !mutedByUs)
                {
                    Mute(true);
                    mutedByUs = true;
                    Interlocked.Increment(ref AdsMuted);
                }
            }
            else
            {
                oddTitleTicks = 0;
                if (mutedByUs && (state == "music" || state == "closed"))
                {
                    if (state == "music") Thread.Sleep(400);    // let the ad's last half second pass
                    Mute(false);
                    mutedByUs = false;
                }
            }
        }

        /// <summary>
        /// With true or false: mutes or unmutes every Spotify audio stream.
        /// With null: changes nothing and returns how loud Spotify is right now (0 to 1).
        /// </summary>
        public static string Target = "Spotify";   // the program whose volume is muted (the test points it at itself)
        public static int Streams;       // how many of its audio streams the last call found
        static bool sawMuted;

        public static bool IsMuted() { sawMuted = false; Mute(null); return sawMuted; }

        public static float Mute(bool? mute)
        {
            float loudest = 0;
            Streams = 0;
            var ids = new HashSet<uint>();
            foreach (var p in Process.GetProcessesByName(Target)) { ids.Add((uint)p.Id); p.Dispose(); }
            if (ids.Count == 0) return 0;
            object enumObj = null, mgrObj = null;
            IMMDevice device = null; IAudioSessionEnumerator sessions = null;
            try
            {
                enumObj = Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")));
                ((IMMDeviceEnumerator)enumObj).GetDefaultAudioEndpoint(0, 1, out device);
                Guid iid = typeof(IAudioSessionManager2).GUID;
                device.Activate(ref iid, 23, IntPtr.Zero, out mgrObj);
                ((IAudioSessionManager2)mgrObj).GetSessionEnumerator(out sessions);
                int count;
                sessions.GetCount(out count);
                Guid none = Guid.Empty;
                for (int i = 0; i < count; i++)
                {
                    IAudioSessionControl2 session;
                    sessions.GetSession(i, out session);
                    try
                    {
                        uint pid;
                        session.GetProcessId(out pid);
                        if (!ids.Contains(pid)) continue;
                        Streams++;
                        bool m;
                        ((ISimpleAudioVolume)session).GetMute(out m);
                        if (m) sawMuted = true;
                        if (mute.HasValue) ((ISimpleAudioVolume)session).SetMute(mute.Value, ref none);
                        else
                        {
                            float peak;
                            ((IAudioMeterInformation)session).GetPeakValue(out peak);
                            if (peak > loudest) loudest = peak;
                        }
                    }
                    finally { Marshal.ReleaseComObject(session); }
                }
            }
            catch { }
            finally
            {
                if (sessions != null) Marshal.ReleaseComObject(sessions);
                if (mgrObj != null) Marshal.ReleaseComObject(mgrObj);
                if (device != null) Marshal.ReleaseComObject(device);
                if (enumObj != null) Marshal.ReleaseComObject(enumObj);
            }
            return loudest;
        }

        // The Windows volume mixer's own interfaces (Core Audio). Method order must match Windows exactly.
        [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IMMDeviceEnumerator
        {
            void EnumAudioEndpoints(int dataFlow, int mask, out IntPtr devices);
            void GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device);
        }

        [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IMMDevice
        {
            void Activate(ref Guid iid, int clsCtx, IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object iface);
        }

        [ComImport, Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IAudioSessionManager2
        {
            void GetAudioSessionControl(IntPtr a, int b, out IntPtr c);
            void GetSimpleAudioVolume(IntPtr a, int b, out IntPtr c);
            void GetSessionEnumerator(out IAudioSessionEnumerator sessions);
        }

        [ComImport, Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IAudioSessionEnumerator
        {
            void GetCount(out int count);
            void GetSession(int index, out IAudioSessionControl2 session);
        }

        [ComImport, Guid("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IAudioSessionControl2
        {
            void GetState(out int state);
            void GetDisplayName(out IntPtr name);
            void SetDisplayName(IntPtr name, ref Guid context);
            void GetIconPath(out IntPtr path);
            void SetIconPath(IntPtr path, ref Guid context);
            void GetGroupingParam(out Guid param);
            void SetGroupingParam(ref Guid param, ref Guid context);
            void RegisterAudioSessionNotification(IntPtr n);
            void UnregisterAudioSessionNotification(IntPtr n);
            void GetSessionIdentifier(out IntPtr id);
            void GetSessionInstanceIdentifier(out IntPtr id);
            void GetProcessId(out uint pid);
        }

        [ComImport, Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface ISimpleAudioVolume
        {
            void SetMasterVolume(float level, ref Guid context);
            void GetMasterVolume(out float level);
            void SetMute(bool mute, ref Guid context);
            void GetMute(out bool mute);
        }

        [ComImport, Guid("C02216F6-8C67-4B5B-9D00-D008E73E0064"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IAudioMeterInformation
        {
            void GetPeakValue(out float peak);
        }
    }

    /// <summary>
    /// Checks the two extras on this PC and prints the result (python tests/test_windows.py runs it).
    /// Every Windows setting it touches is put back exactly as it was, and Spotify is unmuted again.
    /// </summary>
    static class ExtrasTest
    {
        static int failed;
        static void Check(string name, bool ok, string detail)
        {
            if (!ok) failed++;
            Console.WriteLine((ok ? "ok\t" : "FAIL\t") + name + "\t" + detail);
        }

        public static int Run()
        {
            // The rule that tells an ad from a song, on the titles Spotify really shows.
            string[,] titles = {
                { "Daft Punk - Get Lucky", "music" }, { "Fairuz - Nassam Alayna El Hawa", "music" }, { "AC/DC - T.N.T.", "music" },
                { "The Daily - Episode 12", "music" }, { "Spotify Free", "idle" }, { "Spotify Premium", "idle" }, { "Spotify", "idle" },
                { "Advertisement", "ad" }, { "Spotify Advertisement", "ad" }, { "Coca-Cola", "ad" }, { "", "closed" } };
            int right = 0;
            for (int i = 0; i < titles.GetLength(0); i++) if (SpotifyMute.Judge(titles[i, 0]) == titles[i, 1]) right++;
            Check("tells ads from songs by the title of the Spotify window", right == titles.GetLength(0), right + "/" + titles.GetLength(0));

            string title = SpotifyMute.Title();
            if (title.Length == 0) Console.WriteLine("skip\tSpotify is not running, so muting it was not tested\t");
            else
            {
                Check("finds the Spotify window", true, "\"" + title + "\" = " + SpotifyMute.Judge(title));
                bool was = SpotifyMute.IsMuted();
                SpotifyMute.Mute(true);
                bool muted = SpotifyMute.IsMuted();
                SpotifyMute.Mute(false);
                bool unmuted = !SpotifyMute.IsMuted();
                if (was) SpotifyMute.Mute(true);
                if (SpotifyMute.Streams == 0) Console.WriteLine("skip\tSpotify has not played anything since it started, so it has no volume to mute yet\t");
                else Check("mutes and unmutes Spotify only", muted && unmuted, SpotifyMute.Streams + " audio stream(s)");
            }

            // The same mute, tried on this test program itself while it plays a Windows sound.
            try
            {
                SpotifyMute.Target = Process.GetCurrentProcess().ProcessName;
                using (var sound = new System.Media.SoundPlayer(Environment.ExpandEnvironmentVariables(@"%WINDIR%\Media\ding.wav")))
                {
                    sound.Play();
                    bool muted = false, unmuted = false;
                    for (int i = 0; i < 20 && SpotifyMute.Streams == 0; i++) { Thread.Sleep(100); SpotifyMute.Mute(null); }
                    int streams = SpotifyMute.Streams;
                    if (streams > 0)
                    {
                        SpotifyMute.Mute(true); muted = SpotifyMute.IsMuted();
                        SpotifyMute.Mute(false); unmuted = !SpotifyMute.IsMuted();
                    }
                    Check("the Windows volume mixer mutes one program and unmutes it", muted && unmuted, streams + " audio stream(s) of this test");
                }
            }
            catch (Exception ex) { Check("the Windows volume mixer mutes one program and unmutes it", false, ex.Message); }
            finally { SpotifyMute.Target = "Spotify"; }

            foreach (var t in WindowsAds.All)
            {
                var before = new List<object>();
                foreach (string v in t.Values)
                    using (var k = Registry.CurrentUser.OpenSubKey(v.Split('|')[0])) before.Add(k == null ? null : k.GetValue(v.Split('|')[1]));
                WindowsAds.Set(t, true);
                bool off = WindowsAds.IsOff(t);
                WindowsAds.Set(t, false);
                bool back = !WindowsAds.IsOff(t);
                for (int i = 0; i < t.Values.Length; i++)       // exactly as it was before the test
                    using (var k = Registry.CurrentUser.CreateSubKey(t.Values[i].Split('|')[0]))
                    {
                        if (before[i] == null) k.DeleteValue(t.Values[i].Split('|')[1], false);
                        else k.SetValue(t.Values[i].Split('|')[1], before[i], RegistryValueKind.DWord);
                    }
                Check("Windows ads: " + t.Label, off && back, "switches off and back on");
            }
            return failed == 0 ? 0 : 1;
        }
    }
}

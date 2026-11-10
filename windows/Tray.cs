// Hib Remover Ads for Windows: the tray icon and its window.
// It only reads the counters the service writes and flips the on/off switch.
// It runs as the normal user and never needs administrator rights.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace Hib
{
    static class Theme
    {
        public static readonly Color Deep = Color.FromArgb(16, 39, 43);
        public static readonly Color Tide = Color.FromArgb(24, 58, 63);
        public static readonly Color Line = Color.FromArgb(42, 80, 87);
        public static readonly Color Foam = Color.FromArgb(228, 240, 236);
        public static readonly Color Kelp = Color.FromArgb(157, 187, 179);
        public static readonly Color Amber = Color.FromArgb(243, 178, 60);
    }

    class PillButton : Button
    {
        public bool Primary = true;
        bool hover;
        public PillButton()
        {
            FlatStyle = FlatStyle.Flat;
            FlatAppearance.BorderSize = 0;
            Cursor = Cursors.Hand;
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer, true);
        }
        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;
            g.Clear(Parent.BackColor);
            var r = new Rectangle(0, 0, Width - 1, Height - 1);
            using (var path = new GraphicsPath())
            {
                int d = r.Height;
                path.AddArc(r.X, r.Y, d, d, 90, 180);
                path.AddArc(r.Right - d, r.Y, d, d, 270, 180);
                path.CloseFigure();
                Color fill = Primary ? (hover ? Color.FromArgb(255, 196, 92) : Theme.Amber) : (hover ? Theme.Line : Theme.Tide);
                using (var b = new SolidBrush(fill)) g.FillPath(b, path);
                if (Focused && ShowFocusCues) using (var p = new Pen(Theme.Foam, 2)) g.DrawPath(p, path);
            }
            TextRenderer.DrawText(g, Text, Font, r, Primary ? Theme.Deep : Theme.Foam,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
        }
    }

    /// <summary>The counters file written by the service every two seconds.</summary>
    class Stats
    {
        public bool Running, Active, Enabled = true, Encrypted = true;
        public long PauseUntil, Rules, Today, Total, LookupMs, Queries, CacheHits;
        public List<KeyValuePair<string, int>> Top = new List<KeyValuePair<string, int>>();

        public static Stats Read()
        {
            var s = new Stats();
            try
            {
                var f = new FileInfo(Paths.Stats);
                if (!f.Exists) return s;
                bool fresh = (DateTime.UtcNow - f.LastWriteTimeUtc).TotalSeconds < 45;
                foreach (var line in File.ReadAllLines(Paths.Stats))
                {
                    int eq = line.IndexOf('=');
                    if (eq < 0) continue;
                    string k = line.Substring(0, eq), v = line.Substring(eq + 1);
                    long n; long.TryParse(v, out n);
                    if (k == "running") s.Running = n == 1 && fresh;
                    else if (k == "active") s.Active = n == 1;
                    else if (k == "enabled") s.Enabled = n == 1;
                    else if (k == "encrypted") s.Encrypted = n == 1;
                    else if (k == "pause_until") s.PauseUntil = n;
                    else if (k == "rules") s.Rules = n;
                    else if (k == "today") s.Today = n;
                    else if (k == "total") s.Total = n;
                    else if (k == "lookup_ms") s.LookupMs = n;
                    else if (k == "queries") s.Queries = n;
                    else if (k == "cache_hits") s.CacheHits = n;
                    else if (k == "top")
                    {
                        int sp = v.LastIndexOf(' ');
                        int c;
                        if (sp > 0 && int.TryParse(v.Substring(sp + 1), out c)) s.Top.Add(new KeyValuePair<string, int>(v.Substring(0, sp), c));
                    }
                }
            }
            catch { }
            return s;
        }
    }

    class Tray : Form
    {
        const string Prefs = @"Software\Hib Remover Ads";
        readonly NotifyIcon icon = new NotifyIcon();
        readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer { Interval = 2000 };
        readonly SpotifyMute spotify = new SpotifyMute();
        readonly Icon on, off;
        readonly Font big = new Font("Segoe UI", 34f, FontStyle.Bold);
        readonly Font head = new Font("Segoe UI Semibold", 11f);
        readonly Font body = new Font("Segoe UI", 9.75f);
        readonly Font small = new Font("Segoe UI", 9f);
        float k = 1f;
        int S(int v) { return (int)Math.Round(v * k); }

        Label status, count, countCaption, detail;
        PillButton power, pause;
        ListBox top, allowed;
        CheckBox muteSpotify;
        CheckedListBox windowsAds;
        ToolStripMenuItem menuPower, menuPause;
        Stats stats = new Stats();
        bool filling, reallyClose;

        public static int RunApp(bool startHidden)
        {
            bool first;
            using (var only = new Mutex(true, @"Local\HibRemoverAdsTray", out first))
            using (var show = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\HibRemoverAdsShow"))
            {
                // Already running: ask that copy to show its window.
                if (!first) { if (!startHidden) show.Set(); return 0; }
                var form = new Tray(startHidden);
                var waiter = new Thread(delegate()
                {
                    while (true)
                    {
                        show.WaitOne();
                        try { form.BeginInvoke((MethodInvoker)form.ShowWindow); } catch { }
                    }
                }) { IsBackground = true };
                waiter.Start();
                Application.Run(form);
                return 0;
            }
        }

        readonly bool hidden;
        static bool preview;

        /// <summary>Saves a picture of the window, drawn from the counters in Paths.Data.</summary>
        public static void Screenshot(string file)
        {
            preview = true;
            using (var form = new Tray(false))
            {
                form.StartPosition = FormStartPosition.Manual;
                form.Location = new Point(-4000, -4000);
                form.ShowInTaskbar = false;
                form.Show();
                form.Refresh2();
                Application.DoEvents();
                using (var bmp = new Bitmap(form.Width, form.Height))
                {
                    form.DrawToBitmap(bmp, new Rectangle(0, 0, form.Width, form.Height));
                    bmp.Save(file, System.Drawing.Imaging.ImageFormat.Png);
                }
                form.reallyClose = true;
                form.Close();
            }
        }

        Tray(bool startHidden)
        {
            hidden = startHidden;
            Text = "Hib Remover Ads";
            AutoScaleMode = AutoScaleMode.None;
            using (var g = CreateGraphics()) k = g.DpiX / 96f;
            ClientSize = new Size(S(520), S(742));
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Theme.Deep; ForeColor = Theme.Foam; Font = body;
            on = LoadIcon("on.png"); off = LoadIcon("off.png");
            Icon = on;
            Build();

            var menu = new ContextMenuStrip();
            menu.Items.Add("Open Hib Remover Ads", null, delegate { ShowWindow(); });
            menuPower = (ToolStripMenuItem)menu.Items.Add("Turn off", null, delegate { TogglePower(); });
            menuPause = (ToolStripMenuItem)menu.Items.Add("Pause for 1 hour", null, delegate { TogglePause(); });
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Hide this icon (blocking stays on)", null, delegate { reallyClose = true; Close(); });
            icon.ContextMenuStrip = menu;
            icon.Icon = on; icon.Text = "Hib Remover Ads"; icon.Visible = !preview;
            icon.MouseClick += delegate(object s, MouseEventArgs e) { if (e.Button == MouseButtons.Left) ShowWindow(); };

            if (preview) { filling = true; muteSpotify.Checked = true; filling = false; return; }
            FirstRun();
            using (var key = Registry.CurrentUser.CreateSubKey(Prefs))
                spotify.Enabled = muteSpotify.Checked = (key.GetValue("MuteSpotifyAds", 1) as int? ?? 1) == 1;
            spotify.Start();
            timer.Tick += delegate { Refresh2(); };
            timer.Start();
            Refresh2();
        }

        // Started with Windows: stay in the tray, don't show the window.
        protected override void SetVisibleCore(bool value)
        {
            if (hidden && !shownOnce) { if (!IsHandleCreated) CreateHandle(); value = false; }
            base.SetVisibleCore(value);
        }
        bool shownOnce;

        void ShowWindow()
        {
            shownOnce = true;
            Refresh2();
            Show();
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Activate();
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (!reallyClose && e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; Hide(); return; }
            icon.Visible = false;
            base.OnFormClosing(e);
        }

        static Icon LoadIcon(string name)
        {
            using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
            using (var bmp = new Bitmap(s))
            using (var small = new Bitmap(bmp, new Size(32, 32)))
                return Icon.FromHandle(small.GetHicon());
        }

        // The first time each user runs it: switch off the ads built into Windows. Each one can be switched back in the window.
        void FirstRun()
        {
            using (var key = Registry.CurrentUser.CreateSubKey(Prefs))
            {
                if (key.GetValue("FirstRunDone") != null) return;
                foreach (var t in WindowsAds.All) try { WindowsAds.Set(t, true); } catch { }
                key.SetValue("FirstRunDone", 1, RegistryValueKind.DWord);
            }
        }

        // ---------- the window ----------

        Label Add(string text, Font font, Color color, int left, int top, int width, int height)
        {
            var l = new Label { Text = text, Font = font, ForeColor = color, AutoSize = false, BackColor = Color.Transparent,
                Left = S(left), Top = S(top), Width = S(width), Height = S(height) };
            Controls.Add(l);
            return l;
        }

        PillButton AddButton(string text, bool primary, int left, int top, int width, int height, EventHandler click)
        {
            var b = new PillButton { Text = text, Primary = primary, Left = S(left), Top = S(top), Width = S(width), Height = S(height),
                Font = primary ? new Font("Segoe UI", 10.5f, FontStyle.Bold) : new Font("Segoe UI Semibold", 9.75f) };
            b.Click += click;
            Controls.Add(b);
            return b;
        }

        ListBox AddList(int top, int height)
        {
            var l = new ListBox { Left = S(32), Top = S(top), Width = S(456), Height = S(height), BackColor = Theme.Tide, ForeColor = Theme.Foam,
                BorderStyle = BorderStyle.None, Font = new Font("Consolas", 9.75f), IntegralHeight = false };
            Controls.Add(l);
            return l;
        }

        void Build()
        {
            using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("on.png"))
                Controls.Add(new PictureBox { Image = Image.FromStream(s), SizeMode = PictureBoxSizeMode.Zoom, Left = S(32), Top = S(26), Width = S(44), Height = S(44) });
            Add("Hib Remover Ads", new Font("Segoe UI", 15f, FontStyle.Bold), Theme.Foam, 88, 22, 400, 30);
            status = Add("", body, Theme.Kelp, 89, 52, 400, 22);

            count = Add("0", big, Theme.Amber, 26, 84, 464, 60);
            countCaption = Add("ads and trackers blocked today, in every app", body, Theme.Foam, 32, 146, 456, 22);
            detail = Add("", small, Theme.Kelp, 32, 168, 456, 20);

            power = AddButton("Turn off", true, 32, 200, 150, 40, delegate { TogglePower(); });
            pause = AddButton("Pause for 1 hour", false, 194, 200, 170, 40, delegate { TogglePause(); });

            Add("Blocked most since this PC started", head, Theme.Foam, 32, 258, 320, 24);
            AddButton("Allow selected", false, 356, 254, 132, 30, delegate { AllowSelected(); });
            top = AddList(290, 132);

            Add("Allowed by you", head, Theme.Foam, 32, 434, 320, 24);
            AddButton("Block again", false, 356, 430, 132, 30, delegate { BlockAgain(); });
            allowed = AddList(466, 54);

            Add("Extras", head, Theme.Foam, 32, 532, 320, 24);
            muteSpotify = new CheckBox { Text = "Mute Spotify while it plays an audio ad",
                Left = S(32), Top = S(558), Width = S(456), Height = S(22), ForeColor = Theme.Foam, BackColor = Color.Transparent, Font = small };
            muteSpotify.CheckedChanged += delegate
            {
                if (filling) return;
                spotify.Enabled = muteSpotify.Checked;
                using (var key = Registry.CurrentUser.CreateSubKey(Prefs)) key.SetValue("MuteSpotifyAds", muteSpotify.Checked ? 1 : 0, RegistryValueKind.DWord);
            };
            Controls.Add(muteSpotify);
            Add("Ads built into Windows, switched off (untick to get one back):", small, Theme.Kelp, 32, 584, 456, 20);
            windowsAds = new CheckedListBox { Left = S(32), Top = S(606), Width = S(456), Height = S(104), BackColor = Theme.Deep, ForeColor = Theme.Foam,
                BorderStyle = BorderStyle.None, CheckOnClick = true, Font = small, IntegralHeight = false };
            foreach (var t in WindowsAds.All) windowsAds.Items.Add(t.Label);
            windowsAds.ItemCheck += delegate(object s, ItemCheckEventArgs e)
            {
                if (filling) return;
                try { WindowsAds.Set(WindowsAds.All[e.Index], e.NewValue == CheckState.Checked); } catch { }
            };
            Controls.Add(windowsAds);

            var links = new LinkLabel { Text = "Website and source code     Uninstall", Left = S(32), Top = S(714), Width = S(456), Height = S(20),
                LinkColor = Theme.Kelp, ActiveLinkColor = Theme.Amber, Font = small, BackColor = Color.Transparent };
            links.Links.Add(0, 23, "site");
            links.Links.Add(28, 9, "uninstall");
            links.LinkClicked += delegate(object s, LinkLabelLinkClickedEventArgs e)
            {
                try
                {
                    if ((string)e.Link.LinkData == "site") Process.Start(Paths.Repo);
                    else Process.Start(Program.Self, "--uninstall");
                }
                catch { }
            };
            Controls.Add(links);
        }

        // ---------- keeping it current ----------

        void Refresh2()
        {
            stats = Stats.Read();
            bool paused = stats.Running && stats.Enabled && stats.PauseUntil > DateTime.UtcNow.Ticks;
            bool active = stats.Running && stats.Enabled && !paused;
            icon.Icon = active ? on : off;
            string line = !stats.Running ? "Not running. Ads are not being blocked."
                : !stats.Enabled ? "Turned off. Ads are not being blocked."
                : paused ? "Paused until " + new DateTime(stats.PauseUntil, DateTimeKind.Utc).ToLocalTime().ToString("HH:mm") + "."
                : "On. Blocking ads in every app on this PC.";
            icon.Text = active ? "Hib Remover Ads: " + stats.Today.ToString("N0") + " blocked today" : "Hib Remover Ads: " + line.Split('.')[0].ToLowerInvariant();
            menuPower.Text = !stats.Running ? "Start" : stats.Enabled ? "Turn off" : "Turn on";
            menuPause.Text = paused ? "Resume now" : "Pause for 1 hour";
            menuPause.Enabled = stats.Running && stats.Enabled;
            if (!Visible) return;

            status.Text = line;
            status.ForeColor = active ? Theme.Kelp : Theme.Amber;
            count.Text = stats.Today.ToString("N0");
            long muted = Interlocked.Read(ref spotify.AdsMuted);
            detail.Text = stats.Total.ToString("N0") + " in total  ·  new lookups take " + stats.LookupMs + " ms, repeats are instant"
                + (muted > 0 ? "  ·  " + muted + " Spotify ads muted" : "");
            power.Text = menuPower.Text;
            pause.Text = menuPause.Text;
            pause.Enabled = menuPause.Enabled;

            object keep = top.SelectedItem;
            top.BeginUpdate();
            top.Items.Clear();
            foreach (var kv in stats.Top) top.Items.Add(kv.Value.ToString().PadLeft(6) + "  " + kv.Key);
            if (stats.Top.Count == 0) top.Items.Add("  Nothing yet. Open an app or a website.");
            if (keep != null) foreach (object o in top.Items) if (Domain(o) == Domain(keep)) { top.SelectedItem = o; break; }
            top.EndUpdate();

            keep = allowed.SelectedItem;
            allowed.BeginUpdate();
            allowed.Items.Clear();
            foreach (string a in ReadAllow()) allowed.Items.Add(a);
            if (keep != null && allowed.Items.Contains(keep)) allowed.SelectedItem = keep;
            allowed.EndUpdate();

            filling = true;
            for (int i = 0; i < WindowsAds.All.Length; i++)
                try { windowsAds.SetItemChecked(i, preview || WindowsAds.IsOff(WindowsAds.All[i])); } catch { }
            filling = false;
        }

        static string Domain(object item)
        {
            string s = (item as string ?? "").Trim();
            int sp = s.LastIndexOf(' ');
            return sp < 0 ? s : s.Substring(sp + 1);
        }

        // ---------- the switches ----------

        void WriteSettings(bool enabled, long pauseUntil)
        {
            try
            {
                Directory.CreateDirectory(Paths.User);
                File.WriteAllText(Paths.Settings, "enabled=" + (enabled ? 1 : 0) + "\npause_until=" + pauseUntil + "\n");
            }
            catch (Exception ex) { MessageBox.Show(this, "Couldn't save the setting: " + ex.Message, "Hib Remover Ads"); }
            // The service picks the change up within a second.
            var t = new System.Windows.Forms.Timer { Interval = 1500 };
            t.Tick += delegate { t.Stop(); t.Dispose(); Refresh2(); };
            t.Start();
        }

        void TogglePower()
        {
            if (!stats.Running)
            {
                // Starting a service needs administrator permission; the installer does it and checks it works.
                try { Process.Start(Program.Self, "--install --no-open"); } catch { }
                return;
            }
            WriteSettings(!stats.Enabled, 0);
        }

        void TogglePause()
        {
            bool paused = stats.PauseUntil > DateTime.UtcNow.Ticks;
            WriteSettings(true, paused ? 0 : DateTime.UtcNow.AddHours(1).Ticks);
        }

        static List<string> ReadAllow()
        {
            var list = new List<string>();
            try
            {
                foreach (var line in File.ReadAllLines(Paths.UserAllow))
                    if (line.Trim().Length > 0) list.Add(line.Trim());
            }
            catch { }
            return list;
        }

        void SaveAllow(List<string> list)
        {
            try
            {
                Directory.CreateDirectory(Paths.User);
                File.WriteAllLines(Paths.UserAllow, list.ToArray());
            }
            catch (Exception ex) { MessageBox.Show(this, "Couldn't save the list: " + ex.Message, "Hib Remover Ads"); }
            Refresh2();
        }

        void AllowSelected()
        {
            string name = Domain(top.SelectedItem);
            if (name.IndexOf('.') < 0) return;
            var list = ReadAllow();
            if (!list.Contains(name)) list.Add(name);
            SaveAllow(list);
        }

        void BlockAgain()
        {
            string name = allowed.SelectedItem as string;
            if (name == null) return;
            var list = ReadAllow();
            list.Remove(name);
            SaveAllow(list);
        }
    }
}

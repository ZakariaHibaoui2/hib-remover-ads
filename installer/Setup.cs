// Hib Remover Ads installer for Windows.
// Unpacks the extension to %LOCALAPPDATA%\Hib Remover Ads\extension, copies that
// path, and opens the browser's extensions page. Browsers don't allow outside
// programs to add extensions silently, so the last three clicks are the user's.
// Build: installer\build.cmd
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("Hib Remover Ads Setup")]
[assembly: AssemblyProduct("Hib Remover Ads")]
[assembly: AssemblyVersion("2.0.0.0")]
[assembly: AssemblyFileVersion("2.0.0.0")]

namespace HibSetup
{
    class Browser
    {
        public string Name, Exe, Page;
        public Browser(string name, string exe, string page) { Name = name; Exe = exe; Page = page; }
        public override string ToString() { return Name; }
    }

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
        public PillButton()
        {
            FlatStyle = FlatStyle.Flat;
            FlatAppearance.BorderSize = 0;
            Cursor = Cursors.Hand;
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer, true);
        }
        bool hover;
        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;
            g.Clear(Parent.BackColor);
            var r = new Rectangle(0, 0, Width - 1, Height - 1);
            using (var path = Round(r, Height / 2))
            {
                Color fill = Primary ? (hover ? Color.FromArgb(255, 196, 92) : Theme.Amber) : (hover ? Theme.Line : Theme.Tide);
                using (var b = new SolidBrush(Enabled ? fill : Theme.Line)) g.FillPath(b, path);
                if (Focused && ShowFocusCues)
                    using (var p = new Pen(Theme.Foam, 2)) g.DrawPath(p, path);
            }
            TextRenderer.DrawText(g, Text, Font, r, Primary ? Theme.Deep : Theme.Foam,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
        }
        public static GraphicsPath Round(Rectangle r, int radius)
        {
            var p = new GraphicsPath();
            int d = Math.Min(radius * 2, Math.Min(r.Width, r.Height));
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }
    }

    class SetupForm : Form
    {
        readonly string target = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Hib Remover Ads", "extension");
        readonly Font title = new Font("Segoe UI", 22f, FontStyle.Bold);
        readonly Font body = new Font("Segoe UI", 10.5f);
        readonly Font bold = new Font("Segoe UI Semibold", 10.5f);
        readonly Panel page = new Panel();
        ComboBox browsers;
        float k = 1f;
        int S(int v) { return (int)Math.Round(v * k); }
        Browser chosen;

        public SetupForm()
        {
            Text = "Hib Remover Ads Setup";
            using (var g = CreateGraphics()) k = g.DpiX / 96f;
            ClientSize = new Size(S(560), S(520));
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Theme.Deep;
            ForeColor = Theme.Foam;
            Font = body;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
            page.Dock = DockStyle.Fill;
            page.Padding = new Padding(S(40), S(36), S(40), S(32));
            Controls.Add(page);
            ShowWelcome();
        }

        static Image Logo()
        {
            var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("logo.png");
            return s == null ? null : Image.FromStream(s);
        }

        Label AddLabel(string text, Font font, Color color, int top, int height)
        {
            var l = new Label { Text = text, Font = font, ForeColor = color, AutoSize = false,
                Left = S(40), Top = S(top), Width = S(480), Height = S(height), BackColor = Color.Transparent };
            page.Controls.Add(l);
            return l;
        }

        PillButton AddButton(string text, bool primary, int left, int top, int width, EventHandler click)
        {
            var b = new PillButton { Text = text, Primary = primary, Left = S(left), Top = S(top), Width = S(width), Height = S(48),
                Font = primary ? new Font("Segoe UI", 11.5f, FontStyle.Bold) : bold };
            b.Click += click;
            page.Controls.Add(b);
            return b;
        }

        static List<Browser> FindBrowsers()
        {
            string pf = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
            string pf86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            var candidates = new[] {
                new Browser("Google Chrome", @"Google\Chrome\Application\chrome.exe", "chrome://extensions"),
                new Browser("Microsoft Edge", @"Microsoft\Edge\Application\msedge.exe", "edge://extensions"),
                new Browser("Brave", @"BraveSoftware\Brave-Browser\Application\brave.exe", "brave://extensions"),
                new Browser("Opera", @"Programs\Opera\opera.exe", "opera://extensions"),
                new Browser("Opera GX", @"Programs\Opera GX\opera.exe", "opera://extensions"),
                new Browser("Vivaldi", @"Vivaldi\Application\vivaldi.exe", "vivaldi://extensions"),
                new Browser("Opera Air", @"Programs\Opera Air\opera.exe", "opera://extensions"),
                new Browser("Yandex Browser", @"Yandex\YandexBrowser\Application\browser.exe", "browser://extensions"),
                new Browser("Chromium", @"Chromium\Application\chrome.exe", "chrome://extensions"),
                new Browser("Thorium", @"Thorium\Application\thorium.exe", "chrome://extensions"),
                new Browser("Cent Browser", @"CentBrowser\Application\chrome.exe", "chrome://extensions"),
                new Browser("Coc Coc", @"CocCoc\Browser\Application\browser.exe", "coccoc://extensions"),
                new Browser("Comodo Dragon", @"Comodo\Dragon\dragon.exe", "chrome://extensions"),
                new Browser("Epic Privacy Browser", @"Epic Privacy Browser\Application\epic.exe", "chrome://extensions"),
                new Browser("SRWare Iron", @"Chromium\Application\iron.exe", "chrome://extensions"),
                new Browser("Google Chrome Beta", @"Google\Chrome Beta\Application\chrome.exe", "chrome://extensions"),
                new Browser("Google Chrome Dev", @"Google\Chrome Dev\Application\chrome.exe", "chrome://extensions"),
                new Browser("Google Chrome Canary", @"Google\Chrome SxS\Application\chrome.exe", "chrome://extensions"),
                new Browser("Microsoft Edge Beta", @"Microsoft\Edge Beta\Application\msedge.exe", "edge://extensions"),
                new Browser("Microsoft Edge Dev", @"Microsoft\Edge Dev\Application\msedge.exe", "edge://extensions"),
                new Browser("Brave Beta", @"BraveSoftware\Brave-Browser-Beta\Application\brave.exe", "brave://extensions"),
            };
            var found = new List<Browser>();
            foreach (var c in candidates)
            {
                foreach (var root in new[] { pf, pf86, local })
                {
                    string full = Path.Combine(root, c.Exe);
                    if (File.Exists(full)) { found.Add(new Browser(c.Name, full, c.Page)); break; }
                }
            }
            return found;
        }

        static int DefaultIndex(List<Browser> list)
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"))
                {
                    string id = k == null ? "" : (k.GetValue("ProgId") as string ?? "").ToLowerInvariant();
                    for (int i = 0; i < list.Count; i++)
                    {
                        string n = list[i].Name.ToLowerInvariant();
                        if ((id.StartsWith("chrome") && n.Contains("chrome")) || (id.StartsWith("msedge") && n.Contains("edge"))
                            || (id.StartsWith("brave") && n.Contains("brave")) || (id.StartsWith("opera") && n.Contains("opera"))
                            || (id.StartsWith("vivaldi") && n.Contains("vivaldi")) || (id.StartsWith("yandex") && n.Contains("yandex"))) return i;
                    }
                }
            }
            catch { }
            return 0;
        }

        void ShowWelcome()
        {
            page.Controls.Clear();
            var logo = Logo();
            if (logo != null)
                page.Controls.Add(new PictureBox { Image = logo, SizeMode = PictureBoxSizeMode.Zoom, Left = S(40), Top = S(40), Width = S(64), Height = S(64) });
            AddLabel("Hib Remover Ads", title, Theme.Foam, 120, 48);
            AddLabel("Free ad blocker for YouTube and every website. Blocks video ads, banners, popups and trackers.",
                body, Theme.Kelp, 172, 50);

            var list = FindBrowsers();
            if (list.Count == 0)
            {
                AddLabel("No supported browser found. Install Chrome, Edge, Brave, Opera, Vivaldi or another Chromium browser, then run this again.",
                    bold, Theme.Amber, 250, 50);
                AddButton("Close", false, 40, 420, 140, delegate { Close(); });
                return;
            }
            AddLabel("Install it in", bold, Theme.Foam, 250, 24);
            browsers = new ComboBox { Left = S(40), Top = S(278), Width = S(480), DropDownStyle = ComboBoxStyle.DropDownList,
                FlatStyle = FlatStyle.Flat, BackColor = Theme.Tide, ForeColor = Theme.Foam, Font = bold };
            foreach (var b in list) browsers.Items.Add(b);
            browsers.SelectedIndex = DefaultIndex(list);
            page.Controls.Add(browsers);

            AddLabel("Installs to " + target, new Font("Segoe UI", 9f), Theme.Kelp, 330, 36);
            var install = AddButton("Install", true, 40, 410, 200, delegate { Install(); });
            AcceptButton = install;
            ActiveControl = install;
            AddButton("Cancel", false, 256, 410, 120, delegate { Close(); });
        }

        void Install()
        {
            chosen = (Browser)browsers.SelectedItem;
            try
            {
                if (Directory.Exists(target)) Directory.Delete(target, true);
                Directory.CreateDirectory(target);
                using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("extension.zip"))
                using (var zip = new ZipArchive(s, ZipArchiveMode.Read))
                {
                    foreach (var entry in zip.Entries)
                    {
                        string dest = Path.GetFullPath(Path.Combine(target, entry.FullName));
                        if (!dest.StartsWith(Path.GetFullPath(target) + Path.DirectorySeparatorChar)) continue;
                        if (entry.FullName.EndsWith("/")) { Directory.CreateDirectory(dest); continue; }
                        Directory.CreateDirectory(Path.GetDirectoryName(dest));
                        entry.ExtractToFile(dest, true);
                    }
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "Couldn't unpack the extension: " + ex.Message +
                    "\n\nClose the browser and run Setup again.", "Hib Remover Ads", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            CopyPath();
            OpenExtensionsPage();
            ShowSteps();
        }

        void CopyPath()
        {
            for (int i = 0; i < 10; i++)
            {
                try { Clipboard.SetDataObject(target, true, 5, 100); return; }
                catch { System.Threading.Thread.Sleep(100); }
            }
        }

        void OpenExtensionsPage()
        {
            try { Process.Start(new ProcessStartInfo(chosen.Exe, chosen.Page) { UseShellExecute = false }); }
            catch { }
        }

        void ShowSteps()
        {
            page.Controls.Clear();
            AddLabel("Almost done", title, Theme.Foam, 36, 48);
            AddLabel(chosen.Name + " is open on its extensions page. Do these three things there:", body, Theme.Kelp, 88, 44);
            string[] steps = {
                "Turn on Developer mode (switch at the top right).",
                "Click Load unpacked.",
                "In the folder box, press Ctrl+V and click Select Folder. The folder path is already copied.",
            };
            int top = 146;
            for (int i = 0; i < steps.Length; i++)
            {
                var n = new Label { Text = (i + 1).ToString(), Left = S(40), Top = S(top), Width = S(34), Height = S(34),
                    TextAlign = ContentAlignment.MiddleCenter, Font = new Font("Segoe UI", 12f, FontStyle.Bold),
                    ForeColor = Theme.Deep, BackColor = Theme.Amber };
                using (var p = PillButton.Round(new Rectangle(0, 0, S(34), S(34)), S(17))) n.Region = new Region(p);
                page.Controls.Add(n);
                var l = AddLabel(steps[i], bold, Theme.Foam, top + 6, 48);
                l.Left = S(88); l.Width = S(432);
                top += 64;
            }
            var box = new TextBox { Text = target, ReadOnly = true, Left = S(40), Top = S(top + 6), Width = S(480),
                BackColor = Theme.Tide, ForeColor = Theme.Foam, BorderStyle = BorderStyle.FixedSingle, Font = new Font("Consolas", 10f) };
            page.Controls.Add(box);
            AddLabel("Then pin it from the puzzle-piece menu to see how many ads it blocks.", body, Theme.Kelp, top + 44, 40);
            AddButton("Copy path again", false, 40, 430, 170, delegate { CopyPath(); });
            AddButton("Open page again", false, 222, 430, 170, delegate { OpenExtensionsPage(); });
            AddButton("Done", true, 404, 430, 116, delegate { Close(); });
        }

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        static extern bool SetProcessDPIAware();

        [STAThread]
        static void Main()
        {
            try { SetProcessDPIAware(); } catch { }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SetupForm());
        }
    }
}

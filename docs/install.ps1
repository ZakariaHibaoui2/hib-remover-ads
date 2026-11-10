# Hib Remover Ads installer for Windows.
# Run in PowerShell:  irm https://zakariahibaoui2.github.io/hib-remover-ads/install.ps1 | iex
#
# Downloads the latest release zip from GitHub, unpacks it to
# %LOCALAPPDATA%\Hib Remover Ads\extension, copies that path and opens your
# browser's extensions page. Browsers don't let outside programs add
# extensions, so you finish with Load unpacked.
#
# Then it offers the Windows app, which blocks ads in every program (Spotify,
# free games, Windows itself). That part asks for administrator permission.
#
# For testing only (tests/test_install.py), three environment variables:
#   HIB_SOURCE   folder or address to download from, instead of the latest release
#   HIB_TARGET   folder to install into, instead of %LOCALAPPDATA%\Hib Remover Ads
#   HIB_ANSWERS  answers to the questions, e.g. "browser=none;windows=no"

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$source = 'https://github.com/ZakariaHibaoui2/hib-remover-ads/releases/latest/download'
if ($env:HIB_SOURCE) { $source = $env:HIB_SOURCE.TrimEnd('/') }
$folder = Join-Path $env:LOCALAPPDATA 'Hib Remover Ads'
if ($env:HIB_TARGET) { $folder = $env:HIB_TARGET }
$answers = @{}
if ($env:HIB_ANSWERS) { $env:HIB_ANSWERS -split ';' | ForEach-Object { $k, $v = $_ -split '=', 2; $answers[$k.Trim()] = "$v".Trim() } }

$zipUrl = "$source/hib-remover-ads.zip"
$target = Join-Path $folder 'extension'
$zip = Join-Path $env:TEMP 'hib-remover-ads.zip'

Write-Host ''
Write-Host '  Hib Remover Ads' -ForegroundColor Yellow
Write-Host '  Free ad blocker for YouTube, every website and every Windows app' -ForegroundColor DarkGray
Write-Host ''

Write-Host '  Downloading the latest version...'
Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing

if (Test-Path $target) { Remove-Item $target -Recurse -Force }
New-Item -ItemType Directory -Force -Path $target | Out-Null
Expand-Archive -Path $zip -DestinationPath $target -Force
Remove-Item $zip -Force
$version = (Get-Content (Join-Path $target 'manifest.json') -Raw | ConvertFrom-Json).version
Write-Host "  Unpacked version $version to $target" -ForegroundColor Green

$roots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA) | Where-Object { $_ }
$browsers = @(
  @('Google Chrome',        'Google\Chrome\Application\chrome.exe',                 'chrome://extensions'),
  @('Microsoft Edge',       'Microsoft\Edge\Application\msedge.exe',                'edge://extensions'),
  @('Brave',                'BraveSoftware\Brave-Browser\Application\brave.exe',    'brave://extensions'),
  @('Opera',                'Programs\Opera\opera.exe',                             'opera://extensions'),
  @('Opera GX',             'Programs\Opera GX\opera.exe',                          'opera://extensions'),
  @('Opera Air',            'Programs\Opera Air\opera.exe',                         'opera://extensions'),
  @('Vivaldi',              'Vivaldi\Application\vivaldi.exe',                      'vivaldi://extensions'),
  @('Yandex Browser',       'Yandex\YandexBrowser\Application\browser.exe',         'browser://extensions'),
  @('Chromium',             'Chromium\Application\chrome.exe',                      'chrome://extensions'),
  @('Thorium',              'Thorium\Application\thorium.exe',                      'chrome://extensions'),
  @('Cent Browser',         'CentBrowser\Application\chrome.exe',                   'chrome://extensions'),
  @('Coc Coc',              'CocCoc\Browser\Application\browser.exe',               'coccoc://extensions'),
  @('Comodo Dragon',        'Comodo\Dragon\dragon.exe',                             'chrome://extensions'),
  @('Epic Privacy Browser', 'Epic Privacy Browser\Application\epic.exe',            'chrome://extensions')
)
$found = @()
foreach ($b in $browsers) {
  foreach ($r in $roots) {
    $exe = Join-Path $r $b[1]
    if (Test-Path $exe) { $found += ,@($b[0], $exe, $b[2]); break }
  }
}

if ($answers['browser'] -eq 'none') { $found = @() } else { Set-Clipboard -Value $target }
if ($answers['browser'] -eq 'none') {
  Write-Host '  (test run: no browser opened)' -ForegroundColor DarkGray
} elseif ($found.Count -eq 0) {
  Write-Host '  No supported browser found. Open your browser''s extensions page yourself.' -ForegroundColor Yellow
} else {
  $picks = $found
  if ($found.Count -gt 1) {
    Write-Host ''
    Write-Host ("  0. All {0} browsers (press Enter)" -f $found.Count)
    for ($i = 0; $i -lt $found.Count; $i++) { Write-Host ("  {0}. {1}" -f ($i + 1), $found[$i][0]) }
    $answer = Read-Host '  Install it in which browser? Type its number'
    $n = 0
    if ([int]::TryParse($answer, [ref]$n) -and $n -ge 1 -and $n -le $found.Count) { $picks = @(,$found[$n - 1]) }
  }
  foreach ($pick in $picks) { Start-Process -FilePath $pick[1] -ArgumentList $pick[2] }
  Write-Host ''
  if ($picks.Count -gt 1) {
    Write-Host ("  {0} are open on their extensions pages. In each one:" -f (($picks | ForEach-Object { $_[0] }) -join ', '))
  } else {
    Write-Host ("  {0} is open on its extensions page. There:" -f $picks[0][0])
  }
}
Write-Host '    1. Turn on Developer mode (top right).'
Write-Host '    2. Click Load unpacked.'
Write-Host '    3. Press Ctrl+V in the folder box and click Select Folder. The path is already copied.'
Write-Host ''

# ---------- the Windows app: ads gone from every program, not only the browser ----------
if ([Environment]::OSVersion.Version.Major -ge 10) {
  $want = $answers['windows']
  if (-not $want) {
    Write-Host '  Also block ads in Windows apps (Spotify, free games, Windows itself)?' -ForegroundColor Yellow
    Write-Host '  It asks for administrator permission once. Remove it any time from Settings > Apps.' -ForegroundColor DarkGray
    $want = Read-Host '  Press Enter for yes, or type n for no'
  }
  if ($want -notmatch '^\s*n') {
    $app = Join-Path $folder 'HibRemoverAds-Windows.exe'
    Write-Host '  Downloading the Windows app...'
    Invoke-WebRequest -Uri "$source/HibRemoverAds-Windows.exe" -OutFile $app -UseBasicParsing
    # "check" is for the tests: it asks the app whether this PC is ready, and installs nothing.
    $mode = if ($want -eq 'check') { '--check' } else { '--install' }
    $run = Start-Process -FilePath $app -ArgumentList $mode -Wait -PassThru
    if ($run.ExitCode -eq 0) {
      if ($mode -eq '--check') { Write-Host '  This PC is ready for the Windows app.' -ForegroundColor Green }
      else { Write-Host '  Done. Ads are now blocked in every app. Look for the Hib Remover Ads icon next to the clock.' -ForegroundColor Green }
    } else {
      Write-Host '  The Windows app was not installed, and nothing was changed. Run this again any time.' -ForegroundColor Yellow
    }
    Write-Host ''
  }
}

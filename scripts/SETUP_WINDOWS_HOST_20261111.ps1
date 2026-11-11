# Xiaomi Pad 5 (nabu) - rebuild the Windows host after a clean reinstall.
# Run in an ELEVATED PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\SETUP_WINDOWS_HOST_20261111.ps1
#
# What it does (in order):
#   1. Installs Git, Python 3.12, GitHub CLI (winget), Android platform-tools and the Google USB driver.
#   2. Recreates Desktop\NABU_IPADOS_LAB and clones beamerwz/nabu-ipados-macos-build (dev branch)
#      plus zzweiqing/UniXNU-nabu pinned at 54b4f98.
#   3. Looks for the external backups (NABU_IPADOS_COMPLETE_BACKUP_20261107, NABU_IPADOS_RECOVERY_20261106)
#      and for the verified temporary TWRP image (by size and SHA-256). Copies only the TWRP image.
#   4. Waits for the tablet in Fastboot or TWRP, runs READ-ONLY identity checks, RAM-boots the verified
#      TWRP (fastboot boot = no flash), then in TWRP: sets the ESP block device read-only, mounts it
#      read-only, checks the installed combined-Metal candidate hashes and pulls XNU2LOG.BIN.
#
# It NEVER runs fastboot flash/erase/format/set_active, never writes a partition, never touches Android.
# Everything is logged to NABU_IPADOS_LAB\host-setup\<timestamp>\.

#Requires -RunAsAdministrator
param(
    [int]$WaitMinutes = 15,
    [switch]$NoDevice,
    [switch]$NoTwrpBoot
)

$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ---------------------------------------------------------------- constants
$Lab        = Join-Path $env:USERPROFILE 'Desktop\NABU_IPADOS_LAB'
$RepoUrl    = 'https://github.com/beamerwz/nabu-ipados-macos-build'
$RepoBranch = 'build/nabu-integrated-vsync-20261110'
$RepoCommit = '473cdbb'
$RefUrl     = 'https://github.com/zzweiqing/UniXNU-nabu'
$RefCommit  = '54b4f98457f8e9e232cc0a077c20d08d0b2f0ac9'
$Serial     = '33288984'
$TwrpName   = 'V4-MODDED-TWRP-LINUX.img'
$TwrpSize   = 41598976
$TwrpSha    = '7a71da691a9117cf959ced0557593d647a8fc384b2374404f14184126ab7cbc6'
$EspDev     = '/dev/block/sda29'
$EspSize    = '1073741824'
$Payload    = '/esp/EFI/UniXNU/Payloads/kernel-fulltrace-panic.macho'
# Installed combined Metal candidate (docs/COMBINED_METAL_20261110_INSTALL_RESULT.md)
$Expected = [ordered]@{
    ($Payload)                      = '7291773563faf2791ca4e874117b9c517437791f0d8efe98cb3838a16839b60d'
    ($Payload + '.adt')             = '429d9e7f39da10fb373b4a05081b9817843fe6c8e86e10728ac8fb74f7fbb514'
    ($Payload + '.gpuaddon')        = 'df3ada891f3a69c340b78db71a903fd2f681443e89884cce499143090a1f2db4'
    ($Payload + '.trustcache')      = 'a8c8ec8fd80217a763c0f40311fe84f66a9ffaf4cbc03146e01be8831e6fa3f6'
    '/esp/EFI/UniXNU/unixnu.toml'   = 'a7c022ab15e885546e860bd7612bcf623ad3c37adc6d90d5cf5100384f02bdd7'
}

$Stamp  = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$OutDir = Join-Path $Lab ('host-setup\' + $Stamp)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Start-Transcript -Path (Join-Path $OutDir 'transcript.txt') | Out-Null

$Report = [ordered]@{
    utc = $Stamp; lab = $Lab; tools = [ordered]@{}; repos = [ordered]@{}; backups = [ordered]@{};
    twrp = [ordered]@{}; usb = @(); fastboot = [ordered]@{}; recovery = [ordered]@{}; esp = [ordered]@{};
    issues = @(); device_writes = 'none'
}
function Note([string]$m) { Write-Host ('[nabu] ' + $m) }
function Issue([string]$m) { Write-Host ('[nabu][ISSUE] ' + $m) -ForegroundColor Yellow; $script:Report.issues += $m }

function Update-PathFromRegistry {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = $machine + ';' + $user
}

# Runs a native tool with a hard timeout; returns code/stdout/stderr. Never throws.
function Invoke-Tool([string]$Exe, [string[]]$Arguments, [int]$TimeoutSec = 30) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe
    $quoted = @()
    foreach ($a in $Arguments) { if ($a -match '[\s"]') { $quoted += ('"' + ($a -replace '"', '\"') + '"') } else { $quoted += $a } }
    $psi.Arguments = $quoted -join ' '
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    try { $p = [System.Diagnostics.Process]::Start($psi) } catch {
        return [pscustomobject]@{ Code = -2; Out = ''; Err = $_.Exception.Message; Text = $_.Exception.Message }
    }
    $o = $p.StandardOutput.ReadToEndAsync()
    $e = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit($TimeoutSec * 1000)) {
        try { $p.Kill() } catch {}
        return [pscustomobject]@{ Code = -1; Out = ''; Err = 'TIMEOUT'; Text = 'TIMEOUT' }
    }
    $p.WaitForExit()
    return [pscustomobject]@{ Code = $p.ExitCode; Out = $o.Result.Trim(); Err = $e.Result.Trim(); Text = ($o.Result + "`n" + $e.Result).Trim() }
}

# ---------------------------------------------------------------- 1. tools
Note 'Step 1/4: development tools'
if (Get-Command winget -ErrorAction SilentlyContinue) {
    foreach ($id in @('Git.Git', 'Python.Python.3.12', 'GitHub.cli')) {
        Note ('winget install ' + $id)
        $r = Invoke-Tool 'winget' @('install', '--id', $id, '-e', '--silent', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity') 900
        $Report.tools[$id] = $r.Code
    }
} else {
    Issue 'winget not found: open Microsoft Store, update "App Installer", then rerun this script.'
}
Update-PathFromRegistry

$Dl = Join-Path $Lab 'downloads'
New-Item -ItemType Directory -Force -Path $Dl | Out-Null
$pt = Join-Path $Lab 'platform-tools'
try {
    $zip = Join-Path $Dl 'platform-tools-latest-windows.zip'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip' -OutFile $zip
    if (Test-Path $pt) { Remove-Item -Recurse -Force $pt }
    Expand-Archive -Path $zip -DestinationPath $Lab -Force
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($userPath -notlike ('*' + $pt + '*')) { [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $pt), 'User') }
    Update-PathFromRegistry
} catch { Issue ('platform-tools download failed: ' + $_.Exception.Message) }
$Adb = Join-Path $pt 'adb.exe'
$Fb  = Join-Path $pt 'fastboot.exe'
if (Test-Path $Adb) { $Report.tools['adb'] = (Invoke-Tool $Adb @('version')).Out.Split("`n")[0] } else { Issue 'adb.exe missing' }
if (Test-Path $Fb)  { $Report.tools['fastboot'] = (Invoke-Tool $Fb @('--version')).Out.Split("`n")[0] } else { Issue 'fastboot.exe missing' }

try {
    $uzip = Join-Path $Dl 'usb_driver_r13-windows.zip'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://dl.google.com/android/repository/usb_driver_r13-windows.zip' -OutFile $uzip
    $udir = Join-Path $Lab 'usb_driver'
    Expand-Archive -Path $uzip -DestinationPath $Lab -Force
    $inf = Get-ChildItem -Path $udir -Filter 'android_winusb.inf' -Recurse | Select-Object -First 1
    $r = Invoke-Tool 'pnputil.exe' @('/add-driver', $inf.FullName, '/install') 120
    $Report.tools['google_usb_driver'] = $r.Code
    Note $r.Text
} catch { Issue ('Google USB driver install failed: ' + $_.Exception.Message) }

$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
    $Report.tools['python'] = (Invoke-Tool $py.Source @('--version')).Text
    Invoke-Tool $py.Source @('-m', 'pip', 'install', '--upgrade', 'pip', 'pyfatfs') 600 | Out-Null
} else { Issue 'python not on PATH after install (open a new shell and rerun)' }

# ---------------------------------------------------------------- 2. repositories
Note 'Step 2/4: repositories'
$git = (Get-Command git -ErrorAction SilentlyContinue)
$Repo = Join-Path $Lab 'nabu-ipados-macos-build'
$Ref  = Join-Path $Lab 'UniXNU-nabu'
if ($git) {
    $g = $git.Source
    if (-not (Test-Path (Join-Path $Repo '.git'))) {
        Note 'Cloning the private repository - a GitHub sign-in window may open once.'
        $r = Invoke-Tool $g @('clone', '--branch', $RepoBranch, $RepoUrl, $Repo) 1800
        if ($r.Code -ne 0) { Issue ('clone failed: ' + $r.Text) }
    } else { Invoke-Tool $g @('-C', $Repo, 'fetch', 'origin') 600 | Out-Null }
    $anc = Invoke-Tool $g @('-C', $Repo, 'merge-base', '--is-ancestor', $RepoCommit, 'HEAD')
    $Report.repos['build_head'] = (Invoke-Tool $g @('-C', $Repo, 'rev-parse', 'HEAD')).Out
    $Report.repos['contains_473cdbb'] = ($anc.Code -eq 0)
    if ($anc.Code -ne 0) { Issue 'build repo HEAD does not contain 473cdbb' }

    if (-not (Test-Path (Join-Path $Ref '.git'))) { Invoke-Tool $g @('clone', $RefUrl, $Ref) 1800 | Out-Null }
    Invoke-Tool $g @('-C', $Ref, 'checkout', '-q', $RefCommit) | Out-Null
    $Report.repos['UniXNU-nabu_head'] = (Invoke-Tool $g @('-C', $Ref, 'rev-parse', 'HEAD')).Out
} else { Issue 'git not on PATH after install (open a new shell and rerun)' }

# ---------------------------------------------------------------- 3. backups + TWRP image
Note 'Step 3/4: external backups and the verified TWRP image (read-only search)'
$roots = @()
foreach ($d in (Get-PSDrive -PSProvider FileSystem)) {
    foreach ($name in @('NABU_IPADOS_COMPLETE_BACKUP_20261107', 'NABU_IPADOS_RECOVERY_20261106')) {
        $p = Join-Path $d.Root $name
        if (Test-Path $p) { $roots += $p; $Report.backups[$p] = 'found' }
    }
}
if ($roots.Count -eq 0) { Issue 'No external backup folder found on any drive. Connect the external backup disk (F:) and rerun. Do NOT format it.' }
foreach ($p in $roots) {
    $driveRoot = (Split-Path -Qualifier $p)
    $check = Join-Path $Repo 'scripts\CHECK_NABU_AFTER_KERNELOS.ps1'
    if ((Test-Path $check) -and ($p -like '*COMPLETE_BACKUP*')) {
        try { & $check -ExternalDrive $driveRoot *>&1 | Out-File (Join-Path $OutDir 'backup-check.txt') } catch { Issue ('backup check failed: ' + $_.Exception.Message) }
    }
}
$twrpDest = Join-Path $Lab ('boot-preflight\' + $TwrpName)
New-Item -ItemType Directory -Force -Path (Split-Path $twrpDest) | Out-Null
$searchRoots = @($roots) + @((Join-Path $env:USERPROFILE 'Downloads'))
$found = $null
foreach ($sr in $searchRoots) {
    if ($found -or -not (Test-Path $sr)) { continue }
    $cands = Get-ChildItem -Path $sr -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -eq $TwrpSize }
    foreach ($c in $cands) {
        if ((Get-FileHash -Algorithm SHA256 -Path $c.FullName).Hash.ToLower() -eq $TwrpSha) { $found = $c.FullName; break }
    }
}
if ($found) {
    Copy-Item -Path $found -Destination $twrpDest -Force
    $ok = ((Get-FileHash -Algorithm SHA256 -Path $twrpDest).Hash.ToLower() -eq $TwrpSha)
    $Report.twrp = [ordered]@{ source = $found; path = $twrpDest; sha256_ok = $ok }
} else {
    $Report.twrp = [ordered]@{ found = $false }
    Issue 'Verified TWRP image (41,598,976 bytes, sha256 7a71da69...) not found. Fastboot checks still run; TWRP will not be booted.'
}

# ---------------------------------------------------------------- 4. device (read-only)
function Get-NabuUsb {
    Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -match 'VID_(18D1|2717)' } |
        Select-Object FriendlyName, Status, Class, InstanceId
}
function Save-Usb([string]$label) {
    $list = @(Get-NabuUsb)
    foreach ($u in $list) { $script:Report.usb += [ordered]@{ at = $label; name = $u.FriendlyName; status = [string]$u.Status; class = $u.Class; id = $u.InstanceId } }
    foreach ($u in $list) { if ([string]$u.Status -ne 'OK') { Issue ('USB device without working driver at ' + $label + ': ' + $u.InstanceId) } }
}
function Sh([string]$cmd, [int]$t = 90) { return (Invoke-Tool $Adb @('-s', $Serial, 'shell', $cmd) $t).Out }

if (-not $NoDevice -and (Test-Path $Adb) -and (Test-Path $Fb)) {
    Note 'Step 4/4: device checks (read-only).'
    Note 'If the tablet is frozen on coloured bars: hold POWER + VOLUME DOWN until the Fastboot screen appears, then connect USB.'
    Invoke-Tool $Adb @('start-server') | Out-Null
    $deadline = (Get-Date).AddMinutes($WaitMinutes)
    $mode = $null
    while ((Get-Date) -lt $deadline) {
        $st = (Invoke-Tool $Adb @('-s', $Serial, 'get-state') 10).Out
        if ($st -eq 'recovery') { $mode = 'recovery'; break }
        $fd = (Invoke-Tool $Fb @('devices') 10).Out
        if ($fd -match $Serial) { $mode = 'fastboot'; break }
        Start-Sleep -Seconds 3
    }
    Save-Usb 'first-contact'
    if (-not $mode) { Issue ('Tablet not seen in Fastboot or recovery within ' + $WaitMinutes + ' minutes.') }

    if ($mode -eq 'fastboot') {
        foreach ($v in @('product', 'unlocked', 'current-slot', 'serialno', 'slot-count')) {
            $r = Invoke-Tool $Fb @('-s', $Serial, 'getvar', $v) 20
            $line = ($r.Text -split "`n" | Where-Object { $_ -match ('^' + [regex]::Escape($v) + ':') } | Select-Object -First 1)
            $Report.fastboot[$v] = if ($line) { ($line -split ':', 2)[1].Trim() } else { $r.Text }
        }
        if ($Report.fastboot['product'] -ne 'nabu') { Issue ('Fastboot product is not nabu: ' + $Report.fastboot['product']) }
        elseif ($NoTwrpBoot -or -not ($Report.twrp.sha256_ok)) { Note 'Skipping TWRP RAM boot.' }
        else {
            Note 'RAM-booting the verified TWRP (fastboot boot, nothing is flashed).'
            $r = Invoke-Tool $Fb @('-s', $Serial, 'boot', $twrpDest) 90
            $Report.fastboot['twrp_ram_boot'] = $r.Text
            $deadline2 = (Get-Date).AddSeconds(150)
            while ((Get-Date) -lt $deadline2) {
                if ((Invoke-Tool $Adb @('-s', $Serial, 'get-state') 10).Out -eq 'recovery') { $mode = 'recovery'; break }
                Start-Sleep -Seconds 3
            }
            Save-Usb 'after-twrp-boot'
            if ($mode -ne 'recovery') { Issue 'TWRP did not appear on ADB after RAM boot (see usb entries for driver state).' }
        }
    }

    if ($mode -eq 'recovery') {
        $Report.recovery['device'] = Sh 'getprop ro.product.device'
        $Report.recovery['id']     = Sh 'id'
        $Report.recovery['battery_percent'] = Sh 'cat /sys/class/power_supply/battery/capacity'
        $Report.recovery['mem_total'] = Sh 'grep MemTotal /proc/meminfo'
        $Report.recovery['slot_suffix'] = Sh 'getprop ro.boot.slot_suffix'
        Sh 'sgdisk --print /dev/block/sda 2>/dev/null || cat /proc/partitions; ls -l /dev/block/bootdevice/by-name/' 60 | Out-File -Encoding ascii (Join-Path $OutDir 'partitions-sda.txt')
        if ($Report.recovery['device'] -ne 'nabu' -or $Report.recovery['id'] -notmatch 'uid=0\(root\)') {
            Issue 'Recovery is not root nabu; ESP checks skipped.'
        } elseif ((Sh ('blockdev --getsize64 ' + $EspDev)) -ne $EspSize) {
            Issue 'ESP block device size unexpected; ESP checks skipped.'
        } else {
            Sh ('sync; umount /esp 2>/dev/null; blockdev --setro ' + $EspDev) | Out-Null
            $Report.esp['blockdev_ro'] = Sh ('blockdev --getro ' + $EspDev)
            if ($Report.esp['blockdev_ro'] -eq '1') {
                Sh ('mkdir -p /esp; mount -t vfat -o ro ' + $EspDev + ' /esp') | Out-Null
                $mnt = Sh "grep ' /esp ' /proc/mounts"
                $Report.esp['mount'] = $mnt
                if ($mnt -match ' ro,') {
                    $hashes = [ordered]@{}
                    foreach ($k in $Expected.Keys) {
                        $h = (Sh ('sha256sum ' + $k)).Split(' ')[0]
                        $hashes[$k] = [ordered]@{ actual = $h; matches_combined_install = ($h -eq $Expected[$k]) }
                    }
                    $Report.esp['installed'] = $hashes
                    Sh 'ls -la /esp/EFI/UniXNU /esp/EFI/UniXNU/Payloads /esp' | Out-File -Encoding ascii (Join-Path $OutDir 'esp-listing.txt')
                    $raw = Join-Path $OutDir 'XNU2LOG.BIN'
                    $r = Invoke-Tool $Adb @('-s', $Serial, 'pull', '/esp/XNU2LOG.BIN', $raw) 180
                    if (Test-Path $raw) {
                        $Report.esp['log_sha256'] = (Get-FileHash -Algorithm SHA256 -Path $raw).Hash.ToLower()
                        if ($py -and (Test-Path (Join-Path $Ref 'tools\nabu_log_volume.py'))) {
                            $dec = Join-Path $OutDir 'decode_log.py'
                            Set-Content -Encoding ascii -Path $dec -Value @(
                                'import sys, json',
                                ('sys.path.insert(0, r"' + (Join-Path $Ref 'tools') + '")'),
                                'from nabu_log_volume import decode_container',
                                'payload, info = decode_container(open(sys.argv[1], "rb").read())',
                                'open(sys.argv[2], "w", encoding="utf-8").write(payload.decode("utf-8", "replace"))',
                                'print(json.dumps(info, default=str))')
                            $d = Invoke-Tool $py.Source @('-I', $dec, $raw, (Join-Path $OutDir 'boot-log.txt')) 120
                            $Report.esp['log_container'] = $d.Text
                        }
                    } else { Issue ('XNU2LOG.BIN pull failed: ' + $r.Text) }
                    Sh 'umount /esp' | Out-Null
                } else { Issue 'ESP did not mount read-only; nothing read.' }
            } else { Issue 'Could not set ESP block device read-only; ESP not mounted.' }
            $Report.esp['blockdev_ro_after'] = Sh ('blockdev --getro ' + $EspDev)
        }
        Note 'Tablet left in TWRP (RAM). Nothing was written.'
    }
}

$reportPath = Join-Path $OutDir 'host-setup-report.json'
$Report | ConvertTo-Json -Depth 8 | Out-File -Encoding utf8 $reportPath
Stop-Transcript | Out-Null
Write-Host ''
Write-Host ('DONE. Send these files back to Claude:') -ForegroundColor Green
Write-Host ('  ' + $reportPath)
Write-Host ('  ' + (Join-Path $OutDir 'boot-log.txt') + '  (if present)')
Write-Host ('  ' + (Join-Path $OutDir 'partitions-sda.txt') + '  (if present)')
if ($Report.issues.Count -gt 0) { Write-Host ('Issues: ' + $Report.issues.Count + ' (listed in the report)') -ForegroundColor Yellow }

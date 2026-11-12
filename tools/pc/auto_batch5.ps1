param([Parameter(Mandatory=$true)][string]$KernelRun, [Parameter(Mandatory=$true)][string]$CacheRun)
# Batch 5 (PC side): launchd-cache + AppSync kernel, wland/netsvc, owner launchd caches, AppSync runtime, Wi-Fi
# firmware, optional wlan.conf (host-setup\wifi-secret, never in git) and IPAs (host-setup\ipa). Built from the batch-2
# addon/trust base; installs over batch 3 with backups .pre-batch5-20261112; boots; waits for the log.
$L = Join-Path $env:USERPROFILE 'Desktop\NABU_IPADOS_LAB'
$R = "$L\nabu-ipados-macos-build"
$adb = "$L\platform-tools\adb.exe"
$o = "$L\host-setup\batch5"; New-Item -ItemType Directory -Force $o | Out-Null
function W($m) { ((Get-Date).ToString('HH:mm:ss') + ' ' + $m) | Tee-Object -Append "$o\auto.log" }
function Sha($f) { (Get-FileHash -Algorithm SHA256 $f).Hash.ToLower() }
function Install($file, $target, $old, $suffix) {
  $s = [IO.File]::ReadAllText("$L\tablet_install_file.sh") -replace "`r", ""
  [IO.File]::WriteAllText("$o\install_file.sh", $s)
  & $adb -s 33288984 push "$o\install_file.sh" /tmp/install_file.sh *> $null
  & $adb -s 33288984 push $file /tmp/new.file *> $null
  $r = & $adb -s 33288984 shell sh /tmp/install_file.sh $target $old (Sha $file) $suffix 2>&1
  W ("$target -> " + ($r -join ' | ')) | Out-Null
  return (($r -join "`n") -match 'INSTALL_READBACK_PASS')
}
W "batch 4 start kernel=$KernelRun cache=$CacheRun"
foreach ($id in $KernelRun, $CacheRun) {
  $c = (gh run view $id -R milazy/nabu-ipados-port --json conclusion --jq .conclusion 2>$null | Out-String).Trim()
  if ($c -ne 'success') { W "run $id is not a success ($c); stop"; exit 1 }
}
git -C $R fetch -q origin main; git -C $R checkout -q -B main origin/main; W ('repo ' + (git -C $R log --oneline -1))

& powershell -NoProfile -ExecutionPolicy Bypass -File "$L\fetch_artifact2.ps1" -RunId $CacheRun -Name nabu-launchd-cache 2>&1 | Out-Null
$ca = "$L\build-artifacts\run-$CacheRun-nabu-launchd-cache"
if (-not (Test-Path "$ca\out\cache-iconfix-appsync\launchd.plist")) { W 'cache artifact incomplete; stop'; exit 1 }
& powershell -NoProfile -ExecutionPolicy Bypass -File "$L\fetch_artifact2.ps1" -RunId $KernelRun -Name nabu-integrated-ui-build 2>&1 | Out-Null
$art = "$L\build-artifacts\run-$KernelRun-nabu-integrated-ui-build"
$kin = Get-ChildItem -Recurse -File $art | Where-Object { $_.FullName -match 'unixnu-final\\out\\nabu\\kernel\\kernel\.macho$' } | Select-Object -First 1
if (-not $kin) { W 'final kernel.macho not found; stop'; exit 1 }
$cf = "$L\build-artifacts\nabu-metal-checkfix-20261111"
$kout = "$L\build-artifacts\nabu-stack-$KernelRun"; if (Test-Path $kout) { Remove-Item -Recurse -Force $kout }
python "$R\ci\prepare_stack_kernel.py" --kernel $kin.FullName --layout-report "$art\output\final-display-reference-validation.json" `
  --addon "$cf\kernel-metal-checkfix.macho.gpuaddon" --trustcache "$cf\kernel-metal-checkfix.macho.trustcache" --run-id $KernelRun --out $kout 2>&1 | ForEach-Object { W $_ }
$k = "$kout\kernel-batch1.macho"
if (-not (Test-Path $k)) { W 'prepared kernel missing; stop'; exit 1 }
foreach ($m in 'NABU LAUNCHD cache mode=', 'NABU APPSYNC library=', '[appsync-trust] loaded user code') {
  if (-not (Select-String -Path $k -SimpleMatch $m -Quiet)) { W "kernel lacks '$m'; stop"; exit 1 }
}

$a0 = "$L\host-setup\batch2\kernel-fulltrace-panic.macho.gpuaddon"
$t0 = "$L\host-setup\batch2\payload\kernel-metal-gmem.macho.trustcache"
if ((Sha $a0) -ne 'f9ee94ada643dad45d24b2e3a573b284135a780f165b4f5dba25eec0878bd627' -or (Sha $t0) -ne '36d9c1ee2a23bfead27bd447d5e95c5c9e083835cd69ca838ea120b9154e43bc') { W 'batch-2 addon/trust inputs changed; stop'; exit 1 }
python "$R\tools\batch4_payload.py" --cache-art $ca --firmware "$L\host-setup\wifi-firmware\wififw" --wlan-conf "$L\host-setup\wifi-secret\wlan.conf" `
  --ipa-dir "$L\host-setup\ipa" --out "$o\members.json" 2>&1 | ForEach-Object { W $_ }
$mj = Get-Content "$o\members.json" -Raw | ConvertFrom-Json
$pay = "$o\payload"; if (Test-Path $pay) { Remove-Item -Recurse -Force $pay }
$argsList = @("$R\tools\addon_add_payload.py", '--addon', $a0, '--trustcache', $t0, '--out', $pay, '--label', 'nabu-batch5')
foreach ($h in $mj.cdhashes) { $argsList += @('--cdhash', $h) }
foreach ($f in $mj.files) { $argsList += @('--file', $f) }
python @argsList 2>&1 | Select-String 'ADDON_PAYLOAD|STOP|Error' | ForEach-Object { W $_.Line }
$addon = "$pay\kernel-fulltrace-panic.macho.gpuaddon"; $tc = "$pay\kernel-fulltrace-panic.macho.trustcache"
if (-not ((Test-Path $addon) -and (Test-Path $tc))) { W 'payload not prepared; stop'; exit 1 }
python "$R\tools\pc\make_menu_batch5.py" 2>&1 | ForEach-Object { W $_ }
$menu = "$o\unixnu.toml"
W ("ready: kernel " + (Sha $k) + " addon " + (Sha $addon) + " (" + (Get-Item $addon).Length + " bytes) trust " + (Sha $tc) + " menu " + (Sha $menu))

W 'waiting for the tablet in TWRP or fastboot'
for ($i = 0; $i -lt 1440; $i++) {
  if ((& $adb -s 33288984 get-state 2>$null) -eq 'recovery') { break }
  if ((& "$L\platform-tools\fastboot.exe" devices) -match '33288984') {
    & "$L\platform-tools\fastboot.exe" -s 33288984 boot "$L\boot-preflight\V4-MODDED-TWRP-LINUX.img" *> $null; Start-Sleep 25
  }
  Start-Sleep 30
}
if ((& $adb -s 33288984 get-state 2>$null) -ne 'recovery') { W 'tablet not in TWRP; stop'; exit 1 }
$suf = 'pre-batch5-20261112'
if (-not (Install $addon 'kernel-fulltrace-panic.macho.gpuaddon' '2fa80ecc4f016e82de704f05374f21353e2fd5da5b60713891661107faca9749' $suf)) { W 'addon install failed; stop'; exit 1 }
if (-not (Install $tc 'kernel-fulltrace-panic.macho.trustcache' '2c3c434375f07053c8690ea517445f8520eb28f4ed315f04da54d90459cbb034' $suf)) { W 'trust install failed; stop'; exit 1 }
$s = [IO.File]::ReadAllText("$L\tablet_install_pair.sh") -replace "`r", ""
[IO.File]::WriteAllText("$o\install_pair.sh", $s)
& $adb -s 33288984 push "$o\install_pair.sh" /tmp/install_pair.sh *> $null
& $adb -s 33288984 push $k /tmp/new.kernel *> $null
& $adb -s 33288984 push $menu /tmp/new.toml *> $null
$r = & $adb -s 33288984 shell sh /tmp/install_pair.sh 40b0965ea39982790945191a45945887f48339144d8f99a351885c9e18c92c41 (Sha $k) 403dd353988990c17954ae8d8bbe5e98b94856644349ac414346df7d35c11ceb (Sha $menu) $suf 2>&1
W ($r -join ' | ')
if (-not (($r -join "`n") -match 'INSTALL_READBACK_PASS')) { W 'kernel/menu install failed; stop'; exit 1 }
W 'BATCH5_INSTALLED'
& powershell -NoProfile -ExecutionPolicy Bypass -File "$L\boot_uefi.ps1" 2>&1 | ForEach-Object { W $_ }
Start-Sleep 90
& powershell -NoProfile -ExecutionPolicy Bypass -File "$L\wait_and_pull_log.ps1" -Name tablet-batch5 -Minutes 720

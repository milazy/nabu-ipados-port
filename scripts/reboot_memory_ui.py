"""Read back the installed memory/UI repair and request one authorized reboot."""
import argparse, datetime, hashlib, json, subprocess
from pathlib import Path
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--root', type=Path, required=True)
p.add_argument('--serial', required=True)
a = p.parse_args()
out = a.root / 'build-artifacts/nabu-memory-ui-20261110'
receipt = json.loads((out / 'install-receipt.json').read_text())
assert receipt['status'] == 'MEMORY_UI_INSTALL_PASS_BOOT_UNVERIFIED'
assert not (out / 'reboot-receipt.json').exists(), 'Reboot already recorded'
def adb(*args):
    r = subprocess.run([str(a.root / 'platform-tools/adb.exe'), '-s', a.serial, *args], capture_output=True, text=True, timeout=180)
    if r.returncode: raise RuntimeError(r.stderr[-500:])
    return r.stdout.strip()
assert adb('get-state') == 'recovery'
assert adb('shell', 'getprop ro.product.device') == 'nabu'
assert adb('shell', 'blockdev --getro /dev/block/sda29') == '1'
assert ' ro,' in adb('shell', "cat /proc/mounts | grep ' /esp '")
k = '/esp/EFI/UniXNU/Payloads/kernel-fulltrace-panic.macho'
expected = {k: receipt['kernel_sha256'], k + '.adt': receipt['adt_sha256'], '/esp/EFI/UniXNU/unixnu.toml': receipt['menu_sha256'], **receipt['protected_payloads_verified']}
for path, digest in expected.items():
    assert adb('shell', 'sha256sum ' + path).split()[0] == digest, 'Readback mismatch: ' + path
result = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'status': 'FINAL_READBACK_PASS_REBOOT_REQUEST_ACCEPTED_UI_UNVERIFIED', 'verified_sha256': expected, 'ESP_readonly_before_reboot': True, 'boot_verified': False, 'firmware_allocation_proven': False}
adb('reboot')
(out / 'reboot-receipt.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))

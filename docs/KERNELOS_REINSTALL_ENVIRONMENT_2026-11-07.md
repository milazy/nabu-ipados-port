# KernelOS Windows reinstallation: recovered Pad 5 development environment

Recorded 2026-11-07 following Windows/KernelOS reinstallation.

## Local recovery

- External archive: `F:\NABU_IPADOS_COMPLETE_BACKUP_20261107\NABU_IPADOS_LAB`, file-count 32390, total 40,374,431,865 bytes.
- Separate original tablet recovery folder: `F:\NABU_IPADOS_RECOVERY_20261106` (not overwritten).
- Restored workspace: `C:\Users\Giacomo\Desktop\NABU_IPADOS_LAB`.
- Robocopy restore finished with **32390 files copied, 0 failed, 0 size mismatches**, 37.601 GiB in log.
- A separate SHA-256 byte-for-byte audit of C: against F: was launched, writing `F:\NABU_IPADOS_COMPLETE_BACKUP_20261107\VERIFICATION_REPORT.json` and `BACKUP_COMPLETE_AND_VERIFIED.txt` if and only if it passes. **Do not claim the audit has passed until that report exists with result=PASS.**
- Earlier F: backup lacked its original verification marker after Windows reinstall; therefore restore verification was deliberately performed from the new OS.
- Restored local source state: `UniXNU-nabu` commit `54b4f98` had many uncommitted modifications; `UniXNU-pinned` `245aca1` had local changes. Preserve both; do not reset or clean. Local private `nabu-ipados-macos-build` checkout remained at `c7e2855` (behind the latest remote branch); fetch after GitHub CLI login, don't overwrite uncommitted work.

## Installed and tested developer tooling

- Git for Windows **2.56.0.4**, including Git LFS **3.8.1**.
- Python **3.13.17**, pip **26.2.2**, at `C:\Program Files\Python313\python.exe`.
- GitHub CLI **2.103.3**: installed, requires browser-based `gh auth login` before pushing/pulling private repo. Desktop launcher `LOGIN_GITHUB_FOR_NABU.cmd`.
- OpenAI Codex CLI **0.167.0** (official `@openai/codex`): installed and **logged in using ChatGPT**, plus official `OpenAI.chatgpt` VS Code extension.
- Node.js **24.22.2**, npm **11.19.1** (already present).
- Android SDK Platform-Tools **37.0.2**: adb, fastboot on user's PATH.
- VS Code **1.143.1** + official Codex, Microsoft Python/Pylance, C/C++, PowerShell extensions.
- QEMU ARM64 **11.1.0** with `virt` machine and `C:\Program Files\qemu\share\edk2-aarch64-code.fd`.
- LLVM/Clang **23.1.5**, including llvm-readobj; CMake **4.4.4**; Ninja **1.13.2**.
- 7-Zip **26.02**, WinUSB driver tool Zadig **2.9**; Windows built-in SSH client.
- Machine PATH expanded only to `C:\Program Files\LLVM\bin` and `C:\Program Files\qemu`, with binary version checks passing.
- These tools support local host testing, assembly, emulation, image inspections and Codex. **Full source-based XNU target builds still need macOS/Xcode or properly provisioned GitHub macOS runners.**

## Fastboot USB driver installed and verified

- Exact physically detected USB device `VID_18D1&PID_D00D` in Fastboot.
- Initially Windows PnP Code 28, driver not installed; old official Google USB INF in archive does not match D00D.
- Installed official signed Zadig/WinUSB (libwdi) **only for this device**. Zadig generated a random WinUSB `DeviceInterfaceGUIDs`; official Android Fastboot expects GUID `{F72FE0D4-CBCB-407D-8814-9ED673D0DD6B}` in addition to the random GUID. Added Android GUID for this *exact* USB devnode without removing its existing GUID and restarted only that device. Backed up registry key to Desktop `FASTBOOT_D00D_BEFORE_GUID_FIX.reg`.
- Verified `fastboot devices -l` recognizes the device; read-only `fastboot getvar product` reports `nabu`, `getvar current-slot` reports `b`, and `getvar unlocked` reports `yes`.
- **No boot/reboot, flash, erase, filesystem write, partition modification, firmware downgrade or physical iPadOS test was performed.**
- Android recovery/ADB-mode might expose a different USB ID, so verify its driver separately *when user intentionally boots that mode*; do not preinstall unrelated random Qualcomm driver packs.

## Pinned clean source checkouts — never overwrite modified original

Created `C:\Users\Giacomo\Desktop\NABU_IPADOS_REFERENCES`:

| Clean local checkout | Pinned revision |
|---|---|
| `UniXNU-nabu-clean` | `54b4f98457f8e9e232cc0a077c20d08d0b2f0ac9` |
| `UniXNU-core-owner-pin` | `245aca1a9ec5b730b1cad80fade295800d2981f1` |
| `Bergamota` | `37a7a7a917fc09945ed2f7d1ae68b84d4525b4cb` |
| `HakiOS-XNU` | `63fc2b4633bac3af8e57dadab9f5a8d4cb940438` |
| `HakiOS-iOS26-dada` | `f1ae906fcc43ba8f763663257724ba938fb820ab` |

All five clones completed and `git rev-parse HEAD` matched the pinned SHA. Local `SOURCE_PIN_VERIFICATION.json` contains details.

## Desktop helpers

- `START_NABU_CODEX.cmd`: opens project in Codex CLI only after restore SHA marker and AGENTS handoff exist.
- `LOGIN_GITHUB_FOR_NABU.cmd`: GitHub web authorization, user completes with own account.
- `CHECK_NABU_SETUP.cmd`: read-only versions, repos and USB check.
- `NABU_CODEX_PROJECT_INSTRUCTIONS.md`: staged AGENTS guidance; install as `NABU_IPADOS_LAB\AGENTS.md` after SHA verification.
- `NABU_VERIFY_RESTORED_AFTER_COPY.ps1`: independent checksum audit.
- `NABU_CLONE_PINNED_REFERENCES.ps1`: rebuilds pinned public source mirrors without overwriting existing clones.

## Critical next steps

1. Verify F: SHA report and completion marker; then activate AGENTS and Codex launcher.
2. Finish interactive GitHub CLI login via normal browser, not API token passed in chat.
3. Safely fetch private GitHub main and inspect changes; do not reset existing modified source.
4. Fix GitHub Actions runner provisioning (past workflows failed before steps started), or use a macOS/Xcode build host.
5. Continue with genuine iPadOS 17.7 source integration and complete UFS OS/SystemOS root. Use HakiOS/Bergamota as architecture and implementation references; no blind cross-device kernel copying.
6. Identify actual nabu 120Hz panel variant, implement real vblank/refresh and test separately from simple iPad Pro identity.
7. Preserve F: and Android. No flash until full owner-specific partition and backup safeguards are checked and explicit user approval for destructive changes is obtained.

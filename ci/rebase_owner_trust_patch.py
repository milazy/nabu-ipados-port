#!/usr/bin/env python3
"""Rebase the source owner's second trust-cache patch onto pinned Apple XNU.

Unlike the bootstrap build, owner-verified OS+SystemOS boot requires this patch.
Fail closed unless both the input patch digest and output digest match pins.
This changes CI source staging only, not the tablet.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

BEFORE = "d4a043f6673eaaab4befc174fd701b473f1bb9db7dced3df35d01c1e12dfd818"
AFTER = "22bdb693b2ce3c1176ee3aafb01ff2767874bf1192ae4f0ff8908269c59d54c3"
OLD = b"#  VM_KASAN =       [ VM_BASE config_kasan config_ubsan config_kcov config_ksancov ]"
NEW = b"#  VM_KASAN =       [ VM_BASE dynamic_codesigning kernel_tagging kernel_tbi config_kasan config_ubsan config_kcov config_ksancov ]"
def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--patch", type=Path, required=True)
    a=p.parse_args()
    raw=a.patch.read_bytes()
    if digest(raw)!=BEFORE or raw.count(OLD)!=1:
        raise RuntimeError("Unexpected second-trust-cache patch revision; refusing to alter source")
    fixed=raw.replace(OLD, NEW)
    if digest(fixed)!=AFTER:
        raise RuntimeError("Rebased second-trust-cache patch did not match reviewed digest")
    a.patch.write_bytes(fixed)
    print("OWNER_SECOND_STATIC_TRUST_CACHE_PATCH_SHA256="+AFTER)
    print("OWNER_TRUST_CACHE_DISABLE_ALLOWED=false")
if __name__=="__main__":
    main()

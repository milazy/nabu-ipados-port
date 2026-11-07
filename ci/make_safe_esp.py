#!/usr/bin/env python3
"""Build a reversible, NON-iPadOS FAT32 EFI self-test image for Xiaomi Pad 5.

The output is a regular host image; this tool never accesses the device.
The test menu has no XNU kernel entry or auto-install action.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from pyfatfs.PyFat import PyFat
from pyfatfs.PyFatFS import PyFatFS

SHA_PINS = {
    "UniXNU.efi": "f08f187a21e5b9b874f8de6bc3c3104bd200efe4ab2e7b1c630afd3079fc8f20",
    "DarwinBoot.efi": "029d2164702c82b36bebaf56e0e6725efaa25b262e7176ae7f32144faea44acd",
    "HelloPayload.efi": "ab73ac58e66ad3c4b565cac0d53f7da4edb9fc02bd7bbc53c1cf1c1eca0de99a",
}
MAX_CUST_BYTES = 1_073_741_824
def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_arm64_efi(path: Path) -> bytes:
    data=path.read_bytes()
    if data[:2] != b"MZ" or len(data) < 512:
        raise RuntimeError(f"Expected Windows PE/COFF EFI binary: {path}")
    offset=struct.unpack_from("<I", data, 60)[0]
    if data[offset:offset+4] != b"PE\\0\\0".decode("unicode_escape").encode("latin1"):
        raise RuntimeError("Missing PE header")
    arch=struct.unpack_from("<H",data,offset+4)[0]
    if arch != 0xAA64: raise RuntimeError("Expected ARM64 EFI executable")
    if sha(data)!=SHA_PINS[path.name]:
        raise RuntimeError("EFI source does not match pinned release hash: "+path.name)
    return data

def synchronize_fat32_fsinfo(image: Path) -> int:
    # pyfatfs 1.1.0 does not update the FSInfo free-cluster advisory when
    # adding files. Recount from the actual FAT, and repair both FSInfo copies
    # before external fsck.fat validates the image.
    with image.open("r+b") as f:
        bpb=f.read(512)
        bps=struct.unpack_from("<H",bpb,11)[0]
        spc=bpb[13]
        reserved=struct.unpack_from("<H",bpb,14)[0]
        copies=bpb[16]
        total=struct.unpack_from("<I",bpb,32)[0]
        fat_sectors=struct.unpack_from("<I",bpb,36)[0]
        fsinfo_sector=struct.unpack_from("<H",bpb,48)[0]
        backup_boot=struct.unpack_from("<H",bpb,50)[0]
        if bps!=512 or spc==0 or copies!=2 or fsinfo_sector!=1 or backup_boot!=6:
            raise RuntimeError("Unexpected FAT32 volume parameters")
        clusters=(total-reserved-copies*fat_sectors)//spc
        f.seek(reserved*bps)
        fat=f.read(fat_sectors*bps)
        if len(fat)<(clusters+2)*4:
            raise RuntimeError("FAT table truncated")
        free=0
        next_free=0xffffffff
        for cluster in range(2,clusters+2):
            value=struct.unpack_from("<I",fat,cluster*4)[0] & 0x0fffffff
            if value==0:
                free+=1
                if next_free==0xffffffff:
                    next_free=cluster
        # pyfatfs does not populate legacy BIOS geometry. mtools refuses
        # to read a FAT volume with both heads/sectors set to zero.
        # Set conventional CHS hints in primary and backup boot sectors;
        # this does not alter the FAT32 LBA geometry.
        for boot_sector in (0,backup_boot):
            f.seek(boot_sector*bps+24)
            f.write(struct.pack("<HH",63,255))
        for sector in (fsinfo_sector,backup_boot+fsinfo_sector):
            f.seek(sector*bps)
            data=f.read(bps)
            if struct.unpack_from("<I",data,0)[0]!=0x41615252 or struct.unpack_from("<I",data,484)[0]!=0x61417272:
                raise RuntimeError("Invalid FAT32 FSInfo signatures")
            f.seek(sector*bps+488)
            f.write(struct.pack("<II",free,next_free))
        f.flush()
    return free

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--bootloader",type=Path,required=True)
    ap.add_argument("--darwinboot",type=Path,required=True)
    ap.add_argument("--hello",type=Path,required=True)
    ap.add_argument("--timeout",type=int,default=180)
    ap.add_argument("--size-mib",type=int,default=256)
    args=ap.parse_args()
    if not 64<=args.size_mib<=256:ap.error("Size must be 64..256 MiB")
    if not 1<=args.timeout<=3600:ap.error("Timeout must be 1..3600 seconds")
    dest=args.output.resolve()
    if dest.exists() or dest.is_symlink():
        raise RuntimeError("Refusing to overwrite existing image")
    if dest.suffix.lower()!=".img" or dest.name.lower().startswith(("sda","cust","rawdump")):
        raise RuntimeError("Output must be a host-only .img, not a device partition")
    if args.size_mib * 1048576 >= MAX_CUST_BYTES:
        raise RuntimeError("Test image must fit existing cust partition")
    sources={item.name:read_arm64_efi(item) for item in
             (args.bootloader,args.darwinboot,args.hello)}
    if len(sources)!=3 or set(sources)!=set(SHA_PINS):
        raise RuntimeError("Unexpected EFI inputs")
    menu=f'''# Physical nabu UEFI boot menu smoke test ONLY. No iPadOS installed.
version = 1
[boot]
timeout = {args.timeout}
default = "hello"
[ui]
title = "Pad 5 - UEFI Hardware Check"
[kits]
autoload = false
[[entry]]
id = "hello"
title = "Test UEFI (no Android changes)"
type = "efi"
path = "Payloads/HelloPayload.efi"
args = "plain shutdown"
[[entry]]
id = "reset"
title = "Restart tablet"
type = "action"
action = "reset"
[[entry]]
id = "shutdown"
title = "Power off tablet"
type = "action"
action = "shutdown"
'''
    dest.parent.mkdir(parents=True,exist_ok=True)
    # PyFat.mkfs opens an existing file in rb+ mode; preallocate the host image.
    with dest.open("xb") as blank:
        blank.truncate(args.size_mib * 1048576)
    pf=PyFat()
    pf.mkfs(str(dest), fat_type=PyFat.FAT_TYPE_FAT32,
            size=args.size_mib*1048576,sector_size=512,label="ESPNABU",
            volume_id=0x4E414255)
    pf.close()
    contents={
        "/EFI/BOOT/BOOTAA64.EFI":sources["UniXNU.efi"],
        "/EFI/UniXNU/UniXNU.efi":sources["UniXNU.efi"],
        "/EFI/UniXNU/Drivers/DarwinBoot.efi":sources["DarwinBoot.efi"],
        "/EFI/UniXNU/Payloads/DarwinBoot.efi":sources["DarwinBoot.efi"],
        "/EFI/UniXNU/Payloads/HelloPayload.efi":sources["HelloPayload.efi"],
        "/EFI/UniXNU/unixnu.toml":menu.encode("ascii"),
        "/README.TXT":b"This is a temporary UEFI SELF TEST, not an iPadOS installation.\r\n",
    }
    fs=PyFatFS(str(dest))
    try:
        for directory in ("/EFI","/EFI/BOOT","/EFI/UniXNU",
                          "/EFI/UniXNU/Drivers","/EFI/UniXNU/Payloads"):
            fs.makedirs(directory,recreate=True)
        for path,payload in contents.items():
            fs.writebytes(path,payload)
    finally:
        fs.close()
    fs=PyFatFS(str(dest),read_only=True)
    try:
        for name,payload in contents.items():
            data=fs.readbytes(name)
            if data!=payload:raise RuntimeError("FAT read-back mismatch: "+name)
        if "kernel.macho" in str(fs.listdir("/EFI/UniXNU/Payloads")):
            raise RuntimeError("A kernel slipped into safe test image")
    finally:
        fs.close()
    free_clusters=synchronize_fat32_fsinfo(dest)
    with dest.open("rb") as f:
        sector=f.read(512)
    if sector[82:90]!=b"FAT32   " or sector[510:512]!=b"\\x55\\xaa".decode("unicode_escape").encode("latin1"):
        raise RuntimeError("Invalid FAT32 boot sector signature")
    if dest.stat().st_size!=args.size_mib*1048576:
        raise RuntimeError("FAT image not expected size")
    h=hashlib.sha256()
    with dest.open("rb") as f:
        while chunk:=f.read(4*1048576):h.update(chunk)
    report={
        "kind":"Xiaomi Pad 5 reversible UEFI self-test FAT32 volume",
        "image":str(dest),"bytes":dest.stat().st_size,"sha256":h.hexdigest(),
        "files":{name:{"length":len(data),"sha256":sha(data)} for name,data in contents.items()},
        "cust_original_partition_bytes":MAX_CUST_BYTES,
        "fits_in_cust":dest.stat().st_size<MAX_CUST_BYTES,
        "uefi_menu_default":"hello","menu_timeout_seconds":args.timeout,
        "contains_iPadOS":False,"contains_XNU_kernel":False,"fat32_free_clusters":free_clusters,
        "writes_to_tablet":False,"safe_to_claim_ipados_installed":False,
    }
    sidecar=dest.with_suffix(".json")
    sidecar.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("UEFI_TEST_FAT32_READY="+str(dest),flush=True)
    print("ESP_SHA256="+h.hexdigest(),flush=True)
    print("BOOT_IMAGE_READY_NOT_FLASHED=true",flush=True)

if __name__=="__main__":
    main()

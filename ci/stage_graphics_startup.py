#!/usr/bin/env python3
"""Retain prepared graphics startup code while excluding overlapping console hunks."""
import argparse
import hashlib
from pathlib import Path
import re

def stage(source, destination):
    text=source.read_text()
    selected=[]
    for section in re.split(r'(?=^--- a/)',text,flags=re.M):
        if section.startswith(('--- a/bsd/kern/bsd_init.c\n','--- a/iokit/Kernel/IOUserClient.cpp\n')):
            selected.append(section)
    if len(selected)!=2:
        raise ValueError("Expected exactly the prepared BSD startup and IOUserClient sections")
    result=''.join(selected)
    for marker in ('+nabu_graphics_start_after_root(void)','+volatile unsigned nabu_graphics_worker_stage;','+volatile int native_mobile_graphics_load_status = -1;'):
        if result.count(marker)!=1:
            raise ValueError("Missing or ambiguous prepared graphics definition: "+marker)
    if 'pexpert/arm/pe_init.c' in result or 'iokit/bsddev/IOKitBSDInit.cpp' in result:
        raise ValueError("Overlapping console patch escaped filtering")
    if destination.exists():
        raise FileExistsError(destination)
    destination.write_text(result,newline='\n')
    print("GRAPHICS_STARTUP_STAGED",hashlib.sha256(result.encode()).hexdigest())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    stage(args.input,args.output)

if __name__=='__main__':
    main()

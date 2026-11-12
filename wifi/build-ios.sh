#!/bin/sh
# Build the nabu Wi-Fi userland (wland, netsvc) for iPadOS 17 arm64, signed ad hoc (CDHashes go into the trust cache).
set -eu
cd "$(dirname "$0")"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
CC="$(xcrun -f clang) -arch arm64 -isysroot $SDK -miphoneos-version-min=17.0"
mkdir -p out
$CC -O2 -Wall -Wno-unused-parameter -Wno-unused-function -include wland/nabu_log.h -o out/wland \
  wland/wland.c wland/smem.c wland/pmem.c wland/glink.c wland/link.c wland/qrtr_mux.c wland/qmi.c wland/rmtfs.c \
  wland/pdmapper.c wland/servreg.c wland/tftp.c wland/scm.c wland/wlfw.c wland/radio.c wland/ipnet.c wland/bridge.c \
  wland/nabu_log.c
$CC -O2 -fobjc-arc -framework Foundation -framework SystemConfiguration -o out/netsvc tools/netsvc.m
codesign -f -s - out/wland
codesign -f -s - --entitlements tools/netsvc-ents.plist out/netsvc
file out/wland out/netsvc
shasum -a 256 out/wland out/netsvc

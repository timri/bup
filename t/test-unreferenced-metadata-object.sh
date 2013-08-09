#!/usr/bin/env bash
. ./wvtest-bup.sh

set -e -o pipefail

WVSTART 'all'

top="$(pwd)"
tmpdir="$(wvmktempdir)"
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

mkdir "$tmpdir/foo"
touch "$tmpdir/foo/bar"
WVPASS bup init
WVPASS bup index "$tmpdir/foo"
WVPASS bup save -n foo "$tmpdir/foo"
# we should not have any unreachble objects:
(cd $BUP_DIR ; git fsck --unreachable 2>/dev/null | grep unreachable ) && WVFAIL
WVPASS bup save -n foo "$tmpdir/foo"
# nothing changed, so still no unreachables... but there are some:
(cd $BUP_DIR ; git fsck --unreachable 2>/dev/null | grep unreachable ) && # WVFAIL
# here is a hexdump:
(cd $BUP_DIR ; git fsck --unreachable 2>/dev/null | grep unreachable | \
cut -f3 -d" " | xargs git cat-file -p | hd ; WVFAIL )


rm -rf "$tmpdir"

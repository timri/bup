#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

top="$(pwd)" || exit $?
tmpdir="$(wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS mkdir -p "$tmpdir/src/x"
WVPASS mkdir -p "$tmpdir/src/y/z"
WVPASS bup init
WVPASS bup random 8k > $tmpdir/src/random-1
WVPASS bup random 8k > $tmpdir/src/x/random-2
WVPASS bup random 8k > $tmpdir/src/y/z/random-3
WVPASS bup index "$tmpdir/src"

WVSTART 'bup save --tree / restore'
tree=$(bup save --tree "$tmpdir/src") || exit $?
WVPASS bup restore -C "$tmpdir/r-t" --vfs-root $tree "$tmpdir/src"
WVPASS "$top/t/compare-trees" "$tmpdir/src/" "$tmpdir/r-t/src/"

WVSTART 'bup save --commit / restore'
commit=$(bup save --commit "$tmpdir/src") || exit $?
WVPASS bup restore -C "$tmpdir/r-c" --vfs-root $commit "$tmpdir/src"
WVPASS "$top/t/compare-trees" "$tmpdir/src/" "$tmpdir/r-c/src/"

WVPASS "$top/t/compare-trees" "$tmpdir/r-t/src/" "$tmpdir/r-c/src/"

WVSTART 'restore --vfs-root'
WVPASS bup save -n foo "$tmpdir/src"
# restore "old style"
WVPASS bup restore -C "$tmpdir/r1" "foo/latest/$tmpdir/src"
# restore "new style"
WVPASS bup restore -C "$tmpdir/r2" --vfs-root foo "$tmpdir/src"
WVPASS "$top/t/compare-trees" "$tmpdir/r1/src/" "$tmpdir/r2/src/"

WVPASS rm -rf "$tmpdir"

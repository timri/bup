#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS bup init
WVPASS cd "$tmpdir"

branchname="a/rev/name/with/many/slashes"
WVSTART "save revname with slashes"
WVPASS mkdir src
WVPASS touch src/foo
WVPASS bup index src
WVPASS bup save -n $branchname src
WVPASSEQ $(GIT_DIR=$BUP_DIR git branch) $branchname
WVPASSEQ $(bup ls $branchname/latest/$tmpdir/src/) "foo"

# these are valid branches
WVPASS bup restore -C dest "$branchname/latest/$(pwd)/src/"
WVPASS rm -rf dest
WVPASS bup restore -C dest "$branchname/latest/$(pwd)/"
WVPASS rm -rf dest
WVPASS bup restore -C dest "$branchname/latest/"
WVPASS rm -rf dest

# these are not valid:
WVFAIL bup restore -C dest "$branchname/"
WVPASS rm -rf dest
WVFAIL bup restore -C dest "a/rev/name/with/many/"
WVPASS rm -rf dest
WVFAIL bup restore -C dest "a/rev/name/with/"
WVPASS rm -rf dest
WVFAIL bup restore -C dest "a/rev/name/"
WVPASS rm -rf dest
WVFAIL bup restore -C dest "a/rev/"
WVPASS rm -rf dest
WVFAIL bup restore -C dest "a/"
WVPASS rm -rf dest

# this should be fixed / catched later....
WVSTART "bup save fails with existing prefix (should be fixed)"
WVFAIL bup save -n a/rev/name src

WVPASS rm -rf "$tmpdir"

#!/usr/bin/env bash
. ./wvtest-bup.sh
. t/lib.sh

top="$(pwd)"
bup() { "$top/bup" "$@"; }

WVSTART "exclude-if-present"
(
    set -e -o pipefail
    D="$(wvmktempdir)"
    export BUP_DIR="$D/.bup"
    force-delete $D
    mkdir $D
    WVPASS bup init
    touch $D/a
    WVPASS bup random 128k >$D/b
    mkdir $D/d $D/d/e
    WVPASS bup random 512 >$D/f
    touch $D/d/exclude-file
    WVPASS bup index -ux --exclude-if-present exclude-file $D
    bup save -n exclude $D
    WVPASSEQ "$(bup ls exclude/latest/$TOP/$D/)" "a
b
f"
    rm -rf "$D"
) || WVFAIL

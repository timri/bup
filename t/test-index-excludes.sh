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

WVSTART "exclude-caches"
(
    D="$(WVPASS wvmktempdir)" || exit $?
    WVPASS force-delete $D
    WVPASS mkdir $D
    export BUP_DIR="$D/.bup"
    WVPASS bup init
    WVPASS touch $D/a
    WVPASS bup random 128k >$D/b
    WVPASS mkdir $D/d $D/d/e
    WVPASS touch $D/d/file
    WVPASS bup random 512 >$D/f
    WVPASS echo 'Signature: 8a477f597d28d172789f06886806bc55' > $D/d/CACHEDIR.TAG
    WVPASS bup index -ux --exclude-caches $D
    WVPASS bup save -n exclude $D
    WVPASSEQ "$(bup ls exclude/latest/$TOP/$D/)" "a
b
d
f"
    WVPASSEQ "$(bup ls exclude/latest/$TOP/$D/d/)" "CACHEDIR.TAG"
) || WVFAIL

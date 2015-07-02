#!/usr/bin/env bash
. wvtest.sh
. wvtest-bup.sh
. t/lib.sh

set -o pipefail

top="$(WVPASS /bin/pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS cd "$tmpdir"

WVPASS bup init

WVSTART "split"
WVPASS echo a >a.tmp
WVPASS echo b >b.tmp
WVPASS bup split --blobs a.tmp >taga.tmp
WVPASS bup split --blobs b.tmp >tagb.tmp
WVPASS cat a.tmp b.tmp | WVPASS bup split --blobs >tagab.tmp
WVPASSEQ $(cat taga.tmp | wc -l) 1
WVPASSEQ $(cat tagb.tmp | wc -l) 1
WVPASSEQ $(cat tagab.tmp | wc -l) 1
WVPASSEQ $(cat tag[ab].tmp | wc -l) 2
WVPASSEQ "$(bup split --blobs a.tmp b.tmp)" "$(cat tagab.tmp)"
WVPASSEQ "$(bup split --blobs --keep-boundaries a.tmp b.tmp)" "$(cat tag[ab].tmp)"
WVPASSEQ "$(cat tag[ab].tmp | bup split --blobs --keep-boundaries --git-ids)" \
         "$(cat tag[ab].tmp)"
WVPASSEQ "$(cat tag[ab].tmp | bup split --blobs --git-ids)" \
         "$(cat tagab.tmp)"
WVPASS bup split --bench --blobs <"$top/t/testfile1" >tags1.tmp
WVPASS bup split -vvvv --blobs "$top/t/testfile2" >tags2.tmp
WVPASS echo -n "" | WVPASS bup split -n split_empty_string.tmp
WVPASS bup margin
WVPASS bup midx -f
WVPASS bup midx --check -a
WVPASS bup midx -o "$BUP_DIR/objects/pack/test1.midx" \
	"$BUP_DIR"/objects/pack/*.idx
WVPASS bup midx --check -a
WVPASS bup midx -o "$BUP_DIR"/objects/pack/test1.midx \
	"$BUP_DIR"/objects/pack/*.idx \
	"$BUP_DIR"/objects/pack/*.idx
WVPASS bup midx --check -a
all=$(echo "$BUP_DIR"/objects/pack/*.idx "$BUP_DIR"/objects/pack/*.midx)
WVPASS bup midx -o "$BUP_DIR"/objects/pack/zzz.midx $all
WVPASS bup tick
WVPASS bup midx -o "$BUP_DIR"/objects/pack/yyy.midx $all
WVPASS bup midx -a
WVPASSEQ "$(echo "$BUP_DIR"/objects/pack/*.midx)" \
	""$BUP_DIR"/objects/pack/yyy.midx"
WVPASS bup margin
WVPASS bup split --tree "$top/t/testfile2" >tags2t.tmp
WVPASS bup split --tree "$top/t/testfile2" --fanout 3 >tags2tf.tmp
WVPASS bup split -r "$BUP_DIR" --commit "$top/t/testfile2" >tags2c.tmp
WVPASS bup split -r ":$BUP_DIR" --commit "$top/t/testfile2" >tags2c.tmp
WVPASS ls -lR \
    | WVPASS bup split -r ":$BUP_DIR" --commit --fanout 3 --max-pack-objects 3 -n lslr \
    || exit $?
WVPASS bup ls
WVFAIL bup ls /does-not-exist
WVPASS bup ls /lslr
WVPASS bup ls /lslr/latest
WVPASS bup ls /lslr/latest/
#WVPASS bup ls /lslr/1971-01-01   # all dates always exist
WVFAIL diff -u tags1.tmp tags2.tmp

# fanout must be different from non-fanout
WVFAIL diff tags2t.tmp tags2tf.tmp
WVPASS wc -c "$top/t/testfile1" "$top/t/testfile2"
WVPASS wc -l tags1.tmp tags2.tmp

WVSTART "join"
WVPASS bup join $(cat tags1.tmp) >out1.tmp
WVPASS bup join <tags2.tmp >out2.tmp
WVPASS bup join <tags2t.tmp -o out2t.tmp
WVPASS bup join -r "$BUP_DIR" <tags2c.tmp >out2c.tmp
WVPASS bup join -r ":$BUP_DIR" <tags2c.tmp >out2c.tmp
WVPASS diff -u "$top/t/testfile1" out1.tmp
WVPASS diff -u "$top/t/testfile2" out2.tmp
WVPASS diff -u "$top/t/testfile2" out2t.tmp
WVPASS diff -u "$top/t/testfile2" out2c.tmp
WVPASSEQ "$(bup join split_empty_string.tmp)" ""

WVPASS rm -rf "$tmpdir"

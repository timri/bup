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

WVSTART "index"
D=bupdata.tmp
WVPASS force-delete $D
WVPASS mkdir $D
WVFAIL bup index --exclude-from $D/cannot-exist $D
WVPASSEQ "$(bup index --check -p)" ""
WVPASSEQ "$(bup index --check -p $D)" ""
WVFAIL [ -e $D.fake ]
WVFAIL bup index --check -u $D.fake
WVPASS bup index --check -u $D
WVPASSEQ "$(bup index --check -p $D)" "$D/"
WVPASS touch $D/a
WVPASS bup random 128k >$D/b
WVPASS mkdir $D/d $D/d/e
WVPASS bup random 512 >$D/f
WVPASS ln -s non-existent-file $D/g
WVPASSEQ "$(bup index -s $D/)" "A $D/"
WVPASSEQ "$(bup index -s $D/b)" ""
WVPASSEQ "$(bup index --check -us $D/b)" "A $D/b"
WVPASSEQ "$(bup index --check -us $D/b $D/d)" \
"A $D/d/e/
A $D/d/
A $D/b"
WVPASS touch $D/d/z
WVPASS bup tick
WVPASSEQ "$(bup index --check -usx $D)" \
"A $D/g
A $D/f
A $D/d/z
A $D/d/e/
A $D/d/
A $D/b
A $D/a
A $D/"
WVPASSEQ "$(bup index --check -us $D/a $D/b --fake-valid)" \
"  $D/b
  $D/a"
WVPASSEQ "$(bup index --check -us $D/a)" "  $D/a"  # stays unmodified
WVPASSEQ "$(bup index --check -us $D/d --fake-valid)" \
"  $D/d/z
  $D/d/e/
  $D/d/"
WVPASS touch $D/d/z
WVPASS bup index -u $D/d/z  # becomes modified
WVPASSEQ "$(bup index -s $D/a $D $D/b)" \
"A $D/g
A $D/f
M $D/d/z
  $D/d/e/
M $D/d/
  $D/b
  $D/a
A $D/"

WVPASS bup index -u $D/d/e $D/a --fake-invalid
WVPASSEQ "$(cd $D && bup index -m .)" \
"./g
./f
./d/z
./d/e/
./d/
./a
./"
WVPASSEQ "$(cd $D && bup index -m)" \
"g
f
d/z
d/e/
d/
a
./"
WVPASSEQ "$(cd $D && bup index -s .)" "$(cd $D && bup index -s .)"

WVFAIL bup save --tree $D/doesnt-exist-filename

WVPASS mv "$BUP_DIR/bupindex" "$BUP_DIR/bi.old"
WVFAIL bup save --tree $D/d/e/fifotest
WVPASS mkfifo $D/d/e/fifotest
WVPASS bup index -u $D/d/e/fifotest
WVPASS bup save --tree $D/d/e/fifotest
WVPASS bup save --tree $D/d/e
WVPASS rm -f $D/d/e/fifotest
WVPASS bup index -u $D/d/e
WVFAIL bup save --tree $D/d/e/fifotest
WVPASS mv "$BUP_DIR/bi.old" "$BUP_DIR/bupindex"

WVPASS bup index -u $D/d/e
WVPASS bup save --tree $D/d/e
WVPASSEQ "$(cd $D && bup index -m)" \
"g
f
d/z
d/
a
./"
WVPASS bup save --tree $D/d
WVPASS bup index --fake-invalid $D/d/z
WVPASS bup save --tree $D/d/z
WVPASS bup save --tree $D/d/z  # test regenerating trees when no files are changed
WVPASS bup save --tree $D/d
WVPASSEQ "$(cd $D && bup index -m)" \
"g
f
a
./"
WVPASS bup save -r ":$BUP_DIR" -n r-test $D
WVFAIL bup save -r ":$BUP_DIR/fake/path" -n r-test $D
WVFAIL bup save -r ":$BUP_DIR" -n r-test $D/fake/path

WVPASS rm -rf "$tmpdir"

% bup-get(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-get - copy repository items

# SYNOPSIS

bup get \[-s *source-path*\] \[-r *host*:*path*\]  OPTIONS \<(METHOD *item*)...\>

# DESCRIPTION

`bup get` copies the indicated *item*s from the source repository to
the destination repository (respecting `--bup-dir` and `BUP_DIR`),
according to the specified METHOD, which may be one of `--ff`,
`--append`, `--pick`, `--ff-pick`, `--force-pick`, `--new-tag`,
`--overwrite`, or `--unnamed`.  See the EXAMPLES below for a quick
introduction.

Each *item* must be of the form:

    *src*[:*dest*]

Here, *src* is the VFS path of the object to be fetched, and *dest* is
the optional destination.  Some methods don't always require (or
allow) a destination, and of course, tags may be refered to via the
VFS /.tag/ directory.  For example:

    bup get -s /source/repo --ff foo
    bup get -s /source/repo --ff foo/latest:bar
    bup get -s /source/repo --pick foo/2010-10-10-101010:.tag/bar

In some situations `bup get` will evaluate a branch operation
according to whether or not it will be a "fast-forward" (which
requires that any existing destination branch be an ancestor of the
source).

An existing destination tag can only be overwritten by an `--overwrite`
or `--force-pick`.

When a new commit is created (i.e. via `--append`, `--pick`, etc.), it
will have the same author, author date, and message as the original,
but a committer and committer date corresponding to the current user
and time.

For each destination reference updated, if requested by the
appropriate options bup will print the commit, tree, or tag hash.
When relevant, the tree hash will be printed before the commit hash.

Local *item*s can be pushed to a remote repository with the `--remote`
option, and remote *item*s can be pulled into a local repository via
"bup on HOST get ...".  See `bup-on`(1) and the EXAMPLES below for
further information.

Assuming sufficient disk space (and until/unless bup supports
something like rm/gc), this command can be used to drop old, unwanted
backups by creating a new repository, fetching the desired saves into
it, and then deleting the old repository.

# METHODS

\--ff *src*[:*dest*]
:   fast-forward *dest* to match *src*.  If *dest* is not specified
    and *src* names a save, set *dest* to the save's branch.  If
    *dest* is not specified and *src* names a branch or a tag, use the
    same name for *dest*.

\--append *src*[:*dest*]
:   append all of the commits represented by *src* to *dest* as new
    commits. If *src* names a directory/tree, append a new commit for
    that tree.  If *dest* is not specified and *src* names a save or
    branch, set *dest* to the *src* branch name.  If *dest* is not
    specified and *src* names a tag, use the same name for *dest*.

\--pick *src*[:*dest*]
:   append the single commit named by *src* to *dest* as a new commit.
    If *dest* is not specified and *src* names a save, set *dest* to
    the *src* branch name.  If *dest* is not specified and *src* names
    a tag, use the same name for *dest*.

\--ff-pick *src*[:*dest*]
:   do the same thing as `--pick`, but require the destination to be a
    branch, and refuse if the operation wouldn't be a fast-forward.

\--force-pick *src*[:*dest*]
:   do the same thing as `--pick`, but don't refuse to overwrite an
    existing tag.

\--new-tag *src*[:*dest*]
:   create a *dest* tag for *src*, but refuse to overwrite an existing
    tag.  If *dest* is not specified and *src* names a tag, use the
    same name for *dest*.

\--overwrite *src*[:*dest*]
:   clobber *dest* with *src*, overwriting any existing tag, or
    replacing any existing branch.  If *dest* is not specified and
    *src* names a branch or tag, use the same name for *dest*.

\--unnamed *src*
:   copy *src* into the destination repository, without any name,
    leaving a potentially dangling reference until/unless the object
    named by *src* is referred to some other way (cf. `bup tag`).

# OPTIONS

-s, \--source=*path*
:   use *path* as the source repository, instead of the default.

-r, \--remote=*host*:*path*
:   store the indicated items on the given remote server.  If *path*
    is omitted, uses the default path on the remote server (you still
    need to include the ':').  The connection to the remote server is
    made with SSH.  If you'd like to specify which port, user or
    private key to use for the SSH connection, we recommend you use
    the `~/.ssh/config` file.

-c, \--print-commits
:   for each updated branch, print the new git commit id.

-t, \--print-trees
:   for each updated branch, print the new git tree id of the
    filesystem root.

\--print-tags
:   for each updated tag, print the new git id.

-v, \--verbose
:   increase verbosity (can be used more than once).  With
    `-v`, print the name of every item fetched, with `-vv` add
    directory names, and with `-vvv` add every filename.

\--bwlimit=*bytes/sec*
:   don't transmit more than *bytes/sec* bytes per second to the
    server.  This can help avoid sucking up all your network
    bandwidth.  Use a suffix like k, M, or G to specify multiples of
    1024, 1024\*1024, 1024\*1024\*1024 respectively.

-*#*, \--compress=*#*
:   set the compression level to # (a value from 0-9, where
    9 is the highest and 0 is no compression).  The default
    is 1 (fast, loose compression)

# EXAMPLES

    # Update or copy the archives branch in src-repo to the local repository.
    $ bup get -s src-repo --ff archives

    # Append a particular archives save to the pruned-archives branch.
    $ bup get -s src-repo --pick archives/2013-01-01-030405:pruned-archives

    # Update or copy the archives branch on remotehost to the local
    # repository.
    $ bup on remotehost get --ff archives

    # Update or copy the local branch archives to remotehost.
    $ bup get -r remotehost: --ff archives

    # Update or copy the archives branch in src-repo to remotehost.
    $ bup get -s src-repo -r remotehost: --ff archives

    # Update the archives-2 branch on remotehost to match archives.
    # If archives-2 exists and is not an ancestor of archives, bup
    # will refuse.
    $ bup get -r remotehost: --ff archives:archives-2

    # Replace the contents of branch y with those of x.
    $ bup get --overwrite x:y

    # Copy the latest local save from the archives branch to the
    # remote tag foo.
    $ bup get -r remotehost: --pick archives/latest:.tag/foo

    # Or if foo already exists:
    $ bup get -r remotehost: --force-pick archives/latest:.tag/foo

    # Append foo (from above) to the local other-archives branch.
    $ bup on remotehost get --append .tag/foo:other-archives

    # Append only the /home directory from archives/latest to only-home.
    $ bup get -s "$BUP_DIR" --append archives/latest/home:only-home

# SEE ALSO

`bup-on`(1), `bup-tag`(1), `ssh_config`(5)

# BUP

Part of the `bup`(1) suite.

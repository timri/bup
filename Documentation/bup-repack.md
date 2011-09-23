% bup-save(1) Bup %BUP_VERSION%
% Zoran Zaric <zz@zoranzaric.de>
% %BUP_DATE%

# NAME

bup-repack - repack a repository to free up space

# SYNOPSIS

bup repack [-n] [-q] [-#] [-f]

# DESCRIPTION

`bup repack` repacks all objects in a repository into new
packfiles.  It traverses the history and saves only needed
objects.

`bup repack` iterates over the existing packfiles and
deletes each, after writing the last needed object to the
new packfile.  Because of this repacking a repository can
use the biggest existing packfile's filesize as additional
diskspace.

# OPTIONS

-n,--dry-run
:   don't do anything just print out what would be done

-q, --quiet
:   disable progress messages.

-*#*, --compress=*#*
:   set the compression level to # (a value from 0-9, where
    9 is the highest and 0 is no compression).  The default
    is 1 (fast, loose compression).  WARNING: Changing the
    compression level will change all objects and will result
    in duplicate objects if the new compression level isn't
    set on new saves.

-f, --force
:   ignore free space check.


# EXAMPLE

    $ bup index -ux /etc
    Indexing: 1981, done.

    $ bup save -r myserver: -n my-pc-backup --bwlimit=50k /etc
    Reading index: 1981, done.
    Saving: 100.00% (998/998k, 1981/1981 files), done.

    $ bup repack
    Traversing my-pc-backup to find needed objects...
    Traversing objects: 54323, done.
    Writing new packfiles...
    Writing objects: 28115, done.


# SEE ALSO

`bup-save`(1)

# BUP

Part of the `bup`(1) suite.

% bup-nbd(1) Bup %BUP_VERSION%
% Tim Riemenschneider <git@tim-riemenschneider.de>
% %BUP_DATE%

# NAME

bup-nbd - export files from a bup repository as network-block-device

# SYNOPSIS

bup nbd [--host *host*] [--port *port*] [refs, hashes or paths...]

# DESCRIPTION

`bup nbd` exports files from a bup repository as a
network-block-device (NBD) compatible with nbd-server/nbd-client.
This allows mounting disk-images saved by `bup-join` or `bup-save`.

The supplied list of refs or hashes can be in any format
accepted by `git`(1), including branch names, commit ids,
tree ids, or blob ids. Furthermore you can supply paths like
those accepted by `bup-restore`, as long as they reference a
single file. (Actually you can also point to directories
(tree-objects), which are then reinterpretated as hash-split
files. This is required to support backups made by bup-join
and makes only sense with those. Trying that with other
directories is expected to result in exceptions in the
client-connection-handler)

If no refs or hashes are given on the command line, `bup
nbd` reads them from stdin instead.

# OPTIONS

\--host=*host*
:   Specify the address to listen on for incoming requests by nbd-client.
    This defaults to 127.0.0.1

\--port=*port*
:   Specify the port to listen on for incoming requests.
    Defaults to the standardport for nbd, 10809

# EXAMPLES

    # split a cd-image and then export it as network device:
    $ bup split -n debian-iso debian-7.2.0-i386-netinst.iso
    bloom: creating from 1 file (37344 objects).
    $ bup nbd debian-iso
    Incoming connection from 127.0.0.1:55956
    [127.0.0.1:55956] Client aborted negotiation
    exiting
    Incoming connection from 127.0.0.1:55958
    Client using new-style non-fixed handshake
    [127.0.0.1:55958] Negotiated export: debian-iso => ec507f9801328a6d62be58c68c5fd8790f33169b
    [127.0.0.1:55958] disconnecting
    exiting
    ^C
    # meanwhile actions in a second shell:
    $ sudo nbd-client localhost 10809 -l
    Negotiation: ..
    debian-iso
    $ sudo nbd-client localhost 10809 -N debian-iso /dev/nbd0
    Negotiation: ..size = 277MB
    bs=1024, sz=290455552 bytes
    $ sudo mount /dev/nbd0 /mnt
    mount: block device /dev/nbd0 is write-protected, mounting read-only
    $ ls /mnt
    autorun.inf
    css
    debian
    dists
    ...
    $ sudo umount /dev/nbd0
    $ sudo nbd-client -d /dev/nbd0
    Disconnecting: que, disconnect, sock, done
    $
    
    # You can export multiple files at once, the exports will be named
    # like given on the command-line:
    $ bup index isos
    Indexing: 4, done.
    $ bup save --strip-path=$PWD -n my-isos isos
    Reading index: 4, done.
    Saving: 100.00% (600484/600484k, 4/4 files), done.
    bloom: adding 1 file (43076 objects).
    $ bup ls my-isos/latest/isos
    debian-7.2.0-i386-netinst.iso
    hdt-0.5.2.img
    pmagic_2013_02_28.iso
    $ bup nbd my-isos/latest/isos/debian-7.2.0-i386-netinst.iso my-isos/latest/isos/pmagic_2013_02_28.iso .commit/19/b91ee3a0d42f366f3508ace6289268655c7ce5
    Incoming connection from 127.0.0.1:56018
    [127.0.0.1:56018] Client aborted negotiation
    exiting
    Incoming connection from 127.0.0.1:56021
    Client using new-style non-fixed handshake
    [127.0.0.1:56021] Negotiated export: my-isos/latest/isos/pmagic_2013_02_28.iso => 3ab646b2da6c1b657dfcf6d1751939d1a6202737
    [127.0.0.1:56021] disconnecting
    exiting
    ^C
    # second shell:
    $ sudo nbd-client localhost 10809 -l
    Negotiation: ..
    my-isos/latest/isos/debian-7.2.0-i386-netinst.iso
    .commit/19/b91ee3a0d42f366f3508ace6289268655c7ce5
    my-isos/latest/isos/pmagic_2013_02_28.iso
    $ sudo nbd-client localhost 10809 -N my-isos/latest/isos/pmagic_2013_02_28.iso /dev/nbd0
    Negotiation: ..size = 308MB
    bs=1024, sz=322961408 bytes
    $ sudo mount /dev/nbd0 /mnt
    mount: block device /dev/nbd0 is write-protected, mounting read-only
    $ ls /mnt
    boot  EFI  mkgriso  pmagic
    $ sudo umount /mnt
    $ sudo nbd-client -d /dev/nbd0
    Disconnecting: que, disconnect, sock, done
    
    # You can layer this with the third-party tool qemu-nbd to access
    # virtual-machine disks:
    bup index .VirtualBox/VMs/debian\ test/
    Indexing: 10, done.
    bup: merging indexes (23/23), done.
    $ bup save -n virtualbox-backup --strip .VirtualBox/VMs/debian\ test/
    Reading index: 10, done.
    Saving: 100.00% (1532244/1532248k, 10/10 files), done.
    bloom: adding 1 file (56 objects).
    $ bup nbd virtualbox-backup/latest/debian\ test.vdi
    ...
    # shell 2:
    $ sudo nbd-client localhost 10809 -N virtualbox-backup/latest/debian\ test.vdi /dev/nbd0
    Negotiation: ..size = 1496MB
    bs=1024, sz=1568690176 bytes
    $ sudo qemu-nbd -c /dev/nbd1 /dev/nbd0
    $ sudo mount /dev/nbd1p1 /mnt
    $ cat /mnt/etc/debian_version
    7.0
    $ ls /mnt
    bin
    boot
    dev
    etc
    ...
    $ sudo umount /mnt
    $ sudo qemu-nbd -d /dev/nbd1
    /dev/nbd1 disconnected
    $ sudo nbd-client -d /dev/nbd0
    Disconnecting: que, disconnect, sock, done

# SEE ALSO

`bup-split`(1), `bup-save`(1), `bup-cat-file`, `ssh_config`(5)

    Inspired by this thread on the mailing-list:
    https://groups.google.com/forum/#!msg/bup-list/-A9WmBhTaYs/SXFZew02SfMJ

# BUP

Part of the `bup`(1) suite.

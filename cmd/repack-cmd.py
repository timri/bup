#!/usr/bin/env python
import sys, os
from bup import git, options
from bup.helpers import *

def run(argv):
    # at least in python 2.5, using "stdout=2" or "stdout=sys.stderr" below
    # doesn't actually work, because subprocess closes fd #2 right before
    # execing for some reason.  So we work around it by duplicating the fd
    # first.
    fd = os.dup(2)  # copy stderr
    try:
        p = subprocess.Popen(argv, stdout=fd, close_fds=False)
        return p.wait()
    finally:
        os.close(fd)


optspec = """
bup repack
--
q,quiet    don't show progress meter
v,verbose  increase log output (can be used more than once)
n,dry-run  don't do anything, just print what would be done
f,force    ignore the space check
#,compress=  set compression level to # (0-9, 9 is highest) [1] (See WARNING in manpage!)
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()

handle_ctrl_c()

if not opt.force:
    # this only works on unix
    vfs_stats = os.statvfs(git.repo())
    free_space = vfs_stats.f_bsize * vfs_stats.f_bavail
    if not opt.force and free_space < git.max_pack_size * 2:
        o.fatal("insufficent space")

cp = git.CatPipe()

opt.progress = (istty2 and not opt.quiet)
refs = git.list_refs()
refnames = [name for name, sha in refs]

git.lock()

try:
    pl = git.PackIdxList(git.repo('objects/pack'))
    total_objects = len(pl)

    needed_objects = git.NeededObjects(pl)

    # Find needed objects reachable from commits
    traversed_objects_counter = 0

    for refname in refnames:
        if not refname.startswith('refs/heads/'):
            continue
        log('Traversing %s to find needed objects...\n' % refname[11:])
        for date, sha in ((date, sha.encode('hex')) for date, sha in
                          git.rev_list(refname)):
            for type, sha_ in git.traverse_commit(cp, sha, needed_objects):
                traversed_objects_counter += 1
                qprogress('Traversing objects (%d/%d)\r' %
                          (traversed_objects_counter, total_objects))

    # Find needed objects reachable from tags
    tags = git.tags()
    if len(tags) > 0:
        for key in tags:
            log('Traversing tag %s to find needed objects...\n' %
                ", ".join(tags[key]))
            for type, sha in git.traverse_commit(cp, sha, needed_objects):
                traversed_objects_counter += 1
                qprogress('Traversing objects (%d/%d)\r' %
                          (traversed_objects_counter, total_objects))
    skipped_objects = total_objects - traversed_objects_counter
    if skipped_objects == 0:
        progress('Traversing objects (%d/%d), done.\n' %
                 (traversed_objects_counter, total_objects))
    else:
        progress('Traversing objects (%d/%d), done. Skipped %d\n' %
                 (traversed_objects_counter, total_objects, skipped_objects))


    if traversed_objects_counter == 0:
        o.fatal('No reachable objects found.')


    if not opt.dry_run:
        blob_writer = git.PackWriter(compression_level=opt.compress)
        w = git.PackWriter(compression_level=opt.compress)

    log('Writing new packfiles...\n')
    par2 = False
    written_object_counter = 0
    for pack in needed_objects.packs:
        ba = needed_objects.get_bitarray_for_pack(pack.name)
        for offset, sha in pack.hashes_sorted_by_ofs():
            idx = pack._idx_from_hash(sha)
            if idx in ba:
                it = iter(cp.get(sha.encode('hex')))
                type = it.next()
                content = "".join(it)
                if not opt.dry_run:
                    if opt.verbose:
                        print "writing %s %s" % (sha.encode('hex'), type)
                    if type == 'blob':
                        blob_writer._write(sha, type, content)
                    else:
                        w._write(sha, type, content)
                needed_objects.remove(sha.encode('hex'))
                written_object_counter += 1
                qprogress('Writing objects: %d\r' % written_object_counter)
            else:
                it = iter(cp.get(sha.encode('hex')))
                type = it.next()
                if opt.verbose:
                    print "not writing %s %s" % (sha.encode('hex'), type)
        if not opt.dry_run:
            os.unlink(pack.name)
            os.unlink(pack.name[:-3] + "pack")
            if os.path.exists(pack.name[:-3] + "par2"):
                par2 = True
                os.unlink(pack.name[:-3] + "par2")
    progress('Writing objects: %d, done.\n' % written_object_counter)

    if not opt.dry_run:
        blob_writer.close()
        w.close()
        if par2:
            run(['bup', 'fsck', '-g'])

finally:
    git.unlock()


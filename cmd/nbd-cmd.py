#!/usr/bin/env python
import sys, signal
from bup import git, options, client, vfs, nbdserver
from bup.helpers import *
import SocketServer

optspec = """
bup nbd [paths...]
--
vfs-root=       start the VFS on a different object, could be a commit-id (f.e. from "bup save -c") or a tree-id (f.e. from "bup save -t" or "bup ls -s")
host=           host/ip to bind to [127.0.0.1]
port=           port-number [10809]
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()

if not extra:
    extra = linereader(sys.stdin)

if opt.vfs_root:
    # opt.vfs_root might be an integer
    commitid = git.rev_parse('%s' % opt.vfs_root)
    if not commitid:
        o.fatal("commit '%s' could not be found" % opt.vfs_root)
    top = vfs.Dir(None, opt.vfs_root, GIT_MODE_TREE, commitid)
else:
    top = vfs.RefList(None)

roots = {}
for id in extra:
    #hash = git.rev_parse(id)
    node = top.resolve(id)
    if isinstance(node, vfs.CommitDir):
        log("ignoring %s (Can't use CommitDir as export)\n" % id)
        continue
    elif isinstance(node, vfs.CommitList):
        log("ignoring %s (Can't use CommitList as export)\n" % id)
        continue
#    elif isinstance(node, vfs.BranchDir):
#        log("ignoring %s (Can't use BranchDir as export)\n" % id)
#        continue
    elif isinstance(node, vfs.RefList):
        log("ignoring %s (Can't use RefList as export)\n" % id)
        continue
    elif isinstance(node, vfs.TagDir):
        log("ignoring %s (Can't use CommitList as export)\n" % id)
        continue
    elif isinstance(node, vfs.File):
        log("bupmode: %d\n" % node.bupmode)
    elif isinstance(node, vfs.Dir) or isinstance(node, vfs.BranchList):
        # assume that this is created by bup-join
        # so it is a File with bupmode==BUP_CHUNKED
        hash = node.hash
        cp = git.CatPipe()
        it = cp.get(hash.encode('hex'))
        type = it.next()
        if type == 'commit':
            treeline = ''.join(it).split('\n')[0]
            assert(treeline.startswith('tree '))
            hash = treeline[5:].decode('hex')
        node = vfs.File(node.parent, node.name, node.mode, hash, git.BUP_CHUNKED)
    else:
        log("nbd: implementation for type %s missing!\n" % node.__class__.__name__)
        print node
        sys.exit(1)
    # Dir, Symlink, File (any others?)
    roots[id] = node

if len(roots) == 0:
    log("no exports defined\n")
    sys.exit(1)
server = nbdserver.NbdServer(roots, opt.host, opt.port)
def handler(signum, trace):
        server.server_close()

signal.signal(signal.SIGINT, handler)
signal.signal(signal.SIGTERM, handler)

try:
        server.serve_forever()
except:
        pass


sys.exit(0)

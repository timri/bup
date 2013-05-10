#!/usr/bin/env python
import sys
from bup import git, vfs, ls
from bup.helpers import *
from bup.hashsplit import GIT_MODE_TREE

git.check_repo_or_die()

if len(sys.argv) < 2:
    sys.stderr.write('Usage: %s <commit-id>\n' % sys.argv[0])
    sys.exit(1)

hash = sys.argv[1]
top = vfs.Dir(None, hash, GIT_MODE_TREE, hash.decode('hex'))

# Check out lib/bup/ls.py for the opt spec
ret = ls.do_ls(sys.argv[2:], top, default='/', spec_prefix='bup ')

sys.exit(ret)

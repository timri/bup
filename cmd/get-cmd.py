#!/usr/bin/env python
import os, re, stat, sys, time
from collections import namedtuple
from functools import partial
from bup import git, options, client, helpers, vfs
from bup.git import get_commit_items, parse_commit, walk_object
from bup.helpers import add_error, debug1, handle_ctrl_c, log, saved_errors
from bup.helpers import hostname, userfullname, username

optspec = """
bup get [-s SRC_REPO] <(METHOD SRC[:DEST])...>
--
ff=         METHOD: fast-forward DEST to match SRC or fail
append=     METHOD: append SRC (treeish or committish) to DEST
pick=       METHOD: append single SRC commit to DEST
force-pick= METHOD: --pick, but clobber DEST
new-tag=    METHOD: tag SRC as DEST unless it already exists
overwrite=  METHOD: update DEST to match SRC, clobbering DEST
unnamed=    METHOD: fetch SRC anonymously (no DEST name)
s,source=  path to the source repository (defaults to BUP_DIR)
r,remote=  hostname:/path/to/repo of remote destination repository
t,print-trees     output a tree id (for each SET)
c,print-commits   output a commit id (for each SET)
print-tags  output an id for each tag
v,verbose  increase log output (can be used more than once)
q,quiet    don't show progress meter
bwlimit=   maximum bytes/sec to transmit to server
#,compress=  set compression level to # (0-9, 9 is highest) [1]
"""

method_args = ('--ff', '--append', '--pick', '--force-pick',
               '--new-tag', '--overwrite', '--unnamed')

is_reverse = os.environ.get('BUP_SERVER_REVERSE')

class LocalRepo:
    def __init__(self, dir=None):
        self.update_ref = partial(git.update_ref, repo_dir=dir)
        self._vfs_top = vfs.RefList(None, repo_dir=dir)
        self.path_info = lambda x: vfs.path_info(x, self._vfs_top)
    def close(self):
        pass


class RemoteRepo:
    def __init__(self, remote_name):
        self._client = client.Client(remote_name)
        self.path_info = self._client.path_info
        self.update_ref = self._client.update_ref
    def client(self):
        return self._client
    def close(self):
        self._client.close()


def get_random_item(name, hash, cp, writer, opt):
    def already_seen(id):
        return writer.exists(id.decode('hex'))
    for id, type, data in walk_object(cp, hash, opt.verbose, [name],
                                      stop_at=already_seen, include_data=True):
        # already_seen ensures that writer.exists(id) is false.
        # Otherwise, write() would fail.
        writer.write(id.decode('hex'), type, data)


def append_commit(name, hash, parent, cp, writer, opt):
    now = time.time()
    items = get_commit_items(hash, cp)
    tree = items.tree.decode('hex')
    author = '%s <%s>' % (items.author_name, items.author_mail)
    author_time = (items.author_sec, items.author_offset)
    committer = '%s <%s@%s>' % (userfullname(), username(), hostname())
    get_random_item(name, hash, cp, writer, opt)
    c = writer.new_commit(tree, parent,
                          author, items.author_sec, items.author_offset,
                          committer, now, None,
                          items.message)
    return (c, tree)


def append_commits(commits, src_name, dest_hash, cp, writer, opt):
    last_c, tree = dest_hash, None
    for commit in commits:
        last_c, tree = append_commit(src_name, commit.encode('hex'), last_c,
                                     cp, writer, opt)
    assert(tree is not None)
    return last_c, tree


Spec = namedtuple('Spec', ['argopt', 'argval', 'src', 'dest', 'method'])


def parse_target_args(flags, fatal):
    def split_target(arg):
        parts = arg.split(':')
        if len(parts) not in (1, 2) or not parts[0]:
            fatal('invalid item %r' % arg)
        dest_name = None
        src_name = parts[0]
        if len(parts) == 2 and parts[1]:
            dest_name = parts[1]
        return src_name, dest_name

    result = []
    for opt, value in flags:
        # We'll add an update-pick if/when anyone cares.
        if opt in method_args:
            src, dest =  split_target(value)
            result.append(Spec(argopt=opt, argval=value,
                               src=src, dest=dest, method=opt[2:]))
    return result


Loc = namedtuple('Loc', ['type', 'hash', 'path'])
default_loc = Loc(None, None, None)


# FIXME: change all the code to handle path_info() types directly
# (which would allow log_item() to handle chunked-files as files)?
def find_vfs_item(name, repo):
    info = repo.path_info([name])
    if not info[0]:
        return None
    path, id, type = info[0]
    if type in ('dir', 'chunked-file'):
        type = 'tree'
    elif type == 'file':
        type = 'blob'
    return Loc(type=type, hash=id, path=path)


Target = namedtuple('Target', ['spec', 'src', 'dest'])


def loc_desc(loc):
    if loc and loc.hash:
        loc = loc._replace(hash=loc.hash.encode('hex'))
    return str(loc)


def cleanup_vfs_path(p):
    result = os.path.normpath(p)
    if result.startswith('/'):
        return result
    return '/' + result


def validate_vfs_path(p, fatal):
    if p.startswith('/.') \
       and not p.startswith('/.tag/'):
        spec_args = '%s %s' % (spec.argopt, spec.argval)
        fatal('unsupported destination path %r in %r' % (dest.path, spec_args))
    return p


def resolve_src(spec, src_repo, fatal):
    src = find_vfs_item(spec.src, src_repo)
    spec_args = '%s %s' % (spec.argopt, spec.argval)
    if not src:
        fatal('cannot find source for %r' % spec_args)
    if src.hash == vfs.EMPTY_SHA.encode('hex'):
        fatal('cannot find source for %r (no hash)' % spec_args)
    if src.type == 'root':
        fatal('cannot fetch entire repository for %r' % spec_args)
    debug1('src: %s\n' % loc_desc(src))
    return src


def get_save_branch(vfs_path):
    try:
        n = src_vfs.lresolve(vfs_path)
        return n.parent.fullname()
    except vfs.NodeError, ex:
        if not save_node:
            fatal('%r has vanished from the source VFS' % spec.src)


def resolve_branch_dest(spec, src, dest_repo, fatal):
    # Resulting dest must be treeish, or not exist.
    if not spec.dest:
        # Pick a default dest.
        if src.type == 'branch':
            spec = spec._replace(dest=spec.src)
        elif src.type == 'save':
            spec = spec._replace(dest=get_save_branch(spec.src))
        elif src.path.startswith('/.tag/'):  # Dest defaults to the same.
            spec = spec._replace(dest=spec.src)

    spec_args = '%s %s' % (spec.argopt, spec.argval)
    if not spec.dest:
        fatal('no destination (implicit or explicit) for %r', spec_args)

    dest = find_vfs_item(spec.dest, dest_repo)
    if dest:
        if dest.type == 'commit':
            fatal('destination for %r is a tagged commit, not a branch'
                  % spec_args)
        if dest.type != 'branch':
            fatal('destination for %r is a %s, not a branch'
                  % (spec_args, dest.type))
    else:
        dest = default_loc._replace(path=cleanup_vfs_path(spec.dest))

    if dest.path.startswith('/.'):
        fatal('destination for %r must be a valid branch name' % spec_args)

    debug1('dest: %s\n' % loc_desc(dest))
    return spec, dest


def resolve_ff(spec, src_repo, src_vfs, src_dir, src_cp, dest_repo, fatal):
    src = resolve_src(spec, src_repo, fatal)
    spec_args = '%s %s' % (spec.argopt, spec.argval)
    if src.type == 'tree':
        fatal('%r is impossible; can only --append a tree to a branch'
              % spec_args)
    if src.type not in ('branch', 'save', 'commit'):
        fatal('source for %r must be a branch, save, or commit, not %s'
              % (spec_args, src.type))
    spec, dest = resolve_branch_dest(spec, src, dest_repo, fatal)
    return Target(spec=spec, src=src, dest=dest)


def handle_ff(item, repo, cp, writer, opt, fatal):
    assert(item.spec.method == 'ff')
    assert(item.src.type in ('branch', 'save', 'commit'))
    hex_src = item.src.hash.encode('hex')
    commits = [c for d, c in git.rev_list(hex_src, repo_dir=repo)]
    if not item.dest.hash or item.dest.hash in commits:
        # Can fast forward.
        get_random_item(item.spec.src, hex_src, cp, writer, opt)
        commit_items = get_commit_items(hex_src, cp)
        return item.src.hash, commit_items.tree.decode('hex')
    spec_args = '%s %s' % (item.spec.argopt, item.spec.argval)
    fatal('destination is not an ancestor of source for %r' % spec_args)


def resolve_append(spec, src_repo, src_vfs, src_dir, src_cp, dest_repo, fatal):
    src = resolve_src(spec, src_repo, fatal)
    if src.type not in ('branch', 'save', 'commit', 'tree'):
        spec_args = '%s %s' % (spec.argopt, spec.argval)
        fatal('source for %r must be a branch, save, commit, or tree, not %s'
              % (spec_args, src.type))
    spec, dest = resolve_branch_dest(spec, src, dest_repo, fatal)
    return Target(spec=spec, src=src, dest=dest)


def handle_append(item, repo, cp, writer, opt, fatal):
    assert(item.spec.method == 'append')
    assert(item.src.type in ('branch', 'save', 'commit', 'tree'))
    assert(item.dest.type == 'branch' or not item.dest.type)
    hex_src = item.src.hash.encode('hex')
    if item.src.type == 'tree':
        get_random_item(item.spec.src, hex_src, cp, writer, opt)
        parent = item.dest.hash
        msg = 'bup save\n\nGenerated by command:\n%r\n' % sys.argv
        userline = '%s <%s@%s>' % (userfullname(), username(), hostname())
        now = time.time()
        commit = writer.new_commit(item.src.hash, parent,
                                   userline, now, None,
                                   userline, now, None, msg)
        return commit, item.src.hash
    commits = [c for d, c in git.rev_list(hex_src, repo_dir=repo)]
    commits.reverse()
    return append_commits(commits, item.spec.src, item.dest.hash,
                          cp, writer, opt)


def resolve_pick(spec, src_repo, src_vfs, src_dir, src_cp, dest_repo, fatal):
    src = resolve_src(spec, src_repo, fatal)
    spec_args = '%s %s' % (spec.argopt, spec.argval)
    if src.type == 'tree':
        fatal('%r is impossible; can only --append a tree' % spec_args)
    if src.type not in ('commit', 'save'):
        fatal('%r impossible; can only pick a commit or save, not %s'
              % (spec_args, src.type))
    if not spec.dest:
        if src.path.startswith('/.tag/'):
            spec = spec._replace(dest=spec.src)
        elif src.type == 'save':
            spec = spec._replace(dest=get_save_branch(spec.src))
    if not spec.dest:
        fatal('no destination provided for %r', spec_args)
    dest = find_vfs_item(spec.dest, dest_repo)
    if not dest:
        cp = validate_vfs_path(cleanup_vfs_path(spec.dest), fatal)
        dest = default_loc._replace(path=cp)
    else:
        if not dest.type == 'branch' and not dest.path.startswith('/.tag/'):
            fatal('%r destination is not a tag or branch' % spec_args)
        if spec.method == 'pick' \
           and dest.hash and dest.path.startswith('/.tag/'):
            fatal('cannot overwrite existing tag for %r (requires --force-pick)'
                  % spec_args)
    return Target(spec=spec, src=src, dest=dest)


def handle_pick(item, repo, cp, writer, opt, fatal):
    assert(item.spec.method in ('pick', 'ff-pick', 'force-pick'))
    assert(item.src.type in ('save', 'commit'))
    hex_src = item.src.hash.encode('hex')
    if item.dest.hash:
        return append_commit(item.spec.src, hex_src, item.dest.hash,
                             cp, writer, opt)
    return append_commit(item.spec.src, hex_src, None, cp, writer, opt)


def resolve_new_tag(spec, src_repo, src_vfs, src_dir, src_cp, dest_repo, fatal):
    src = resolve_src(spec, src_repo, fatal)
    spec_args = '%s %s' % (spec.argopt, spec.argval)
    if not spec.dest and src.path.startswith('/.tag/'):
        spec = spec._replace(dest=src.path)
    if not spec.dest:
        fatal('no destination (implicit or explicit) for %r', spec_args)
    dest = find_vfs_item(spec.dest, dest_repo)
    if not dest:
        dest = default_loc._replace(path=cleanup_vfs_path(spec.dest))
    if not dest.path.startswith('/.tag/'):
        fatal('destination for %r must be a VFS tag' % spec_args)
    if dest.hash:
        fatal('cannot overwrite existing tag for %r (requires --overwrite)'
              % spec_args)
    return Target(spec=spec, src=src, dest=dest)


def handle_new_tag(item, repo, cp, writer, opt, fatal):
    assert(item.spec.method == 'new-tag')
    assert(item.dest.path.startswith('/.tag/'))
    get_random_item(item.spec.src, item.src.hash.encode('hex'), cp, writer, opt)
    return (item.src.hash,)


def resolve_overwrite(spec, src_repo, src_vfs, src_dir, src_cp, dest_repo, fatal):
    src = resolve_src(spec, src_repo, fatal)
    spec_args = '%s %s' % (spec.argopt, spec.argval)
    if not spec.dest:
        if src.path.startswith('/.tag/') or src.type == 'branch':
            spec = spec._replace(dest=spec.src)
    if not spec.dest:
        fatal('no destination provided for %r', spec_args)
    dest = find_vfs_item(spec.dest, dest_repo)
    if dest:
        if not dest.type == 'branch' and not dest.path.startswith('/.tag/'):
            fatal('%r impossible; can only overwrite branch or tag'
                  % spec_args)
    else:
        cp = validate_vfs_path(cleanup_vfs_path(spec.dest), fatal)
        dest = default_loc._replace(path=cp)
    if not dest.path.startswith('/.tag/') \
       and not src.type in ('branch', 'save', 'commit'):
        fatal('cannot overwrite branch with %s for %r' % (src.type, spec_args))
    return Target(spec=spec, src=src, dest=dest)


def handle_overwrite(item, repo, cp, writer, opt, fatal):
    assert(item.spec.method == 'overwrite')
    if item.dest.path.startswith('/.tag/'):
        get_random_item(item.spec.src, item.src.hash.encode('hex'),
                        src_cp, writer, opt)
        return (item.src.hash,)
    assert(item.dest.type == 'branch' or not item.dest.type)
    hex_src = item.src.hash.encode('hex')
    get_random_item(item.spec.src, hex_src, src_cp, writer, opt)
    commit_items = get_commit_items(hex_src, cp)
    return item.src.hash, commit_items.tree.decode('hex')


def resolve_unnamed(spec, src_repo, src_vfs, src_dir, src_cp, dest_repo, fatal):
    if spec.dest:
        spec_args = '%s %s' % (spec.argopt, spec.argval)
        fatal('destination name given for %r' % spec_args)
    src = resolve_src(spec, src_repo, fatal)
    return Target(spec=spec, src=src, dest=None)


def handle_unnamed(item, repo, cp, writer, opt, fatal):
    get_random_item(item.spec.src, item.src.hash.encode('hex'),
                    src_cp, writer, opt)
    return (None,)


def resolve_targets(specs, src_repo, src_vfs, src_dir, src_cp, dest_repo, fatal):
    resolved_items = []
    common_args = (src_repo, src_vfs, src_dir, src_cp, dest_repo, fatal)
    for spec in specs:
        debug1('initial-spec: %s\n' % str(spec))
        if spec.method == 'ff':
            resolved_items.append(resolve_ff(spec, *common_args))
        elif spec.method == 'append':
            resolved_items.append(resolve_append(spec, *common_args))
        elif spec.method in ('pick', 'force-pick'):
            resolved_items.append(resolve_pick(spec, *common_args))
        elif spec.method == 'new-tag':
            resolved_items.append(resolve_new_tag(spec, *common_args))
        elif spec.method == 'overwrite':
            resolved_items.append(resolve_overwrite(spec, *common_args))
        elif spec.method == 'unnamed':
            resolved_items.append(resolve_unnamed(spec, *common_args))
        else: # Should be impossible -- prevented by the option parser.
            assert(False)

    # FIXME: check for prefix overlap?  i.e.:
    #   bup get --ff foo --ff baz:foo/bar
    #   bup get --new-tag .tag/foo --new-tag bar:.tag/foo/bar

    # Now that we have all the items, check for duplicate tags.
    tags_targeted = set()
    for item in resolved_items:
        dest_path = item.dest and item.dest.path
        if dest_path:
            assert(dest_path.startswith('/'))
            if dest_path.startswith('/.tag/'):
                if dest_path in tags_targeted:
                    if item.spec.method not in ('overwrite', 'force-pick'):
                        spec_args = '%s %s' % (item.spec.argopt,
                                               item.spec.argval)
                        fatal('cannot overwrite tag %r via %r' \
                              % (dest_path, spec_args))
                else:
                    tags_targeted.add(dest_path)
    return resolved_items


def log_item(name, type, opt, tree=None, commit=None, tag=None):
    if tag and opt.print_tags:
        print tag.encode('hex')
    if tree and opt.print_trees:
        print tree.encode('hex')
    if commit and opt.print_commits:
        print commit.encode('hex')
    if opt.verbose:
        last = ''
        if type in ('root', 'branch', 'save', 'commit', 'tree'):
            if not name.endswith('/'):
                last = '/'
        log('%s%s\n' % (name, last))


handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra):
    o.fatal('unexpected arguments: %s' % ' '.join(map(repr, extra)))

target_specs = parse_target_args(flags, o.fatal)

git.check_repo_or_die()
src_dir = opt.source or git.repo()

if opt.bwlimit:
    client.bwlimit = parse_num(opt.bwlimit)

if is_reverse and opt.remote:
    o.fatal("don't use -r in reverse mode; it's automatic")

if opt.remote or is_reverse:
    dest_repo = RemoteRepo(opt.remote)
    writer = dest_repo.client().new_packwriter(compression_level=opt.compress)
else:
    dest_repo = LocalRepo()
    writer = git.PackWriter(compression_level=opt.compress)

src_vfs = vfs.RefList(None, repo_dir=src_dir)
src_cp = vfs.cp(src_dir)
src_repo = LocalRepo(src_dir)

# Resolve and validate all sources and destinations, implicit or
# explicit, and do it up-front, so we can fail before we start writing
# (for any obviously broken cases).
target_items = resolve_targets(target_specs, src_repo, src_vfs, src_dir, src_cp,
                               dest_repo, o.fatal)

updated_refs = {}  # ref_name -> (original_ref, tip_commit(bin))
no_ref_info = (None, None)

handlers = {'ff': handle_ff,
            'append': handle_append,
            'force-pick': handle_pick,
            'pick': handle_pick,
            'new-tag': handle_new_tag,
            'overwrite': handle_overwrite,
            'unnamed': handle_unnamed}

for item in target_items:

    debug1('get-spec: %s\n' % str(item.spec))
    debug1('get-src: %s\n' % loc_desc(item.src))
    debug1('get-dest: %s\n' % loc_desc(item.dest))

    dest_path = item.dest and item.dest.path
    if dest_path:
        if dest_path.startswith('/.tag/'):
            dest_ref = 'refs/tags/%s' % dest_path[6:]
        else:
            dest_ref = 'refs/heads/%s' % dest_path[1:]
    else:
        dest_ref = None

    dest_hash = item.dest and item.dest.hash
    orig_ref, cur_ref = updated_refs.get(dest_ref, no_ref_info)
    orig_ref = orig_ref or dest_hash
    cur_ref = cur_ref or dest_hash

    handler = handlers[item.spec.method]
    item_result = handler(item, src_dir, src_cp, writer, opt, o.fatal)
    if len(item_result) > 1:
        new_id, tree = item_result
    else:
        new_id = item_result[0]

    if not dest_ref:
        log_item(item.spec.src, item.src.type, opt)
    else:
        updated_refs[dest_ref] = (orig_ref, new_id)
        if dest_ref.startswith('refs/tags/'):
            log_item(item.spec.src, item.src.type, opt, tag=new_id)
        else:
            log_item(item.spec.src, item.src.type, opt,
                     tree=tree, commit=new_id)


writer.close()  # Must close before we can update the ref(s).

# Only update the refs at the very end, so that if something goes
# wrong above, the old refs will be undisturbed.
for ref_name, info in updated_refs.iteritems():
    orig_ref, new_ref = info
    try:
        dest_repo.update_ref(ref_name, new_ref, orig_ref)
        if opt.verbose:
            new_hex = new_ref.encode('hex')
            if orig_ref:
                orig_hex = orig_ref.encode('hex')
                log('updated %r (%s -> %s)\n' % (ref_name, orig_hex, new_hex))
            else:
                log('updated %r (%s)\n' % (ref_name, new_hex))
    except (git.GitError, client.ClientError), ex:
        add_error('unable to update ref %r: %s' % (ref_name, ex))

dest_repo.close()

if saved_errors:
    log('WARNING: %d errors encountered while saving.\n' % len(saved_errors))
    sys.exit(1)

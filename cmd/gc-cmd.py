#!/usr/bin/env python
import glob, os, stat, subprocess, sys, tempfile, time
from bup import bloom, git, midx, options, vfs
from bup.helpers import handle_ctrl_c, log, progress, qprogress, saved_errors
from os.path import basename

optspec = """
bup gc [options...]
--
v,verbose   increase log output (can be used more than once)
threshold   only rewrite a packfile if it's over this percent garbage [10]
#,compress= set compression level to # (0-9, 9 is highest) [1]
"""


class Nonlocal:
    pass

gc_start = time.time()
trees = set()
# FIXME: unify with the walk_object() version in bup-get
def walk_object(cat_pipe, id, verbose=None, parent_path=[],
                stop_at=None,
                include_data=None):
    # Yield everything reachable from id via cat_pipe, stopping
    # whenever stop_at(id) returns true.  Produce (id, type data) for
    # each item, or (id, type) if include_data is false.
    if stop_at and stop_at(id):
        return

    item_it = cat_pipe.get(id)  # FIXME: use include_data
    type = item_it.next()

    # FIXME: remove once cat pipe supports include_data.
    need_data = include_data or type in ('commit', 'tree')
    if not need_data:
        list(item_it) # Dump the data (iterator).

    if type == 'blob':
        yield include_data and (id, type, ''.join(item_it)) or (id, type)
    elif type == 'commit':
        data = ''.join(item_it)
        yield include_data and (id, type, data) or (id, type)

        commit_items = git.parse_commit(data)
        tree_id = commit_items.tree
        for x in walk_object(cat_pipe, tree_id, verbose, parent_path,
                             stop_at, include_data):
            yield x
        parents = commit_items.parents
        for pid in parents:
            for x in walk_object(cat_pipe, pid, verbose, parent_path,
                                 stop_at, include_data):
                yield x
    elif type == 'tree':
        data = ''.join(item_it)
        if id.decode('hex') in trees:
             return
        trees.add(id.decode('hex'))
        yield include_data and (id, type, data) or (id, type)
        for (mode, name, ent_id) in git.tree_decode(data):
            if not verbose > 1:
                for x in walk_object(cat_pipe, ent_id.encode('hex'),
                                     stop_at, include_data):
                    yield x
            else:
                demangled, bup_type = git.demangle_name(name)
                sub_path = parent_path + [demangled]
                # Don't print the sub-parts of chunked files.
                sub_v = verbose if bup_type == git.BUP_NORMAL else None
                for x in walk_object(cat_pipe, ent_id.encode('hex'),
                                     sub_v, sub_path,
                                     stop_at, include_data):
                    yield x
                if stat.S_ISDIR(mode):
                    if verbose > 1 and bup_type == git.BUP_NORMAL:
                        log('%s/\n' % '/'.join(sub_path))
                    elif verbose > 2:  # (and BUP_CHUNKED)
                        log('%s\n' % '/'.join(sub_path))
                elif verbose > 2:
                    log('%s\n' % '/'.join(sub_path))
    else:
        raise Exception('unexpected repository object type %r' % type)


def count_objects(dir):
    # For now we'll just use open_idx(), but we could probably be much
    # more efficient since all we need is a single integer (the last
    # fanout entry) from each index.
    object_count = 0
    for idx_name in glob.glob(os.path.join(dir, '*.idx')):
        idx = git.open_idx(idx_name)
        object_count += len(idx)
    return object_count


def find_live_objects(existing_count, cat_pipe, opt):
    pack_dir = git.repo('objects/pack')
    ffd, bloom_filename = tempfile.mkstemp('.bloom', 'tmp-gc-', pack_dir)
    os.close(ffd)
    # FIXME: allow selection of k?
    # FIXME: support ephemeral bloom filters (i.e. *never* written to disk)
    live_objs = bloom.create(bloom_filename, expected=existing_count, k=None)
    traversed_total = 0
    live_count = 0

    for ref_name, ref_id in git.list_refs():
        elapsed = time.time() - gc_start
        log('gc[%02d:%02d:%02d]: traversing %s\n' % ( elapsed // 3600,
                                                  (elapsed // 60) % 60,
                                                   elapsed % 60,
                                                   ref_name))
        for id, type in walk_object(cat_pipe, ref_id.encode('hex'), opt.verbose,
                                    parent_path=[ref_name],
                                    stop_at=None,
                                    include_data=None):
            if not (traversed_total % 128):
                elapsed = time.time() - gc_start
                objs_per_sec = traversed_total / elapsed if elapsed else 0
                qprogress('gc[%02d:%02d:%02d]: searching live objs %d, keep %d (%d objs/s)\r' % ( elapsed // 3600,
                                                  (elapsed // 60) % 60,
                                                   elapsed % 60,
                                                   traversed_total,
                                                   live_count,
                                                   objs_per_sec))
            # FIXME: batch ids
            if not live_objs.exists(id.decode('hex')):
                live_count += 1
            live_objs.add(id.decode('hex'))
            traversed_total += 1
        elapsed = time.time() - gc_start
        objs_per_sec = traversed_total / elapsed if elapsed else 0
        progress('gc[%02d:%02d:%02d]: searched %s, traversed %d objects total (%d objs/s)\n' % ( elapsed // 3600,
                                                  (elapsed // 60) % 60,
                                                   elapsed % 60,
                                                   ref_name,
                                                   traversed_total,
                                                   objs_per_sec))
    if opt.verbose:
        log('gc[%02d:%02d:%02d]: expecting to retain about %.2f%% unnecessary objects\n'
            % ( elapsed // 3600,
               (elapsed // 60) % 60,
                elapsed % 60,
                live_objs.pfalse_positive()))
    return live_objs


def sweep(live_objects, existing_count, cat_pipe, opt):
    # Traverse all the packs, saving the (probably) live data.

    ns = Nonlocal()
    ns.stale_files = []
    def remove_stale_files(new_pack_prefix):
        if opt.verbose and new_pack_prefix:
            log('created ' + basename(new_pack_prefix) + '\n')
        for p in ns.stale_files:
            if opt.verbose:
                elapsed = time.time() - gc_start
                log('gc[%02d:%02d:%02d]: removing %s\n' % ( elapsed // 3600,
                                                           (elapsed // 60) % 60,
                                                            elapsed % 60,
                                                            basename(p)))
            os.unlink(p)
        ns.stale_files = []

    writer = git.PackWriter(objcache_maker=None,
                            compression_level=opt.compress,
                            run_midx=False,
                            on_pack_finish=remove_stale_files)

    # FIXME: sanity check .idx names vs .pack names?
    collect_count = 0
    for idx_name in glob.glob(os.path.join(git.repo('objects/pack'), '*.idx')):
        if opt.verbose:
            elapsed = time.time() - gc_start
            qprogress('gc[%01d:%02d:%02d]: preserving live data (%d%% complete)\r'
                      % ( elapsed // 3600,
                         (elapsed // 60) % 60,
                          elapsed % 60,
                          ((float(collect_count) / existing_count) * 100)))
        idx = git.open_idx(idx_name)

        idx_live_count = 0
        for i in xrange(0, len(idx)):
            sha = idx.shatable[i * 20 : (i + 1) * 20]
            if live_objects.exists(sha):
                idx_live_count += 1

        collect_count += idx_live_count
        if idx_live_count == 0:
            if opt.verbose:
                elapsed = time.time() - gc_start
                log('gc[%02d:%02d:%02d]: %s (delete)\n'
                    % ( elapsed // 3600,
                       (elapsed // 60) % 60,
                        elapsed % 60,
                        git.repo_rel(basename(idx_name))))
            ns.stale_files.append(idx_name)
            ns.stale_files.append(idx_name[:-3] + 'pack')
            continue

        live_frac = idx_live_count / float(len(idx))
        if live_frac > ((100 - opt.threshold) / 100.0):
            if opt.verbose:
                elapsed = time.time() - gc_start
                log('gc[%02d:%02d:%02d]: %s (keep: %d%% live)\n' % ( elapsed // 3600,
                                                    (elapsed // 60) % 60,
                                                     elapsed % 60,
                                                     git.repo_rel(basename(idx_name)),
                                                     live_frac * 100))
            continue

        if opt.verbose:
            elapsed = time.time() - gc_start
            log('gc[%02d:%02d:%02d]: %s (rewrite: %.2f%% live)\n' % ( elapsed // 3600,
                                                     (elapsed // 60) % 60,
                                                      elapsed % 60,
                                                      basename(idx_name),
                                                      live_frac * 100))
        for i in xrange(0, len(idx)):
            sha = idx.shatable[i * 20 : (i + 1) * 20]
            if opt.verbose and not i % 128:
                elapsed = time.time() - gc_start
                qprogress('gc[%02d:%02d:%02d]: this pack %.2f%% done, overall %.2f%% done\r' % ( elapsed // 3600,
                                                     (elapsed // 60) % 60,
                                                      elapsed % 60,
                                                      ((float(i) / len(idx)) * 100),
                                                      ((float(collect_count) / len(live_objects)) * 100)))
            if live_objects.exists(sha):
                item_it = cat_pipe.get(sha.encode('hex'))
                type = item_it.next()
                writer.write(sha, type, ''.join(item_it))

        ns.stale_files.append(idx_name)
        ns.stale_files.append(idx_name[:-3] + 'pack')

    if opt.verbose:
        elapsed = time.time() - gc_start
        progress('gc[%02d:%02d:%02d]: preserving live data (%d%% complete)\n'
                 % ( elapsed // 3600,
                    (elapsed // 60) % 60,
                     elapsed % 60,
                    ((float(collect_count) / existing_count) * 100)))

    # Nothing should have recreated midx/bloom yet.
    pack_dir = git.repo('objects/pack')
    assert(not os.path.exists(os.path.join(pack_dir, 'bup.bloom')))
    assert(not glob.glob(os.path.join(pack_dir, '*.midx')))

    # try/catch should call writer.abort()?
    # This will finally run midx.
    writer.close()  # Can only change refs (if needed) after this.
    remove_stale_files(None)  # In case we didn't write to the writer.

    if opt.verbose:
        elapsed = time.time() - gc_start
        log('gc[%02d:%02d:%02d]: discarded %d%% of objects\n'
            % ( elapsed // 3600,
               (elapsed // 60) % 60,
                elapsed % 60,
              ((existing_count - count_objects(pack_dir))
               / float(existing_count) * 100)))


# FIXME: server mode?
# FIXME: make sure client handles server-side changes reasonably
# FIXME: fdatasync new packs in packwriter?

handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal('no positional parameters expected')

if opt.threshold:
    try:
        opt.threshold = int(opt.threshold)
    except ValueError:
        o.fatal('threshold must be an integer percentage value')
    if opt.threshold < 0 or opt.threshold > 100:
        o.fatal('threshold must be an integer percentage value')

git.check_repo_or_die()

cat_pipe = vfs.cp()
existing_count = count_objects(git.repo('objects/pack'))
if opt.verbose:
    elapsed = time.time() - gc_start
    log('gc[%02d:%02d:%02d]: found %d objects\n' % ( elapsed // 3600,
                                                    (elapsed // 60) % 60,
                                                     elapsed % 60,
                                                     existing_count))
if not existing_count:
    if opt.verbose:
        elapsed = time.time() - gc_start
        log('gc[%02d:%02d:%02d]: nothing to collect\n' % ( elapsed // 3600,
                                                  (elapsed // 60) % 60,
                                                   elapsed % 60))
else:
    live_objects = find_live_objects(existing_count, cat_pipe, opt)
    try:
        # FIXME: just rename midxes and bloom, and restore them at the end if
        # we didn't change any packs?
        elapsed = time.time() - gc_start
        if opt.verbose: log('gc[%02d:%02d:%02d]: clearing midx files\n' % ( elapsed // 3600,
                                                  (elapsed // 60) % 60,
                                                   elapsed % 60))
        midx.clear_midxes()
        elapsed = time.time() - gc_start
        if opt.verbose: log('gc[%02d:%02d:%02d]: clearing bloom filter\n' % ( elapsed // 3600,
                                                  (elapsed // 60) % 60,
                                                   elapsed % 60))
        bloom.clear_bloom(git.repo('objects/pack'))
        elapsed = time.time() - gc_start
        if opt.verbose: log('gc[%02d:%02d:%02d]: clearing reflog\n' % ( elapsed // 3600,
                                                  (elapsed // 60) % 60,
                                                   elapsed % 60))
        expirelog_cmd = ['git', 'reflog', 'expire', '--all']
        expirelog = subprocess.Popen(expirelog_cmd, preexec_fn = git._gitenv())
        git._git_wait(' '.join(expirelog_cmd), expirelog)
        elapsed = time.time() - gc_start
        if opt.verbose: log('gc[%02d:%02d:%02d]: removing unreachable data\n' % ( elapsed // 3600,
                                                  (elapsed // 60) % 60,
                                                   elapsed % 60))
        sweep(live_objects, existing_count, cat_pipe, opt)
    finally:
        live_objects.close()
        os.unlink(live_objects.name)

if saved_errors:
    log('WARNING: %d errors encountered during gc\n' % len(saved_errors))
    sys.exit(1)

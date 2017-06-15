
import sys, os, stat, time, random, subprocess, glob
from subprocess import check_call

from wvtest import *

from bup import client, git
from bup.helpers import mkdirp, readpipe
from buptest import no_lingering_errors, test_tempdir


def exc(*cmd):
    cmd_str = ' '.join(cmd)
    print >> sys.stderr, cmd_str
    check_call(cmd)


def exo(*cmd):
    cmd_str = ' '.join(cmd)
    print >> sys.stderr, cmd_str
    return readpipe(cmd)


def randbytes(sz):
    s = ''
    for i in xrange(sz):
        s += chr(random.randrange(0,256))
    return s


# FIXME: global state modifications below, i.e.
#os.environ['BUP_MAIN_EXE'] = '../../../bup'
#os.environ['BUP_DIR'] = bupdir = tmpdir

top_dir = os.path.realpath('../../..')
bup_exe = top_dir + '/bup'

s1 = randbytes(10000)
s2 = randbytes(10000)
s3 = randbytes(10000)

IDX_PAT = '/*.idx'
    

@wvtest
def test_server_split_with_indexes():
    with no_lingering_errors():
        with test_tempdir('bup-tclient-') as tmpdir:
            os.environ['BUP_MAIN_EXE'] = bup_exe
            os.environ['BUP_DIR'] = bupdir = tmpdir
            git.init_repo(bupdir)
            lw = git.PackWriter()
            c = client.Client(bupdir, create=True)
            rw = c.new_packwriter()

            lw.new_blob(s1)
            lw.close()

            rw.new_blob(s2)
            rw.breakpoint()
            rw.new_blob(s1)
            rw.close()
    

@wvtest
def test_multiple_suggestions():
    with no_lingering_errors():
        with test_tempdir('bup-tclient-') as tmpdir:
            os.environ['BUP_MAIN_EXE'] = bup_exe
            os.environ['BUP_DIR'] = bupdir = tmpdir
            git.init_repo(bupdir)

            lw = git.PackWriter()
            lw.new_blob(s1)
            lw.close()
            lw = git.PackWriter()
            lw.new_blob(s2)
            lw.close()
            WVPASSEQ(len(glob.glob(git.repo('objects/pack'+IDX_PAT))), 2)

            c = client.Client(bupdir, create=True)
            WVPASSEQ(len(glob.glob(c.cachedir+IDX_PAT)), 0)
            rw = c.new_packwriter()
            s1sha = rw.new_blob(s1)
            WVPASS(rw.exists(s1sha))
            s2sha = rw.new_blob(s2)
            # This is a little hacky, but ensures that we test the code under test
            while (len(glob.glob(c.cachedir+IDX_PAT)) < 2 and
                   not c.conn.has_input()):
                pass
            rw.new_blob(s2)
            WVPASS(rw.objcache.exists(s1sha))
            WVPASS(rw.objcache.exists(s2sha))
            rw.new_blob(s3)
            WVPASSEQ(len(glob.glob(c.cachedir+IDX_PAT)), 2)
            rw.close()
            WVPASSEQ(len(glob.glob(c.cachedir+IDX_PAT)), 3)


@wvtest
def test_dumb_client_server():
    with no_lingering_errors():
        with test_tempdir('bup-tclient-') as tmpdir:
            os.environ['BUP_MAIN_EXE'] = bup_exe
            os.environ['BUP_DIR'] = bupdir = tmpdir
            git.init_repo(bupdir)
            open(git.repo('bup-dumb-server'), 'w').close()

            lw = git.PackWriter()
            lw.new_blob(s1)
            lw.close()

            c = client.Client(bupdir, create=True)
            rw = c.new_packwriter()
            WVPASSEQ(len(glob.glob(c.cachedir+IDX_PAT)), 1)
            rw.new_blob(s1)
            WVPASSEQ(len(glob.glob(c.cachedir+IDX_PAT)), 1)
            rw.new_blob(s2)
            rw.close()
            WVPASSEQ(len(glob.glob(c.cachedir+IDX_PAT)), 2)


@wvtest
def test_midx_refreshing():
    with no_lingering_errors():
        with test_tempdir('bup-tclient-') as tmpdir:
            os.environ['BUP_MAIN_EXE'] = bupmain = '../../../bup'
            os.environ['BUP_DIR'] = bupdir = tmpdir
            git.init_repo(bupdir)
            c = client.Client(bupdir, create=True)
            rw = c.new_packwriter()
            rw.new_blob(s1)
            p1base = rw.breakpoint()
            p1name = os.path.join(c.cachedir, p1base)
            s1sha = rw.new_blob(s1)  # should not be written; it's already in p1
            s2sha = rw.new_blob(s2)
            p2base = rw.close()
            p2name = os.path.join(c.cachedir, p2base)
            del rw

            pi = git.PackIdxList(bupdir + '/objects/pack')
            WVPASSEQ(len(pi.packs), 2)
            pi.refresh()
            WVPASSEQ(len(pi.packs), 2)
            WVPASSEQ(sorted([os.path.basename(i.name) for i in pi.packs]),
                     sorted([p1base, p2base]))

            p1 = git.open_idx(p1name)
            WVPASS(p1.exists(s1sha))
            p2 = git.open_idx(p2name)
            WVFAIL(p2.exists(s1sha))
            WVPASS(p2.exists(s2sha))

            subprocess.call([bupmain, 'midx', '-f'])
            pi.refresh()
            WVPASSEQ(len(pi.packs), 1)
            pi.refresh(skip_midx=True)
            WVPASSEQ(len(pi.packs), 2)
            pi.refresh(skip_midx=False)
            WVPASSEQ(len(pi.packs), 1)


@wvtest
def test_remote_parsing():
    with no_lingering_errors():
        tests = (
            (':/bup', ('file', None, None, '/bup')),
            ('file:///bup', ('file', None, None, '/bup')),
            ('192.168.1.1:/bup', ('ssh', '192.168.1.1', None, '/bup')),
            ('ssh://192.168.1.1:2222/bup', ('ssh', '192.168.1.1', '2222', '/bup')),
            ('ssh://[ff:fe::1]:2222/bup', ('ssh', 'ff:fe::1', '2222', '/bup')),
            ('bup://foo.com:1950', ('bup', 'foo.com', '1950', None)),
            ('bup://foo.com:1950/bup', ('bup', 'foo.com', '1950', '/bup')),
            ('bup://[ff:fe::1]/bup', ('bup', 'ff:fe::1', None, '/bup')),)
        for remote, values in tests:
            WVPASSEQ(client.parse_remote(remote), values)
        try:
            client.parse_remote('http://asdf.com/bup')
            WVFAIL()
        except client.ClientError:
            WVPASS()


@wvtest
def test_path_info():
    with no_lingering_errors():
        with test_tempdir('bup-tclient-') as tmpdir:
            os.environ['BUP_MAIN_EXE'] = bup_exe
            os.environ['BUP_DIR'] = bupdir = tmpdir
            src = tmpdir + '/src'
            mkdirp(src)
            with open(src + '/1', 'w+') as f:
                print f, 'something'
            with open(src + '/2', 'w+') as f:
                print f, 'something else'
            os.mkdir(src + '/dir')
            git.init_repo(bupdir)
            c = client.Client(bupdir, create=True)

            info = c.path_info(['/'])
            WVPASS(info)
            WVPASS(len(info) == 1)
            WVPASS(info[0])
            name, id, type = info[0]
            WVPASSEQ(type, 'root')

            info = c.path_info(['/not-there/'])
            WVPASS(info)
            WVPASS(len(info) == 1)
            WVPASS(info[0] is None)

            data = exo(bup_exe, 'random', '128k')
            with open(src + '/chunky', 'wb+') as f:
                f.write(data)
            exc(bup_exe, 'index', '-vv', src)
            exc(bup_exe, 'save', '-n', 'src', '--strip', src)
            exc(bup_exe, 'tag', 'src-latest-tag', 'src')
            src_hash = exo('git', '--git-dir', bupdir,
                           'rev-parse', 'src').strip().split('\n')
            assert(len(src_hash) == 1)
            src_hash = src_hash[0].decode('hex')
            tree_hash = exo('git', '--git-dir', bupdir,
                           'rev-parse', 'src:dir').strip().split('\n')[0].decode('hex')
            file_hash = exo('git', '--git-dir', bupdir,
                           'rev-parse', 'src:1').strip().split('\n')[0].decode('hex')
            chunky_hash = exo('git', '--git-dir', bupdir,
                              'rev-parse', 'src:chunky.bup').strip().split('\n')[0].decode('hex')
            info = c.path_info(['/src'])
            WVPASS(info)
            WVPASS(len(info) == 1)
            WVPASS(info[0])
            WVPASSEQ(info[0], ['/src', src_hash, 'branch'])

            info = c.path_info(['/src/latest'])
            WVPASS(info)
            WVPASS(len(info) == 1)
            WVPASS(info[0])
            WVPASSEQ(info[0], ['/src/latest', src_hash, 'save'])

            info = c.path_info(['/src/latest/dir'])
            WVPASS(info)
            WVPASS(len(info) == 1)
            WVPASS(info[0])
            WVPASSEQ(info[0], ['/src/latest/dir', tree_hash, 'dir'])

            info = c.path_info(['/src/latest/1'])
            WVPASS(info)
            WVPASS(len(info) == 1)
            WVPASS(info[0])
            WVPASSEQ(info[0], ['/src/latest/1', file_hash, 'file'])

            info = c.path_info(['/src/latest/chunky'])
            WVPASS(info)
            WVPASS(len(info) == 1)
            WVPASS(info[0])
            WVPASSEQ(info[0], ['/src/latest/chunky', chunky_hash, 'chunked-file'])

            info = c.path_info(['/.tag/src-latest-tag'])
            WVPASS(info)
            WVPASS(len(info) == 1)
            WVPASS(info[0])
            WVPASSEQ(info[0], ['/.tag/src-latest-tag', src_hash, 'commit'])

            info = c.path_info(['.tag////src-latest-tag'])
            WVPASS(info)
            WVPASS(len(info) == 1)
            WVPASS(info[0])
            WVPASSEQ(info[0], ['/.tag/src-latest-tag', src_hash, 'commit'])

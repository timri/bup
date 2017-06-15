
from __future__ import print_function
from collections import namedtuple
from contextlib import contextmanager
from os.path import abspath, basename, dirname, realpath
from pipes import quote
from subprocess import PIPE, Popen, check_call
from traceback import extract_stack
import subprocess, sys, tempfile

from wvtest import WVPASSEQ, wvfailure_count

from bup import helpers


bup_cmd = abspath(dirname(sys.argv[0]) + '/../bup')


@contextmanager
def no_lingering_errors():
    def fail_if_errors():
        if helpers.saved_errors:
            bt = extract_stack()
            src_file, src_line, src_func, src_txt = bt[-4]
            msg = 'saved_errors ' + repr(helpers.saved_errors)
            print('! %-70s %s' % ('%s:%-4d %s' % (basename(src_file),
                                                  src_line,
                                                  msg),
                                  'FAILED'))
            sys.stdout.flush()
    fail_if_errors()
    helpers.clear_errors()
    yield
    fail_if_errors()
    helpers.clear_errors()


# Assumes (of course) this file is at the top-level of the source tree
_bup_tmp = realpath(dirname(__file__) + '/t/tmp')
helpers.mkdirp(_bup_tmp)


@contextmanager
def test_tempdir(prefix):
    initial_failures = wvfailure_count()
    tmpdir = tempfile.mkdtemp(dir=_bup_tmp, prefix=prefix)
    yield tmpdir
    if wvfailure_count() == initial_failures:
        subprocess.call(['chmod', '-R', 'u+rwX', tmpdir])
        subprocess.call(['rm', '-rf', tmpdir])


def logcmd(cmd):
    if isinstance(cmd, basestring):
        print(cmd, file=sys.stderr)
    else:
        print(' '.join(map(quote, cmd)), file=sys.stderr)


ex_res = namedtuple('ExRes', ['out', 'err', 'proc', 'rc'])

def ex(cmd, stdin=None, stdout=True, shell=False, check=True, preexec_fn=None):
    logcmd(cmd)
    p = Popen(cmd,
              stdin=stdin,
              stdout=(PIPE if stdout else None),
              stderr=PIPE,
              shell=shell,
              preexec_fn=preexec_fn)
    out, err = p.communicate()
    if check and p.returncode != 0:
        raise Exception('subprocess %r failed with status %d, stderr: %r'
                        % (' '.join(cmd), p.returncode, err))
    if err:
        sys.stderr.write(err)
    return ex_res(out=out, err=err, proc=p, rc=p.returncode)

def exc(cmd, shell=False, preexec_fn=None):
    logcmd(cmd)
    check_call(cmd, shell=shell, preexec_fn=preexec_fn)

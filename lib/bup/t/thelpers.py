import math
import os
import bup._helpers as _helpers
from bup.helpers import *
from wvtest import *

@wvtest
def test_parse_num():
    pn = parse_num
    WVPASSEQ(pn('1'), 1)
    WVPASSEQ(pn('0'), 0)
    WVPASSEQ(pn('1.5k'), 1536)
    WVPASSEQ(pn('2 gb'), 2*1024*1024*1024)
    WVPASSEQ(pn('1e+9 k'), 1000000000 * 1024)
    WVPASSEQ(pn('-3e-3mb'), int(-0.003 * 1024 * 1024))

@wvtest
def test_detect_fakeroot():
    if os.getenv('FAKEROOTKEY'):
        WVPASS(detect_fakeroot())
    else:
        WVPASS(not detect_fakeroot())

@wvtest
def test_path_components():
    WVPASSEQ(path_components('/'), [('', '/')])
    WVPASSEQ(path_components('/foo'), [('', '/'), ('foo', '/foo')])
    WVPASSEQ(path_components('/foo/'), [('', '/'), ('foo', '/foo')])
    WVPASSEQ(path_components('/foo/bar'),
             [('', '/'), ('foo', '/foo'), ('bar', '/foo/bar')])
    WVEXCEPT(Exception, path_components, 'foo')


@wvtest
def test_stripped_path_components():
    WVPASSEQ(stripped_path_components('/', []), [('', '/')])
    WVPASSEQ(stripped_path_components('/', ['']), [('', '/')])
    WVPASSEQ(stripped_path_components('/', ['/']), [('', '/')])
    WVPASSEQ(stripped_path_components('/', ['/foo']), [('', '/')])
    WVPASSEQ(stripped_path_components('/foo', ['/bar']),
             [('', '/'), ('foo', '/foo')])
    WVPASSEQ(stripped_path_components('/foo', ['/foo']), [('', '/foo')])
    WVPASSEQ(stripped_path_components('/foo/bar', ['/foo']),
             [('', '/foo'), ('bar', '/foo/bar')])
    WVPASSEQ(stripped_path_components('/foo/bar', ['/bar', '/foo', '/baz']),
             [('', '/foo'), ('bar', '/foo/bar')])
    WVPASSEQ(stripped_path_components('/foo/bar/baz', ['/foo/bar/baz']),
             [('', '/foo/bar/baz')])
    WVEXCEPT(Exception, stripped_path_components, 'foo', [])

@wvtest
def test_grafted_path_components():
    WVPASSEQ(grafted_path_components([('/chroot', '/')], '/foo'),
             [('', '/'), ('foo', '/foo')])
    WVPASSEQ(grafted_path_components([('/foo/bar', '')], '/foo/bar/baz/bax'),
             [('', None), ('baz', None), ('bax', '/foo/bar/baz/bax')])
    WVEXCEPT(Exception, grafted_path_components, 'foo', [])

# If these tests are still relevant, can we just use a path in our
# temp dir that we know won't exist, rather than /NOT_EXISTING/?

# @wvtest
# def test_graft_path():
#     middle_matching_old_path = "/NOT_EXISTING/user"
#     non_matching_old_path = "/NOT_EXISTING/usr"
#     matching_old_path = "/NOT_EXISTING/home"
#     matching_full_path = "/NOT_EXISTING/home/user"
#     new_path = "/opt"

#     all_graft_points = [(middle_matching_old_path, new_path),
#                         (non_matching_old_path, new_path),
#                         (matching_old_path, new_path)]

#     path = "/NOT_EXISTING/home/user/"

#     WVPASSEQ(graft_path([(middle_matching_old_path, new_path)], path),
#                         "/NOT_EXISTING/home/user")
#     WVPASSEQ(graft_path([(non_matching_old_path, new_path)], path),
#                         "/NOT_EXISTING/home/user")
#     WVPASSEQ(graft_path([(matching_old_path, new_path)], path), "/opt/user")
#     WVPASSEQ(graft_path(all_graft_points, path), "/opt/user")
#     WVPASSEQ(graft_path([(matching_full_path, new_path)], path),
#                         "/opt")

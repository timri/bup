
from __future__ import with_statement
import cPickle, errno, os

class HLinkDB:
    def __init__(self):
        # Map a "dev:ino" node to a list of paths associated with that node.
        self._node_paths = {}
        # Map a path to a "dev:ino" node.
        self._path_node = {}

    def load(self, filename):
        try:
            with open(filename, 'r') as f:
                self._node_paths = cPickle.load(f)
        except IOError, e:
            if e.errno == errno.ENOENT:
                pass
            else:
                raise
        # Set up the reverse hard link index.
        for node, paths in self._node_paths.iteritems():
            for path in paths:
                self._path_node[path] = node

    def save(self, filename):
        # FIXME: make sure this is safe wrt saving of index changes
        # FIXME: save safely (use tmp/mv/etc).
        if self._node_paths:
            with open(filename, 'w') as f:
                cPickle.dump(self._node_paths, f, 2)
        else:
            try:
                os.unlink(filename)
            except OSError, e:
                if e.errno == errno.ENOENT:
                    pass
                else:
                    raise

    def add_path(self, path, dev, ino):
        # Assume path is new.
        node = '%s:%s' % (dev, ino)
        self._path_node[path] = node
        link_paths = self._node_paths.get(node)
        if link_paths and path not in link_paths:
            link_paths.append(path)
        else:
            self._node_paths[node] = [path]

    def _del_node_path(self, node, path):
        link_paths = self._node_paths[node]
        link_paths.remove(path)
        if not link_paths:
            del self._node_paths[node]

    def change_path(self, path, new_dev, new_ino):
        prev_node = self._path_node.get(path)
        if prev_node:
            self._del_node_path(prev_node, path)
        self.add_path(new_dev, new_ino, path)

    def del_path(self, path):
        # Path may not be in db (if updating a pre-hardlink support index).
        node = self._path_node.get(path)
        if node:
            self._del_node_path(node, path)
            del self._path_node[path]

    def node_paths(self, dev, ino):
        node = '%s:%s' % (dev, ino)
        return self._node_paths[node]

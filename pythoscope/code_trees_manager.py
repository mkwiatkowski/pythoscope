import os

from pythoscope.logger import log
from pythoscope.util import string2filename, load_pickle_from


class CodeTreeNotFound(Exception):
    def __init__(self, module_subpath):
        Exception.__init__(self, "Couldn't find code tree for module %r." % module_subpath)
        self.module_subpath = module_subpath

class CodeTreesManager(object):
    def __init__(self, code_trees_path):
        raise NotImplementedError

    # :: (CodeTree, str) -> None
    def remember_code_tree(self, code_tree, module_subpath):
        raise NotImplementedError

    # :: str -> CodeTree
    def recall_code_tree(self, module_subpath):
        """Return code tree corresponding to a module located under given subpath.

        May raise CodeTreeNotFound exception.
        """
        raise NotImplementedError

    # :: str -> None
    def forget_code_tree(self, module_subpath):
        """Get rid of the CodeTree for a module located under given subpath.
        Do nothing if the module doesn't exist.
        """
        raise NotImplementedError

    def clear_cache(self):
        pass

class FilesystemCodeTreesManager(CodeTreesManager):
    """Manager of CodeTree instances that keeps at most one CodeTree instance
    in a memory, storing the rest in files.
    """
    def __init__(self, code_trees_path):
        self.code_trees_path = code_trees_path
        self._cached_code_tree = None

    def remember_code_tree(self, code_tree, module_subpath):
        log.debug("Saving code tree for module %r to a file and caching..." % \
                      module_subpath)
        code_tree.save(self._code_tree_path(module_subpath))
        self._cache(code_tree, module_subpath)

    def recall_code_tree(self, module_subpath):
        if self._is_cached(module_subpath):
            return self._cached_code_tree[1]
        try:
            log.debug("Loading code tree for module %r from a file and caching..." % \
                          module_subpath)
            code_tree = load_pickle_from(self._code_tree_path(module_subpath))
            self._cache(code_tree, module_subpath)
            return code_tree
        except IOError:
            raise CodeTreeNotFound(module_subpath)

    def forget_code_tree(self, module_subpath):
        try:
            os.remove(self._code_tree_path(module_subpath))
        except OSError:
            pass
        self._remove_from_cache(module_subpath)

    def clear_cache(self):
        if self._cached_code_tree:
            old_module_subpath, old_code_tree = self._cached_code_tree
            log.debug("Code tree for module %r gets out of cache, "\
                          "saving to a file..." %  old_module_subpath)
            old_code_tree.save(self._code_tree_path(old_module_subpath))
        self._cached_code_tree = None

    def _cache(self, code_tree, module_subpath):
        self.clear_cache()
        self._cached_code_tree = (module_subpath, code_tree)

    def _is_cached(self, module_subpath):
        return self._cached_code_tree and self._cached_code_tree[0] == module_subpath

    def _remove_from_cache(self, module_subpath):
        if self._is_cached(module_subpath):
            self._cached_code_tree = None

    def _code_tree_path(self, module_subpath):
        code_tree_filename = string2filename(module_subpath) + '.pickle'
        return os.path.join(self.code_trees_path, code_tree_filename)

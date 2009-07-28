import gc
import os.path

from mock import Mock

from pythoscope.store import CodeTree, CodeTreeNotFound, \
    FilesystemCodeTreesManager, Module

from assertions import *
from helper import TempDirectory


class TestFilesystemCodeTreesManager(TempDirectory):
    def setUp(self):
        super(TestFilesystemCodeTreesManager, self).setUp()
        self.manager = FilesystemCodeTreesManager(self.tmpdir)

    def assert_empty_cache(self):
        assert_equal(None, self.manager._cached_code_tree)

    def assert_cache(self, module_subpath):
        assert_equal(module_subpath, self.manager._cached_code_tree[0])

    def assert_recalled_tree(self, module_subpath, code):
        assert_equal(code, self.manager.recall_code_tree(module_subpath).code)

    def assert_code_tree_saved(self, module_subpath, saved=True):
        path = self.manager._code_tree_path(module_subpath)
        assert_equal(saved, os.path.exists(path))

    def assert_code_tree_not_saved(self, module_subpath):
        self.assert_code_tree_saved(module_subpath, saved=False)

    def assert_calls_once(self, mock, callback):
        """Assert that given callback calls given Mock object exactly once.
        """
        before_count = mock.call_count
        callback()
        assert_equal(before_count + 1, mock.call_count)

    def test_remembered_code_trees_can_be_recalled(self):
        code_tree = CodeTree(None)
        self.manager.remember_code_tree(code_tree, "module.py")

        assert_equal(code_tree, self.manager.recall_code_tree("module.py"))

    def test_remembered_and_forgotten_code_trees_cannot_be_recalled(self):
        code_tree = CodeTree(None)
        self.manager.remember_code_tree(code_tree, "module.py")
        self.manager.forget_code_tree("module.py")

        assert_raises(CodeTreeNotFound, lambda: self.manager.recall_code_tree("module.py"))

    def test_cache_is_empty_right_after_initialization(self):
        self.assert_empty_cache()

    def test_cache_is_empty_after_clearing(self):
        code_tree = CodeTree(None)
        self.manager.remember_code_tree(code_tree, "module.py")
        self.manager.clear_cache()

        self.assert_empty_cache()

    def test_cache_contains_the_last_recalled_or_remembered_code_tree(self):
        # We use numbers to identify CodeTrees. We cannot use their id, because
        # pickling doesn't preserve those.
        cts = map(CodeTree, [0, 1, 2])
        for i, ct in enumerate(cts):
            self.manager.remember_code_tree(ct, "module%d.py" % i)

        # Checking all combinations of recall/remember calls.
        self.assert_recalled_tree("module0.py", 0)
        self.assert_cache("module0.py")
        self.assert_recalled_tree("module1.py", 1)
        self.assert_cache("module1.py")
        self.manager.remember_code_tree(CodeTree(3), "module3.py")
        self.assert_cache("module3.py")
        self.manager.remember_code_tree(CodeTree(4), "module4.py")
        self.assert_cache("module4.py")
        self.assert_recalled_tree("module2.py", 2)
        self.assert_cache("module2.py")

    def test_remembering_code_tree_saves_it_to_the_filesystem(self):
        code_tree = CodeTree(None)
        self.manager.remember_code_tree(code_tree, "module.py")
        self.assert_code_tree_saved("module.py")

    def test_forgetting_code_tree_removes_its_file_from_the_filesystem(self):
        code_tree = CodeTree(None)
        self.manager.remember_code_tree(code_tree, "module.py")

        self.manager.forget_code_tree("module.py")
        self.assert_code_tree_not_saved("module.py")

    def test_when_clearing_cache_code_tree_currently_in_cache_is_saved_to_the_filesystem(self):
        code_tree = CodeTree(None)
        code_tree.save = Mock()
        self.manager.remember_code_tree(code_tree, "module.py")
        self.assert_cache("module.py")

        self.assert_calls_once(code_tree.save, self.manager.clear_cache)

    def test_code_tree_not_in_cache_can_be_garbage_collected(self):
        code_tree = CodeTree(None)
        self.manager.remember_code_tree(code_tree, "module.py")
        # Referred from the test and from the CodeTreesManager.
        assert_length(gc.get_referrers(code_tree), 2)

        self.manager.clear_cache()

        # No longer referred from the CodeTreesManager.
        assert_length(gc.get_referrers(code_tree), 1)

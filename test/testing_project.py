import os.path

from pythoscope.astbuilder import EmptyCode
from pythoscope.execution import Execution
from pythoscope.store import Project

from helper import MemoryCodeTreesManager


class TestingProject(Project):
    """Project subclass useful during testing.

    It contains handy creation methods, which can all be nested.
    """
    __test__ = False

    def __init__(self, path=os.path.realpath(".")):
        Project.__init__(self, path=path,
            code_trees_manager_class=MemoryCodeTreesManager)
        self._last_module = None
        self._all_catch_module = None

    def with_module(self, path="module.py"):
        modpath = os.path.join(self.path, path)
        self._last_module = self.create_module(modpath, code=EmptyCode())
        return self

    def with_all_catch_module(self):
        """All object lookups will go through this single module.
        """
        if self._all_catch_module is not None:
            raise ValueError("Already specified an all-catch module.")
        self.with_module()
        self._all_catch_module = self._last_module
        return self

    def with_object(self, obj):
        if self._last_module is None:
            raise ValueError("Tried to use with_object() without a module.")
        self._last_module.add_object(obj)
        return self

    def make_new_execution(self):
        return Execution(project=self)

    def find_object(self, type, name, modulename=None):
        if self._all_catch_module is not None:
            return self._all_catch_module.find_object(type, name)
        return Project.find_object(self, type, name, modulename)


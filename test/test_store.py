import os
from fixture import TempIO
from nose.tools import assert_equal, assert_raises

from pythoscope.store import Project, Module, Class, Function, ModuleNotFound,\
     module_path_to_test_path

from helper import assert_length, CustomSeparator

class TestProject:
    def test_can_be_saved_and_restored_from_file(self):
        tmpdir = TempIO()
        filepath = os.path.join(tmpdir, "project.pickle")
        modules = [Module(path='good_module.py', objects=[Class("AClass", ["amethod"]), Function("afunction")]),
                   Module(path='bad_module.py', errors=["Syntax error"])]

        project = Project(filepath, modules)
        project.save()
        project = Project.from_file(filepath)

        assert_equal(2, len(project.modules))
        assert_equal(2, len(project['good_module'].objects))
        assert_equal("AClass", project['good_module'].classes[0].name)
        assert_equal(["amethod"], project['good_module'].classes[0].methods)
        assert_equal("afunction", project['good_module'].functions[0].name)
        assert_equal(["Syntax error"], project['bad_module'].errors)

    def test_can_be_queried_for_modules_by_their_path(self):
        paths = ["module.py", "sub/dir/module.py", "package/__init__.py"]
        project = Project(modules=map(Module, paths))

        for path in paths:
            assert_equal(path, project[path].path)

    def test_raises_module_not_found_exception_when_no_module_like_that_is_present(self):
        project = Project()
        assert_raises(ModuleNotFound, lambda: project["whatever"])

    def test_can_be_queried_for_modules_by_their_locator(self):
        paths = ["module.py", "sub/dir/module.py", "package/__init__.py"]
        locators = ["module", "sub.dir.module", "package"]
        project = Project(modules=map(Module, paths))

        for path, locator in zip(paths, locators):
            assert_equal(path, project[locator].path)

    def test_replaces_old_module_objects_with_new_ones_during_add_modules(self):
        modules = map(Module, ["module.py", "sub/dir/module.py", "other/module.py"])
        new_module = Module("other/module.py")

        project = Project(modules=modules)
        project.add_modules([new_module])

        assert_length(project.modules, 3)
        assert project["other/module.py"] is new_module

class TestStoreWithCustomSeparator(CustomSeparator):
    def test_uses_system_specific_path_separator(self):
        module = Module("some#path.py")
        assert_equal("some.path", module.locator)

    def test_module_path_to_test_path_uses_system_specific_path_separator(self):
        assert_equal("test_pythoscope_store.py",
                     module_path_to_test_path("pythoscope#store.py"))
        assert_equal("test_pythoscope.py",
                     module_path_to_test_path("pythoscope#__init__.py"))

import os
from fixture import TempIO
from nose.tools import assert_equal, assert_raises

from pythoscope.store import Project, Module, Class, Function, ModuleNotFound

class TestProject:
    def test_can_be_saved_and_restored_from_file(self):
        modules = [Module(objects=[Class("AClass", ["amethod"]), Function("afunction")]),
                   Module(errors=["Syntax error"])]
        project = Project(modules)
        tmpdir = TempIO()
        filepath = os.path.join(tmpdir, "project.pickle")

        project.save_to_file(filepath)
        project = Project(filepath=filepath)

        assert_equal(2, len(project.modules))
        assert_equal(2, len(project.modules[0].objects))
        assert_equal("AClass", project.modules[0].classes[0].name)
        assert_equal(["amethod"], project.modules[0].classes[0].methods)
        assert_equal("afunction", project.modules[0].functions[0].name)
        assert_equal(["Syntax error"], project.modules[1].errors)

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

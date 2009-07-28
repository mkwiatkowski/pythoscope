import os
from cPickle import PicklingError

from pythoscope.store import Project, Class, Function, Method, TestClass, \
     TestMethod, ModuleNotFound
from pythoscope.inspector import remove_deleted_modules
from pythoscope.util import get_names, read_file_contents

from assertions import *
from helper import EmptyProject, P, ProjectInDirectory, ProjectWithModules, \
    UNPICKABLE_OBJECT, TempDirectory, putdir

# Let nose know that those aren't test classes.
TestClass.__test__ = False
TestMethod.__test__ = False


class TestProject:
    def test_can_be_queried_for_modules_by_their_path(self):
        paths = ["module.py", P("sub/dir/module.py"), P("package/__init__.py")]
        project = ProjectWithModules(paths)

        for path in paths:
            assert_equal(path, project[path].subpath)

    def test_raises_module_not_found_exception_when_no_module_like_that_is_present(self):
        project = EmptyProject()
        assert_raises(ModuleNotFound, lambda: project["whatever"])

    def test_can_be_queried_for_modules_by_their_locator(self):
        paths = ["module.py", P("sub/dir/module.py"), P("package/__init__.py")]
        locators = ["module", "sub.dir.module", "package"]
        project = ProjectWithModules(paths)

        for path, locator in zip(paths, locators):
            assert_equal(path, project[locator].subpath)

    def test_replaces_old_module_objects_with_new_ones_during_create_module(self):
        paths = ["module.py", P("sub/dir/module.py"), P("other/module.py")]
        project = ProjectWithModules(paths)

        new_module = project.create_module(P("other/module.py"))

        assert_length(project.get_modules(), 3)
        assert project[P("other/module.py")] is new_module

    def test_replaces_module_instance_in_test_cases_associated_modules_during_module_replacement(self):
        paths = ["module.py", P("sub/dir/module.py"), P("other/module.py")]
        project = ProjectWithModules(paths)
        test_class = TestClass(name='TestAnything', associated_modules=[project[P("other/module.py")]])
        project[P("other/module.py")].add_test_case(test_class)

        new_module = project.create_module(P("other/module.py"))

        assert_length(test_class.associated_modules, 1)
        assert test_class.associated_modules[0] is new_module


class TestProjectOnTheFilesystem(TempDirectory):
    def test_can_be_saved_and_restored_from_file(self):
        project = ProjectInDirectory(self.tmpdir).with_modules(["good_module.py", "bad_module.py"])
        project['good_module'].add_objects([Class("AClass", [Method("amethod")]),
                                            Function("afunction")])
        project['bad_module'].errors = ["Syntax error"]
        project.save()

        project = Project.from_directory(project.path)

        assert_equal(2, len(project.get_modules()))
        assert_equal(2, len(project['good_module'].objects))
        assert_equal(["AClass"], get_names(project['good_module'].classes))
        assert_equal(["amethod"], get_names(project['good_module'].classes[0].methods))
        assert_equal(["afunction"], get_names(project['good_module'].functions))
        assert_equal(["Syntax error"], project['bad_module'].errors)

    def _test_finds_new_test_directory(self, test_module_dir):
        putdir(self.tmpdir, ".pythoscope")
        putdir(self.tmpdir, test_module_dir)
        project = Project(self.tmpdir)
        assert_equal(test_module_dir, project.new_tests_directory)

    def test_finds_new_tests_directory(self):
        test_module_dirs = ["test", "functional_test", "unit_test",
                            "tests", "functional_tests", "unit_tests",
                            "pythoscope-tests", "unit-tests"]
        for test_module_dir in test_module_dirs:
            yield '_test_finds_new_test_directory', test_module_dir

    def test_removes_definitions_of_modules_that_dont_exist_anymore(self):
        project = ProjectInDirectory(self.tmpdir).with_modules(["module.py", "other_module.py", "test_module.py"])
        test_class = TestClass("TestSomething", associated_modules=[project["module"]])
        project["test_module.py"].add_test_case(test_class)
        project.save()

        os.remove(os.path.join(project.path, "other_module.py"))

        remove_deleted_modules(project)

        assert_not_raises(ModuleNotFound, lambda: project["module"])
        assert_raises(ModuleNotFound, lambda: project["other_module"])
        assert_not_raises(ModuleNotFound, lambda: project["test_module"])

    def test_doesnt_save_uncomplete_pickle_files(self):
        project = ProjectInDirectory(self.tmpdir)
        project.save()
        original_pickle = read_file_contents(project._get_pickle_path())

        # Inject unpickable object into project.
        project._injected_attr = UNPICKABLE_OBJECT
        try:
            project.save()
        except PicklingError:
            pass

        # Make sure that the original file wasn't overwritten.
        assert_equal_strings(original_pickle,
                             read_file_contents(project._get_pickle_path()))

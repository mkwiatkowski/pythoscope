import os

from fixture import TempIO
from nose.tools import assert_equal, assert_raises

from pythoscope.store import Project, Module, Class, Function, TestClass, \
     TestMethod, ModuleNotFound
from pythoscope.inspector import remove_deleted_modules

from helper import assert_length, assert_equal_sets, EmptyProject, \
     ProjectWithModules, ProjectWithRealModules, ProjectInDirectory, \
     assert_not_raises, get_test_cases

# Let nose know that those aren't test classes.
TestClass.__test__ = False
TestMethod.__test__ = False


def ProjectAndTestClass(test_module_name):
    project = ProjectWithModules(["module.py", test_module_name])
    test_class = TestClass("TestSomething", associated_modules=[project["module"]])
    return project, test_class

class TestProject:
    def test_can_be_saved_and_restored_from_file(self):
        project = ProjectWithRealModules(["good_module.py", "bad_module.py"])
        project['good_module'].objects = [Class("AClass", ["amethod"]), Function("afunction")]
        project['bad_module'].errors = ["Syntax error"]
        project.save()

        # Make a reference to TempIO, so it doesn't auto-destruct.
        tmpdir = project._tmpdir

        project = Project.from_directory(project.path)

        assert_equal(2, len(project.get_modules()))
        assert_equal(2, len(project['good_module'].objects))
        assert_equal("AClass", project['good_module'].classes[0].name)
        assert_equal(["amethod"], project['good_module'].classes[0].methods)
        assert_equal("afunction", project['good_module'].functions[0].name)
        assert_equal(["Syntax error"], project['bad_module'].errors)

    def test_can_be_queried_for_modules_by_their_path(self):
        paths = ["module.py", "sub/dir/module.py", "package/__init__.py"]
        project = ProjectWithModules(paths)

        for path in paths:
            assert_equal(path, project[path].subpath)

    def test_raises_module_not_found_exception_when_no_module_like_that_is_present(self):
        project = EmptyProject()
        assert_raises(ModuleNotFound, lambda: project["whatever"])

    def test_can_be_queried_for_modules_by_their_locator(self):
        paths = ["module.py", "sub/dir/module.py", "package/__init__.py"]
        locators = ["module", "sub.dir.module", "package"]
        project = ProjectWithModules(paths)

        for path, locator in zip(paths, locators):
            assert_equal(path, project[locator].subpath)

    def test_replaces_old_module_objects_with_new_ones_during_create_module(self):
        paths = ["module.py", "sub/dir/module.py", "other/module.py"]
        project = ProjectWithModules(paths)

        new_module = project.create_module("other/module.py")

        assert_length(project.get_modules(), 3)
        assert project["other/module.py"] is new_module

    def test_replaces_module_instance_in_test_cases_associated_modules_during_module_replacement(self):
        paths = ["module.py", "sub/dir/module.py", "other/module.py"]
        project = ProjectWithModules(paths)
        test_class = TestClass(name='TestAnything', associated_modules=[project["other/module.py"]])
        project.add_test_case(test_class)

        new_module = project.create_module("other/module.py")

        assert_length(test_class.associated_modules, 1)
        assert test_class.associated_modules[0] is new_module

    def test_adds_new_test_methods_to_existing_test_classes_inside_application_modules(self):
        project = EmptyProject()
        application_class = Class("Something", [])
        test_class = TestClass("TestSomething")
        module = project.create_module("somethings.py")
        module.add_test_case(test_class)

        new_test_method = TestMethod("test_new_method")
        new_test_class = TestClass("TestSomething", test_cases=[new_test_method])
        project.add_test_case(new_test_class)

        assert_length(get_test_cases(project), 1)
        assert_equal_sets([new_test_method], test_class.test_cases)
        assert new_test_method.parent is test_class

    def test_finds_associated_test_modules_that_use_different_name_conventions(self):
        test_module_names = ["test_module.py", "testModule.py", "TestModule.py",
                             "tests_module.py", "testsModule.py", "TestsModule.py",
                             "module_test.py", "moduleTest.py", "ModuleTest.py",
                             "module_tests.py", "moduleTests.py", "ModuleTests.py"]

        for test_module_name in test_module_names:
            project, test_class = ProjectAndTestClass(test_module_name)
            assert project[test_module_name] is project._find_test_module(test_class)

    def test_finds_associated_test_modules_inside_test_directories(self):
        for test_module_dir in ["test", "tests"]:
            test_module_name = os.path.join(test_module_dir, "test_module.py")
            project, test_class = ProjectAndTestClass(test_module_name)
            assert project[test_module_name] is project._find_test_module(test_class)

    def test_finds_associated_test_modules_inside_new_tests_directory(self):
        new_tests_directory = "something"
        test_module_name = os.path.join(new_tests_directory, "test_module.py")
        project, test_class = ProjectAndTestClass(test_module_name)
        project.new_tests_directory = new_tests_directory
        assert project[test_module_name] is project._find_test_module(test_class)

    def test_finds_new_tests_directory(self):
        test_module_dirs = ["test", "functional_test", "unit_test",
                            "tests", "functional_tests", "unit_tests",
                            "pythoscope-tests", "unit-tests"]

        for test_module_dir in test_module_dirs:
            tmpdir = TempIO()
            tmpdir.mkdir(".pythoscope")
            tmpdir.mkdir(test_module_dir)
            project = Project(tmpdir)

            assert_equal(test_module_dir, project.new_tests_directory)

    def test_removes_definitions_of_modules_that_dont_exist_anymore(self):
        project = ProjectWithRealModules(["module.py", "other_module.py", "test_module.py"])
        test_class = TestClass("TestSomething", associated_modules=[project["module"]])
        project.add_test_case(test_class)
        project.save()

        os.remove(os.path.join(project.path, "other_module.py"))

        remove_deleted_modules(project)

        assert_not_raises(ModuleNotFound, lambda: project["module"])
        assert_raises(ModuleNotFound, lambda: project["other_module"])
        assert_not_raises(ModuleNotFound, lambda: project["test_module"])

class TestProjectWithTestModule:
    def setUp(self):
        self.project = EmptyProject()
        self.existing_test_class = TestClass("TestSomething")
        self.test_module = self.project.create_module("test_module.py")
        self.test_module.add_test_case(self.existing_test_class)

    def test_attaches_test_class_to_test_module_with_most_test_cases_for_associated_module(self):
        module = self.project.create_module("module.py")
        irrelevant_test_module = self.project.create_module("irrelevant_test_module.py")
        self.existing_test_class.associated_modules = [module]

        new_test_class = TestClass("new", associated_modules=[module])
        self.project.add_test_case(new_test_class)

        assert new_test_class in self.test_module.test_cases

    def test_doesnt_overwrite_existing_test_classes_by_default(self):
        test_class = TestClass("TestSomething")
        self.project.add_test_case(test_class)

        assert_length(get_test_cases(self.project), 1)

    def test_adds_new_test_classes_to_existing_test_module(self):
        test_class = TestClass("TestSomethingNew")
        self.project.add_test_case(test_class)

        assert_equal_sets([self.existing_test_class, test_class],
                          get_test_cases(self.project))

    def test_adds_new_test_methods_to_existing_test_classes(self):
        test_method = TestMethod("test_new_method")
        test_class = TestClass("TestSomething", test_cases=[test_method])
        self.project.add_test_case(test_class)

        assert_length(get_test_cases(self.project), 1)
        assert get_test_cases(self.project)[0] is test_method.parent
        assert test_method.parent is not test_class

    def test_after_adding_new_test_case_to_class_its_module_is_marked_as_changed(self):
        self.existing_test_class.add_test_case(TestMethod("test_something_new"))

        assert self.test_module.changed

    def test_merges_imports_during_merging_of_test_classes(self):
        test_class = TestClass("TestSomething", imports=['new_import'])
        self.project.add_test_case(test_class)

        assert_equal(['new_import'], self.test_module.imports)

    def test_doesnt_overwrite_existing_test_methods_by_default(self):
        test_method = TestMethod("test_method")
        test_class = TestClass("TestSomething", test_cases=[test_method])
        self.project.add_test_case(test_class)

        assert_equal([test_method],
                     get_test_cases(self.project)[0].test_cases)

        # Let's try adding the same method again.
        new_test_method = TestMethod("test_method")
        new_test_class = TestClass("TestSomething", test_cases=[new_test_method])
        self.project.add_test_case(new_test_class)

        assert_equal([test_method],
                     get_test_cases(self.project)[0].test_cases)

    def test_overwrites_existing_test_methods_with_force_option(self):
        test_method = TestMethod("test_method")
        test_class = TestClass("TestSomething", test_cases=[test_method])
        self.project.add_test_case(test_class)

        assert_equal([test_method],
                     get_test_cases(self.project)[0].test_cases)

        # Let's try adding the same method again with a force option
        # set to True.
        new_test_method = TestMethod("test_method")
        new_test_class = TestClass("TestSomething", test_cases=[new_test_method])
        self.project.add_test_case(new_test_class, force=True)

        # The class is still the same.
        assert_equal([self.existing_test_class],
                     get_test_cases(self.project))
        # But the method got replaced.
        assert_equal([new_test_method],
                     get_test_cases(self.project)[0].test_cases)

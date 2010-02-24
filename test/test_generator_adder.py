import os

from pythoscope.astbuilder import parse, EmptyCode
from pythoscope.generator import TestMethodDescription, TestGenerator
from pythoscope.generator.adder import add_test_case_to_project, add_test_case, \
    find_test_module, module_path_to_test_path, replace_test_case
from pythoscope.inspector.static import inspect_code
from pythoscope.store import TestClass, TestMethod

from assertions import *
from factories import create
from helper import get_test_cases, CapturedLogger, CustomSeparator, \
    EmptyProject, ProjectWithModules


def ProjectAndTestClass(test_module_name):
    project = ProjectWithModules(["module.py", test_module_name])
    test_class = TestClass("TestSomething", associated_modules=[project["module"]])
    return project, test_class


class TestModulePathToTestPathWithCustomSeparator(CustomSeparator):
    def test_module_path_to_test_path_uses_system_specific_path_separator(self):
        assert_equal("test_pythoscope_store.py",
                     module_path_to_test_path("pythoscope#store.py"))
        assert_equal("test_pythoscope.py",
                     module_path_to_test_path("pythoscope#__init__.py"))

class TestGeneratorAdder:
    def test_replacing_a_test_case_removes_it_from_the_list_of_objects_and_list_of_test_cases(self):
        project = EmptyProject()
        module = project.create_module("module.py", code=parse("# only comments"))
        test_class = create(TestClass, name="TestSomething")
        new_test_class = create(TestClass, name="TestSomethingElse")
        add_test_case(module, test_class)

        replace_test_case(module, test_class, new_test_class)

        assert_equal([new_test_class], module.objects)
        assert_equal([new_test_class], module.test_cases)

    def test_finds_associated_test_modules_that_use_different_name_conventions(self):
        test_module_names = ["test_module.py", "testModule.py", "TestModule.py",
                             "tests_module.py", "testsModule.py", "TestsModule.py",
                             "module_test.py", "moduleTest.py", "ModuleTest.py",
                             "module_tests.py", "moduleTests.py", "ModuleTests.py"]

        for test_module_name in test_module_names:
            project, test_class = ProjectAndTestClass(test_module_name)
            assert project[test_module_name] is find_test_module(project, test_class)

    def test_finds_associated_test_modules_inside_test_directories(self):
        for test_module_dir in ["test", "tests"]:
            test_module_name = os.path.join(test_module_dir, "test_module.py")
            project, test_class = ProjectAndTestClass(test_module_name)
            assert project[test_module_name] is find_test_module(project, test_class)

    def test_finds_associated_test_modules_inside_new_tests_directory(self):
        new_tests_directory = "something"
        test_module_name = os.path.join(new_tests_directory, "test_module.py")
        project, test_class = ProjectAndTestClass(test_module_name)
        project.new_tests_directory = new_tests_directory
        assert project[test_module_name] is find_test_module(project, test_class)

    def test_adds_new_test_methods_to_existing_test_classes_inside_application_modules(self):
        project = EmptyProject().with_module("somethings.py")
        test_class = create(TestClass, name="TestSomething")
        add_test_case(project["somethings"], test_class)

        method = create(TestMethod)
        generated_test_class = create(TestClass, name="TestSomething",
          test_cases=[method])
        add_test_case_to_project(project, generated_test_class)

        assert_length(get_test_cases(project), 1)
        assert_equal_sets([method], test_class.test_cases)
        assert method.parent is test_class

class TestGeneratorAdderForProjectWithTestModule(CapturedLogger):
    def setUp(self):
        CapturedLogger.setUp(self)
        self.project = EmptyProject()
        self.existing_test_class = create(TestClass, name="TestSomething")
        self.test_module = self.project.create_module("test_module.py", code=EmptyCode())
        add_test_case(self.test_module, self.existing_test_class)

    def _associate_module_with_existing_test_class(self):
        self.associated_module = self.project.create_module("module.py")
        self.existing_test_class.associated_modules = [self.associated_module]

    def test_attaches_test_class_to_test_module_with_most_test_cases_for_associated_module(self):
        self.project.create_module("irrelevant_test_module.py")
        self._associate_module_with_existing_test_class()

        new_test_class = create(TestClass, name="new",
          associated_modules=[self.associated_module])
        add_test_case_to_project(self.project, new_test_class)

        assert new_test_class in self.test_module.test_cases

    def test_doesnt_overwrite_existing_test_classes_by_default(self):
        test_class = create(TestClass, name="TestSomething")
        add_test_case_to_project(self.project, test_class)

        assert_length(get_test_cases(self.project), 1)

    def test_adds_new_test_classes_to_existing_test_module(self):
        test_class = create(TestClass, name="TestSomethingNew",
          associated_modules=[self.project.create_module("module.py")])
        add_test_case_to_project(self.project, test_class)

        assert_equal_sets([self.existing_test_class, test_class],
                          get_test_cases(self.project))

    def test_adds_new_test_methods_to_existing_test_classes(self):
        test_method = create(TestMethod, name="test_new_method")
        test_class = create(TestClass, name="TestSomething", test_cases=[test_method])
        add_test_case_to_project(self.project, test_class)

        assert_length(get_test_cases(self.project), 1)
        assert get_test_cases(self.project)[0] is test_method.parent
        assert test_method.parent is not test_class
        # The right message was issued.
        assert_contains_once(self._get_log_output(),
                             "Adding generated test_new_method to TestSomething in test_module.py.")

    def test_after_adding_new_test_case_to_class_its_module_is_marked_as_changed(self):
        add_test_case(self.existing_test_class, create(TestMethod, name="test_something_new"))

        assert self.test_module.changed

    def test_merges_imports_during_merging_of_test_classes(self):
        test_class = TestClass("TestSomething", imports=['new_import'])
        add_test_case_to_project(self.project, test_class)

        assert_equal(['new_import'], self.test_module.imports)

    def test_doesnt_overwrite_existing_test_methods_by_default(self):
        test_method = create(TestMethod, name="test_method")
        test_class = create(TestClass, name="TestSomething",
          test_cases=[test_method])
        add_test_case_to_project(self.project, test_class)

        assert_equal([test_method],
                     get_test_cases(self.project)[0].test_cases)

        # Let's try adding the same method again.
        new_test_method = create(TestMethod, name="test_method")
        new_test_class = create(TestClass, name="TestSomething",
          test_cases=[new_test_method])
        add_test_case_to_project(self.project, new_test_class)

        assert_equal([test_method],
                     get_test_cases(self.project)[0].test_cases)
        # The right message was issued.
        assert_contains_once(self._get_log_output(),
                             "Test case TestSomething.test_method already exists in test_module.py, skipping.")

    def test_overwrites_existing_test_methods_with_force_option(self):
        test_method = create(TestMethod, name="test_method")
        test_class = create(TestClass, name="TestSomething", test_cases=[test_method])
        add_test_case_to_project(self.project, test_class)

        assert_equal([test_method],
                     get_test_cases(self.project)[0].test_cases)

        # Let's try adding the same method again with a force option
        # set to True.
        new_test_method = create(TestMethod, name="test_method")
        new_test_class = create(TestClass, name="TestSomething",
          test_cases=[new_test_method])
        add_test_case_to_project(self.project, new_test_class, force=True)

        # The class is still the same.
        assert_equal([self.existing_test_class],
                     get_test_cases(self.project))
        # But the method got replaced.
        assert_equal([new_test_method],
                     get_test_cases(self.project)[0].test_cases)
        # The right message was issued.
        assert_contains_once(self._get_log_output(),
                             "Replacing TestSomething.test_method from test_module.py with generated version.")

    def test_should_not_touch_modules_with_errors(self):
        project = EmptyProject()
        module = project.create_module("module.py")
        test_module = project.create_module("test_module.py",
            errors=[Exception()])
        add_test_case_to_project(project,
            create(TestClass, associated_modules=[module]))
        assert test_module.changed is False

    def test_should_emit_warning_when_trying_to_add_test_to_module_with_errors(self):
        project = EmptyProject()
        module = project.create_module("module.py")
        project.create_module("test_module.py", errors=[Exception()])
        add_test_case_to_project(project,
            create(TestClass, name="FooTest", associated_modules=[module]))
        assert_contains_once(self._get_log_output(),
            "WARNING: Not adding FooTest to test_module.py, because "
            "of a failed inspection.")

class TestGeneratorAdderOnCode:
    def setUp(self):
        self.generator = TestGenerator()
        self.project = EmptyProject()
        self.module = self.project.create_module("module.py")
        self.test_module = self.project.create_module("test_module.py")

    def _test_module_from_code(self, code):
        return inspect_code(self.project, "test_module.py", code)

    def _test_class_from_code(self, code, name, method):
        return self.generator._generate_test_class(name,
            [TestMethodDescription(method)], self.module, code)

    def test_appends_new_test_methods_to_test_classes_with_proper_indentation(self):
        module = self._test_module_from_code(
            "class NewTestClass(unittest.TestCase):\n"\
            "    def test_some_method(self):\n"\
            "        assert False # c'mon, implement me\n")
        klass = self._test_class_from_code(
            "class NewTestClass(unittest.TestCase):\n"\
            "    def test_new_method(self):\n"\
            "        assert True # ha!\n",
            "NewTestClass", "test_new_method")
        expected_output = "class NewTestClass(unittest.TestCase):\n"\
            "    def test_some_method(self):\n"\
            "        assert False # c'mon, implement me\n\n"\
            "    def test_new_method(self):\n"\
            "        assert True # ha!\n"

        add_test_case_to_project(self.project, klass)

        assert_equal_strings(expected_output, module.get_content())

    def test_keeps_future_imports_first(self):
        module = self._test_module_from_code("from __future__ import division\n")
        self.generator.ensure_import(('nose', 'SkipTest'))
        klass = self._test_class_from_code("", "TestClass", "test_method")

        add_test_case_to_project(self.project, klass)

        assert_matches(r"from __future__ import division.*from nose import SkipTest",
            module.get_content())

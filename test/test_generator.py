import os
import re

from fixture import TempIO
from nose.tools import assert_equal, assert_not_equal, assert_raises

from pythoscope.generator import generate_test_modules, GenerationError,\
     module2testpath
from pythoscope.store import Project, Module, Class, Function
from pythoscope.util import read_file_contents

from helper import assert_contains, assert_doesnt_contain, assert_length,\
     CustomSeparator, generate_single_test_module

# Let nose know that those aren't test functions.
generate_test_modules.__test__ = False

class TestGenerator:
    def test_generates_unittest_boilerplate(self):
        result = generate_single_test_module(Module())
        assert_contains(result, "import unittest")
        assert_contains(result, "if __name__ == '__main__':\n    unittest.main()")

    def test_generates_test_class_for_each_production_class(self):
        module = Module(objects=[Class('SomeClass', ['some_method']),
                                 Class('AnotherClass', ['another_method'])])
        result = generate_single_test_module(module)
        assert_contains(result, "class TestSomeClass(unittest.TestCase):")
        assert_contains(result, "class TestAnotherClass(unittest.TestCase):")

    def test_generates_test_class_for_each_stand_alone_function(self):
        module = Module(objects=[Function('some_function'),
                                 Function('another_function')])
        result = generate_single_test_module(module)
        assert_contains(result, "class TestSomeFunction(unittest.TestCase):")
        assert_contains(result, "class TestAnotherFunction(unittest.TestCase):")

    def test_generates_test_method_for_each_production_method_and_function(self):
        module = Module(objects=[Class('SomeClass', ['some_method']),
                                 Class('AnotherClass', ['another_method', 'one_more']),
                                 Function('a_function')])
        result = generate_single_test_module(module)
        assert_contains(result, "def test_some_method(self):")
        assert_contains(result, "def test_another_method(self):")
        assert_contains(result, "def test_one_more(self):")
        assert_contains(result, "def test_a_function(self):")

    def test_generates_nice_name_for_init_method(self):
        module = Module(objects=[Class('SomeClass', ['__init__'])])
        result = generate_single_test_module(module)
        assert_contains(result, "def test_object_initialization(self):")

    def test_ignores_empty_classes(self):
        module = Module(objects=[Class('SomeClass', [])])
        result = generate_single_test_module(module)
        assert_doesnt_contain(result, "class TestSomeClass(unittest.TestCase):")

    def test_can_generate_nose_style_tests(self):
        module = Module(objects=[Class('AClass', ['a_method']),
                                 Function('a_function')])
        result = generate_single_test_module(module, template='nose')

        assert_doesnt_contain(result, "import unittest")
        assert_contains(result, "from nose import SkipTest")

        assert_contains(result, "class TestAClass:")
        assert_contains(result, "class TestAFunction:")

        assert_contains(result, "raise SkipTest")
        assert_doesnt_contain(result, "assert False")

        assert_doesnt_contain(result, "if __name__ == '__main__':\n    unittest.main()")

    def test_ignores_private_methods(self):
        module = Module(objects=[Class('SomeClass', ['_semiprivate', '__private', '__eq__'])])
        result = generate_single_test_module(module)
        assert_doesnt_contain(result, "class TestSomeClass(unittest.TestCase):")

    def test_ignores_private_functions(self):
        module = Module(objects=[Function('_function')])
        result = generate_single_test_module(module)
        assert_doesnt_contain(result, "class")

    def test_ignores_exception_classes(self):
        module = Module(objects=[Class('ExceptionClass', ['method'], bases=['Exception'])])
        result = generate_single_test_module(module)
        assert_doesnt_contain(result, "class TestExceptionClass(unittest.TestCase):")

    def test_ignores_unittest_classes(self):
        module = Module(objects=[Class('TestClass', ['test_method'], bases=['unittest.TestCase'])])
        result = generate_single_test_module(module)
        assert_doesnt_contain(result, "class TestTestClass(unittest.TestCase):")

    def test_uses_existing_destination_directory(self):
        destdir = TempIO()
        generate_test_modules(Project('pfile'), [], destdir, 'unittest')
        # Simply make sure it doesn't raise any exceptions.

    def test_raises_an_exception_if_destdir_is_a_file(self):
        tmpdir = TempIO()
        destdir = tmpdir.putfile("file", "its content")
        assert_raises(GenerationError,
                      lambda: generate_test_modules(Project('pfile'), [], destdir, 'unittest'))

    def test_doesnt_overwrite_existing_files(self):
        existing_test_case = "# test"
        project, destdir, existing_file = self._create_project_with_test(existing_test_case)

        generate_test_modules(project, ["project"], destdir, 'unittest')
        assert_equal(existing_test_case, read_file_contents(existing_file))

    def test_overwrites_existing_files_with_force_option(self):
        existing_test_case = "# test"
        project, destdir, existing_file = self._create_project_with_test(existing_test_case, [Function("function")])

        generate_test_modules(project, ["project"], destdir, 'unittest', force=True)
        assert_not_equal(existing_test_case, read_file_contents(existing_file))

    def test_doesnt_generate_test_files_with_no_test_cases(self):
        project = Project('pfile', modules=[Module("project.py")])
        destdir = TempIO()
        test_file = os.path.join(destdir, "test_project.py")

        generate_test_modules(project, ["project"], destdir, 'unittest')

        assert not os.path.exists(test_file)

    def test_appends_new_test_classes_to_existing_test_files(self):
        existing_test_case = "class TestSomething: pass\n\n"
        project, destdir, existing_file = self._create_project_with_test(existing_test_case, [Function("function")])

        generate_test_modules(project, ["project"], destdir, 'unittest')

        assert_contains(read_file_contents(existing_file), existing_test_case)
        assert_contains(read_file_contents(existing_file), "class TestFunction(unittest.TestCase):")

    def test_adds_imports_to_existing_test_files_only_if_they_arent_present(self):
        cases = ["import unittest", "from nose import SkipTest"]
        for case in cases:
            existing_test_case = "%s\n\nclass TestSomething: pass\n\n" % case
            project, destdir, existing_file = self._create_project_with_test(existing_test_case, [Function("function")])

            generate_test_modules(project, ["project"], destdir, 'unittest')

            assert_length(re.findall(case, read_file_contents(existing_file)), 1)

    def _create_project_with_test(self, test_contents, objects=[]):
        project = Project('pfile', modules=[Module("project.py", objects)])
        destdir = TempIO()
        existing_file = destdir.putfile("test_project.py", test_contents)
        return project, destdir, existing_file

class TestGeneratorWithCustomSeparator(CustomSeparator):
    def test_module2testpath_uses_system_specific_path_separator(self):
        assert_equal("test_pythoscope_store.py",
                     module2testpath("pythoscope#store.py"))
        assert_equal("test_pythoscope.py",
                     module2testpath("pythoscope#__init__.py"))

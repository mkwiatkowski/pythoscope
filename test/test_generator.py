import os
import re
import time

from fixture import TempIO
from nose.tools import assert_equal, assert_not_equal, assert_raises

from pythoscope.astvisitor import parse
from pythoscope.generator import add_tests_to_project, GenerationError
from pythoscope.store import Project, Module, Class, Function, TestModule,\
     ModuleNeedsAnalysis
from pythoscope.util import read_file_contents

from helper import assert_contains, assert_doesnt_contain, assert_length,\
     CustomSeparator, generate_single_test_module

# Let nose know that those aren't test functions/classes.
add_tests_to_project.__test__ = False
TestModule.__test__ = False

class TestGenerator:
    def test_generates_unittest_boilerplate(self):
        result = generate_single_test_module(Module(objects=[Function('function')]))
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

    def test_generates_content_in_right_order(self):
        result = generate_single_test_module(Module(objects=[Function('function')]))

        assert re.match(r"import unittest.*?class TestFunction.*?if __name__ == '__main__'", result, re.DOTALL)

class TestGeneratorWithDestDir:
    def setUp(self):
        self.destdir = TempIO()
        self.empty_module = Module("project.py")
        self.module_with_function = Module("project.py", [Function("function")])
        self.test_module = TestModule(path=os.path.join(self.destdir, "test_project.py"))
        self.other_test_module = TestModule(os.path.join(self.destdir, "test_other.py"))

    def test_uses_existing_destination_directory(self):
        add_tests_to_project(Project(), [], self.destdir, 'unittest')
        # Simply make sure it doesn't raise any exceptions.

    def test_raises_an_exception_if_destdir_is_a_file(self):
        destfile = self.destdir.putfile("file", "its content")
        assert_raises(GenerationError,
                      lambda: add_tests_to_project(Project(), [], destfile, 'unittest'))

    def test_doesnt_overwrite_existing_files_which_werent_analyzed(self):
        TEST_CONTENTS = "# test"
        # File exists, but project does NOT contain corresponding TestModule.
        project = Project(modules=[self.module_with_function])
        existing_file = self.destdir.putfile("test_project.py", TEST_CONTENTS)

        assert_raises(ModuleNeedsAnalysis,
                      lambda: add_tests_to_project(project, ["project"], self.destdir, 'unittest'))
        assert_equal(TEST_CONTENTS, read_file_contents(existing_file))

    def test_doesnt_overwrite_existing_files_which_were_modified_since_last_analysis(self):
        TEST_CONTENTS = "# test"
        # File exists, and project contains corresponding, but outdated, TestModule.
        project = Project(modules=[self.module_with_function, self.test_module])
        existing_file = self.destdir.putfile("test_project.py", TEST_CONTENTS)
        self.test_module.created = time.time() - 3600

        assert_raises(ModuleNeedsAnalysis,
                      lambda: add_tests_to_project(project, ["project"], self.destdir, 'unittest'))
        assert_equal(TEST_CONTENTS, read_file_contents(existing_file))

    def test_doesnt_generate_test_files_with_no_test_cases(self):
        project = Project(modules=[self.empty_module])
        test_file = os.path.join(self.destdir, "test_project.py")

        add_tests_to_project(project, ["project"], self.destdir, 'unittest')

        assert not os.path.exists(test_file)

    def test_appends_new_test_classes_to_existing_test_files(self):
        TEST_CONTENTS = "class TestSomething: pass\n\n"
        self.test_module.code = parse(TEST_CONTENTS)
        project = Project(modules=[self.module_with_function, self.test_module])

        add_tests_to_project(project, ["project"], self.destdir, 'unittest')

        assert_contains(self.test_module.get_content(), TEST_CONTENTS)
        assert_contains(self.test_module.get_content(), "class TestFunction(unittest.TestCase):")

    def test_adds_imports_to_existing_test_files_only_if_they_arent_present(self):
        imports = ["unittest", ("nose", "SkipTest")]
        for imp in imports:
            self.test_module.imports = [imp]
            project = Project(modules=[self.module_with_function, self.test_module])

            add_tests_to_project(project, ["project"], self.destdir, 'unittest')

            assert_equal([imp], self.test_module.imports)

    def test_associates_test_cases_with_application_modules(self):
        project = Project(modules=[self.module_with_function])

        add_tests_to_project(project, ["project"], self.destdir, 'unittest')

        project_test_cases = list(project.test_cases_iter())
        assert_length(project_test_cases, 1)
        assert_equal(project_test_cases[0].associated_modules, [self.module_with_function])

    def test_creates_new_test_module_if_no_of_the_existing_match(self):
        project = Project(modules=[self.module_with_function, self.other_test_module])

        add_tests_to_project(project, ["project"], self.destdir, 'unittest')

        project_test_cases = list(project.test_cases_iter())
        assert_length(project_test_cases, 1)
        assert_length(self.other_test_module.test_cases, 0)

    def test_chooses_the_right_existing_test_module_for_new_test_case(self):
        project = Project(modules=[self.module_with_function, self.other_test_module, self.test_module])

        add_tests_to_project(project, ["project"], self.destdir, 'unittest')

        assert_length(self.test_module.test_cases, 1)
        assert_length(self.other_test_module.test_cases, 0)

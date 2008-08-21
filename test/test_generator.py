from fixture import TempIO

from nose.tools import assert_raises

from pythoscope.generator import generate_test_module, generate_test_modules,\
     GenerationError
from pythoscope.store import Project, Module, Class, Function

from helper import assert_contains, assert_doesnt_contain

# Let nose know that those aren't test functions.
generate_test_module.__test__ = False
generate_test_modules.__test__ = False

class TestGenerator:
    def test_generates_unittest_boilerplate(self):
        result = generate_test_module(Module())
        assert_contains(result, "import unittest")
        assert_contains(result, "if __name__ == '__main__':\n    unittest.main()")

    def test_generates_test_class_for_each_production_class(self):
        module = Module(objects=[Class('SomeClass', ['some_method']),
                                 Class('AnotherClass', ['another_method'])])
        result = generate_test_module(module)
        assert_contains(result, "class TestSomeClass(unittest.TestCase):")
        assert_contains(result, "class TestAnotherClass(unittest.TestCase):")

    def test_generates_test_class_for_each_stand_alone_function(self):
        module = Module(objects=[Function('some_function'),
                                 Function('another_function')])
        result = generate_test_module(module)
        assert_contains(result, "class TestSomeFunction(unittest.TestCase):")
        assert_contains(result, "class TestAnotherFunction(unittest.TestCase):")

    def test_generates_test_method_for_each_production_method_and_function(self):
        module = Module(objects=[Class('SomeClass', ['some_method']),
                                 Class('AnotherClass', ['another_method', 'one_more']),
                                 Function('a_function')])
        result = generate_test_module(module)
        assert_contains(result, "def test_some_method(self):")
        assert_contains(result, "def test_another_method(self):")
        assert_contains(result, "def test_one_more(self):")
        assert_contains(result, "def test_a_function(self):")

    def test_generates_nice_name_for_init_method(self):
        module = Module(objects=[Class('SomeClass', ['__init__'])])
        result = generate_test_module(module)
        assert_contains(result, "def test_object_initialization(self):")

    def test_ignores_empty_classes(self):
        module = Module(objects=[Class('SomeClass', [])])
        result = generate_test_module(module)
        assert_doesnt_contain(result, "class TestSomeClass(unittest.TestCase):")

    def test_can_generate_nose_style_tests(self):
        module = Module(objects=[Class('AClass', ['a_method']),
                                 Function('a_function')])
        result = generate_test_module(module, template='nose')

        assert_doesnt_contain(result, "import unittest")
        assert_contains(result, "from nose import SkipTest")

        assert_contains(result, "class TestAClass:")
        assert_contains(result, "class TestAFunction:")

        assert_contains(result, "raise SkipTest")
        assert_doesnt_contain(result, "assert False")

        assert_doesnt_contain(result, "if __name__ == '__main__':\n    unittest.main()")

    def test_ignores_private_methods(self):
        module = Module(objects=[Class('SomeClass', ['_semiprivate', '__private', '__eq__'])])
        result = generate_test_module(module)
        assert_doesnt_contain(result, "class TestSomeClass(unittest.TestCase):")

    def test_ignores_exception_classes(self):
        module = Module(objects=[Class('ExceptionClass', ['method'], bases=['Exception'])])
        result = generate_test_module(module)
        assert_doesnt_contain(result, "class TestExceptionClass(unittest.TestCase):")

    def test_uses_existing_destination_directory(self):
        destdir = TempIO()
        generate_test_modules(Project(), [], destdir, 'unittest')
        # Simply make sure it doesn't raise any exceptions.

    def test_raises_an_exception_if_destdir_is_a_file(self):
        tmpdir = TempIO()
        destdir = tmpdir.putfile("file", "its content")
        assert_raises(GenerationError,
                      lambda: generate_test_modules(Project(), [], destdir, 'unittest'))

from pythoscope.generator import generate_test_module
from pythoscope.collector import Module, Class, Function

from helper import assert_contains

# Let nose know that this isn't a test function.
generate_test_module.__test__ = False

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

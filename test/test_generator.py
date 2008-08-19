from pythoscope.generator import generate_test_module
from pythoscope.collector import Module

from helper import assert_contains

# Let nose know that this isn't a test function.
generate_test_module.__test__ = False

class TestGenerator:
    def test_generates_unittest_boilerplate(self):
        result = generate_test_module(Module())
        assert_contains(result, "import unittest")
        assert_contains(result, "if __name__ == '__main__':\n    unittest.main()")

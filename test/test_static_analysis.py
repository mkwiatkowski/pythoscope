from nose.tools import assert_equal
from helper import data, read_data

from pythoscope.collector import collect_information_from_module
from pythoscope.generator import generate_test_module

# Let nose know that this isn't a test function.
generate_test_module.__test__ = False

class TestStaticAnalysis:
    def test_generates_test_stubs(self):
        module_path = data("static_analysis_module.py")
        expected_result = read_data("static_analysis_output.py")

        info = collect_information_from_module(module_path)
        result = generate_test_module(info)

        assert_equal(expected_result, result)

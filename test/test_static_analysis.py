from nose.tools import assert_equal
from helper import data, read_data

from pythoscope.collector import collect_information_from_module

from helper import generate_single_test_module

class TestStaticAnalysis:
    def test_generates_test_stubs(self):
        module_path = data("static_analysis_module.py")
        expected_result = read_data("static_analysis_output.py")

        module = collect_information_from_module(module_path)
        result = generate_single_test_module(module)

        assert_equal(expected_result, result)

from nose.tools import assert_equal
from helper import data, read_data

import pythoscope

class TestStaticAnalysis:
    def test_generates_test_stubs(self):
        module_path = data("static_analysis_module.py")
        expected_result = read_data("static_analysis_output.py")

        information = pythoscope.collect_information([module_path])
        result = pythoscope.generate_test_module(information, module_path)

        assert_equal(expected_result, result)

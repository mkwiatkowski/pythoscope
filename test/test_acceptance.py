import os

from fixture import TempIO
from nose.tools import assert_equal

from helper import assert_length, data, read_data

from pythoscope.collector import collect_information_from_module, collect_information_from_paths
from pythoscope.generator import add_tests_to_project
from pythoscope.store import Project
from pythoscope.util import read_file_contents

from helper import generate_single_test_module

add_tests_to_project.__test__ = False

class TestStaticAnalysis:
    def test_generates_test_stubs(self):
        module_path = data("static_analysis_module.py")
        expected_result = read_data("static_analysis_output.py")

        module = collect_information_from_module(module_path)
        result = generate_single_test_module(module)

        assert_equal(expected_result, result)

class TestAppendingTestClasses:
    def test_appends_test_classes_to_existing_test_modules(self):
        self._test_appending("appending_test_cases_module_modified.py",
                             "appending_test_cases_output_expected.py")

    def test_appends_test_methods_to_existing_test_classes(self):
        self._test_appending("appending_test_cases_module_added_method.py",
                             "appending_test_cases_added_method_output_expected.py")

    def _test_appending(self, modified_input, expected_output):
        project_path = TempIO()
        module_path = project_path.putfile("module.py", read_data("appending_test_cases_module_initial.py"))
        test_module_path = project_path.putfile("test_module.py", read_data("appending_test_cases_output_initial.py"))

        # Analyze the project with an existing test module.
        os.chdir(project_path)
        project = Project(os.path.join(project_path, ".pythoscope"),
                          modules=collect_information_from_paths(["module.py", "test_module.py"]))

        # Modify the application module and analyze it again.
        project_path.putfile("module.py", read_data(modified_input))
        project.add_modules(collect_information_from_paths(["module.py"]))

        # Regenerate the tests.
        add_tests_to_project(project, ["module.py"], project_path, 'unittest')

        assert_length(project._get_test_modules(), 1)
        result = read_file_contents(test_module_path)
        expected_result = read_data(expected_output)
        assert_equal(expected_result, result)

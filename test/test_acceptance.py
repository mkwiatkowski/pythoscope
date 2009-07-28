from pythoscope.inspector import inspect_project
from pythoscope.generator import add_tests_to_project
from pythoscope.util import read_file_contents, write_content_to_file

from assertions import *
from helper import get_test_module_contents, CapturedLogger, \
    ProjectInDirectory, putfile, TempDirectory, read_data

add_tests_to_project.__test__ = False

class TestStaticAnalysis(CapturedLogger, TempDirectory):
    def test_generates_test_stubs(self):
        expected_result = read_data("static_analysis_output.py")
        project = ProjectInDirectory(self.tmpdir)
        module_path = putfile(project.path, "module.py", read_data("static_analysis_module.py"))

        inspect_project(project)
        add_tests_to_project(project, [module_path], 'unittest')
        result = get_test_module_contents(project)

        assert_equal_strings(expected_result, result)

class TestAppendingTestClasses(CapturedLogger, TempDirectory):
    def test_appends_test_classes_to_existing_test_modules(self):
        self._test_appending("appending_test_cases_module_modified.py",
                             "appending_test_cases_output_expected.py")

    def test_appends_test_methods_to_existing_test_classes(self):
        self._test_appending("appending_test_cases_module_added_method.py",
                             "appending_test_cases_added_method_output_expected.py")

    def _test_appending(self, modified_input, expected_output):
        project = ProjectInDirectory(self.tmpdir)

        module_path = putfile(project.path, "module.py", read_data("appending_test_cases_module_initial.py"))
        test_module_path = putfile(project.path, "test_module.py", read_data("appending_test_cases_output_initial.py"))

        # Analyze the project with an existing test module.
        inspect_project(project)

        # Filesystem stat has resolution of 1 second, and we don't want to
        # sleep in a test, so we just fake the original files creation time.
        project["module"].created = 0
        project["test_module"].created = 0

        # Modify the application module and analyze it again.
        putfile(project.path, "module.py", read_data(modified_input))
        inspect_project(project)

        # Regenerate the tests.
        add_tests_to_project(project, [module_path], 'unittest')
        project.save()

        assert_length(project.get_modules(), 2)
        result = read_file_contents(test_module_path)
        expected_result = read_data(expected_output)
        assert_equal_strings(expected_result, result)

class TestObjectsIdentityPreservation(CapturedLogger, TempDirectory):
    def test_preserves_identity_of_objects(self):
        expected_result = read_data("objects_identity_output.py")
        project = ProjectInDirectory(self.tmpdir).with_points_of_entry(["poe.py"])
        module_path = putfile(project.path, "module.py", read_data("objects_identity_module.py"))
        write_content_to_file(read_data("objects_identity_poe.py"),
                              project.path_for_point_of_entry("poe.py"))

        inspect_project(project)
        add_tests_to_project(project, [module_path], 'unittest')
        result = get_test_module_contents(project)

        assert_equal_strings(expected_result, result)

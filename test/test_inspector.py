from pythoscope.inspector import inspect_project

from helper import assert_contains_once, assert_equal_strings, CapturedLogger, \
    P, ProjectInDirectory, ProjectWithPointsOfEntryFiles, ProjectWithRealModules


class TestInspector(CapturedLogger):
    def test_skips_dynamic_inspection_when_no_changes_were_made_to_the_project(self):
        project = ProjectInDirectory()
        inspect_project(project)
        assert_equal_strings("INFO: No changes discovered in the source code, skipping dynamic inspection.\n",
                             self._get_log_output())

    def test_skips_inspection_of_up_to_date_modules(self):
        paths = ["module.py", "something_else.py", P("module/in/directory.py")]
        project = ProjectWithRealModules(paths)

        inspect_project(project)

        for path in paths:
            assert_contains_once(self._get_log_output(),
                                 "INFO: %s hasn't changed since last inspection, skipping." % path)

    def test_reports_each_inspected_module(self):
        paths = ["module.py", "something_else.py", P("module/in/directory.py")]
        project = ProjectWithRealModules(paths)
        # Force the inspection by faking files creation time.
        project["module"].created = 0
        project["something_else"].created = 0
        project["module.in.directory"].created = 0

        inspect_project(project)

        for path in paths:
            assert_contains_once(self._get_log_output(),
                                 "INFO: Inspecting module %s." % path)

    def test_reports_each_inspected_point_of_entry(self):
        paths = ["one.py", "two.py"]
        project = ProjectWithPointsOfEntryFiles(paths)

        inspect_project(project)

        for path in paths:
            assert_contains_once(self._get_log_output(),
                                 "INFO: Inspecting point of entry %s." % path)

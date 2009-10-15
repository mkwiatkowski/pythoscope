from nose import SkipTest

from pythoscope.inspector import inspect_project
from pythoscope.util import generator_has_ended

from assertions import *
from helper import CapturedLogger, P, ProjectInDirectory, TempDirectory


class TestInspector(CapturedLogger, TempDirectory):
    def test_skips_dynamic_inspection_when_no_changes_were_made_to_the_project(self):
        project = ProjectInDirectory(self.tmpdir)
        inspect_project(project)
        assert_equal_strings("INFO: No changes discovered in the source code, skipping dynamic inspection.\n",
                             self._get_log_output())

    def test_skips_inspection_of_up_to_date_modules(self):
        paths = ["module.py", "something_else.py", P("module/in/directory.py")]
        project = ProjectInDirectory(self.tmpdir).with_modules(paths)

        inspect_project(project)

        for path in paths:
            assert_contains_once(self._get_log_output(),
                                 "INFO: %s hasn't changed since last inspection, skipping." % path)

    def test_reports_each_inspected_module(self):
        paths = ["module.py", "something_else.py", P("module/in/directory.py")]
        project = ProjectInDirectory(self.tmpdir).with_modules(paths)
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
        project = ProjectInDirectory(self.tmpdir).with_points_of_entry(paths)

        inspect_project(project)

        for path in paths:
            assert_contains_once(self._get_log_output(),
                                 "INFO: Inspecting point of entry %s." % path)

    def test_warns_about_unreliable_implementation_of_util_generator_has_ended(self):
        if not hasattr(generator_has_ended, 'unreliable'):
            raise SkipTest

        paths = ["edgar.py", "allan.py"]
        project = ProjectInDirectory(self.tmpdir).with_points_of_entry(paths)

        inspect_project(project)

        assert_contains_once(self._get_log_output(),
                             "WARNING: Pure Python implementation of "
                             "util.generator_has_ended is not reliable on "
                             "Python 2.4 and lower. Please compile the _util "
                             "module or use Python 2.5 or higher.")

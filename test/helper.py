import os
import re

from fixture import TempIO
from nose.tools import assert_equal

from pythoscope.generator import add_tests_to_project
from pythoscope.store import Module, Project, Function, ModuleNotFound, \
     PointOfEntry
from pythoscope.util import read_file_contents, set


DATA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))

def data(name):
    "Return a location of a test data with a given name."
    return os.path.join(DATA_PATH, name)

def read_data(name):
    return read_file_contents(data(name))

def quoted_block(text):
    return ''.join(["> %s" % line for line in text.splitlines(True)])

def assert_length(collection, expected_length):
    actual_length = len(collection)
    assert expected_length == actual_length,\
           "Expected collection to have %d elements, it had %d instead." %\
           (expected_length, actual_length)

def assert_contains(haystack, needle):
    assert needle in haystack,\
           "Expected\n%s\nto contain %r, but it didn't." % (quoted_block(haystack), needle)

def assert_contains_once(haystack, needle):
    repeated = len(re.findall(re.escape(needle), haystack))
    assert repeated == 1, "Expected\n%s\nto contain %r once, but it contained it %d times instead." %\
           (quoted_block(haystack), needle, repeated)

def assert_doesnt_contain(haystack, needle):
    assert needle not in haystack,\
           "Expected\n%s\nto NOT contain %r, but it did." % (quoted_block(haystack), needle)

def assert_single_class(info, name):
    assert_length(info.classes, 1)
    assert_equal(name, info.classes[0].name)

def assert_single_function(info, name):
    assert_length(info.functions, 1)
    assert_equal(name, info.functions[0].name)

def assert_equal_sets(collection1, collection2):
    assert_equal(set(collection1), set(collection2))

def assert_not_raises(exception, callable):
    try:
        callable()
    except exception:
        assert False, "Exception %s has been raised." % exception

class PointOfEntryMock(PointOfEntry):
    def __init__(self, project=None, name="poe", content=""):
        if project is None:
            project = Project('.')
        PointOfEntry.__init__(self, project, name)
        self.content = content

    def clear_previous_run(self):
        pass

    def get_content(self):
        return self.content

# Make your test case a subclass of CustomSeparator to test your code with
# alternative os.path.sep.
class CustomSeparator:
    def setUp(self):
        self.old_sep = os.path.sep
        os.path.sep = '#'

    def tearDown(self):
        os.path.sep = self.old_sep

def EmptyProject():
    project = Project(path=os.path.realpath("."))
    # Preserve the default value.
    project.new_tests_directory = "tests"
    return project

def ProjectInDirectory():
    project_path = TempIO()
    project_path.mkdir(".pythoscope")
    project = Project(project_path)
    # Save the TempIO reference, so we can delay its destruction later.
    project._tmpdir = project_path
    return project

def ProjectWithModules(paths, project_type=EmptyProject):
    project = project_type()
    for path in paths:
        project.create_module(os.path.join(project.path, path))
    return project

def ProjectWithRealModules(paths):
    project = ProjectWithModules(paths, ProjectInDirectory)
    for path in paths:
        project.path.putfile(path, "")
    return project

def TestableProject(more_modules=[], project_type=ProjectInDirectory):
    project = ProjectWithModules(["module.py"] + more_modules, project_type)
    project["module"].objects = [Function("function")]
    return project

def get_test_module_contents(project):
    """Get contents of the first test module of a project.
    """
    try:
        return project["tests/test_module.py"].get_content()
    except ModuleNotFound:
        return "" # No test module was generated.
get_test_module_contents.__test__ = False

def generate_single_test_module(template='unittest', **module_kwds):
    """Return test module contents generated for given module.
    """
    project = EmptyProject()
    project.create_module("module.py", **module_kwds)
    add_tests_to_project(project, ["module.py"], template, False)
    return get_test_module_contents(project)
generate_single_test_module.__test__ = False

def get_test_cases(project):
    return list(project.iter_test_cases())
get_test_cases.__test__ = False

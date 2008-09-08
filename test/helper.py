import os

from fixture import TempIO
from nose.tools import assert_equal

from pythoscope.generator import add_tests_to_project
from pythoscope.store import Module, Project, Function, ModuleNotFound
from pythoscope.util import read_file_contents, set


DATA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))

def data(name):
    "Return a location of a test data with a given name."
    return os.path.join(DATA_PATH, name)

def read_data(name):
    return read_file_contents(data(name))

def assert_length(collection, expected_length):
    actual_length = len(collection)
    assert expected_length == actual_length,\
           "Expected collection to have %d elements, it had %d instead." %\
           (expected_length, actual_length)

def assert_contains(haystack, needle):
    assert needle in haystack,\
           "%r should contain %r, but it didn't." % (haystack, needle)

def assert_doesnt_contain(haystack, needle):
    assert needle not in haystack,\
           "%r should NOT contain %r, but it did." % (haystack, needle)

def assert_single_class(info, name):
    assert_length(info.classes, 1)
    assert_equal(name, info.classes[0].name)

def assert_single_function(info, name):
    assert_length(info.functions, 1)
    assert_equal(name, info.functions[0].name)

def assert_equal_sets(collection1, collection2):
    assert_equal(set(collection1), set(collection2))

# Make your test case a subclass of CustomSeparator to test your code with
# alternative os.path.sep.
class CustomSeparator:
    def setUp(self):
        self.old_sep = os.path.sep
        os.path.sep = '#'

    def tearDown(self):
        os.path.sep = self.old_sep

def EmptyProject():
    return Project(path=os.path.realpath("."))

def ProjectInDirectory():
    project_path = TempIO()
    project_path.mkdir(".pythoscope")
    return Project(project_path)

def ProjectWithModules(paths, project_type=EmptyProject):
    project = project_type()
    for path in paths:
        project.create_module(os.path.join(project.path, path))
    return project

def TestableProject(more_modules=[], project_type=ProjectInDirectory):
    project = ProjectWithModules(["module.py"] + more_modules, project_type)
    project["module"].objects = [Function("function")]
    return project

def get_test_module_contents(project):
    """Get contents of the first test module of a project.
    """
    try:
        return project["pythoscope-tests/test_module.py"].get_content()
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

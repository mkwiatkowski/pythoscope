import os

from fixture import TempIO
from nose.tools import assert_equal

from pythoscope.generator import add_tests_to_project
from pythoscope.store import TestModule, Project
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

class CustomSeparator:
    def setUp(self):
        self.old_sep = os.path.sep
        os.path.sep = '#'

    def tearDown(self):
        os.path.sep = self.old_sep

def generate_single_test_module(module, template='unittest'):
    """Return test module contents generated for given module.
    """
    project = Project(modules=[module])
    add_tests_to_project(project, [module.path], TempIO(), template, False)
    try:
        return project._get_test_modules()[0].get_content()
    except IndexError:
        return "" # No test module was generated.
generate_single_test_module.__test__ = False

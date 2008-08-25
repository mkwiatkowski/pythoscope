import os

from nose.tools import assert_equal

from pythoscope.generator import template2generator
from pythoscope.store import TestModule
from pythoscope.util import read_file_contents


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

class CustomSeparator:
    def setUp(self):
        self.old_sep = os.path.sep
        os.path.sep = '#'

    def tearDown(self):
        os.path.sep = self.old_sep

class TestModuleInMemory(TestModule):
    def _read_from_file(self):
        pass
    def save(self):
        pass

def generate_single_test_module(module, template='unittest'):
    generator = template2generator[template]
    test_module = TestModuleInMemory('whatever', module)
    generator.update_test_module(test_module)
    return test_module.get_content()
generate_single_test_module.__test__ = False

"""Module containing code that has to be executed before any of the tests.
"""

# Make pythoscope importable directly from the test modules.
import os, sys
pythoscope_path = os.path.join(os.path.dirname(__file__), os.pardir)
sys.path.insert(0, os.path.abspath(pythoscope_path))

# Make sys.stdout the logger's output stream, so nose capture
# plugin can get hold of it.
# We can't set_output to sys.stdout directly, because capture
# plugin changes that before each test.
class AlwaysCurrentStdout:
    def __getattr__(self, name):
        return getattr(sys.stdout, name)
from pythoscope.logger import DEBUG, log, set_output
set_output(AlwaysCurrentStdout())
log.level = DEBUG

# Make sure all those suspiciously looking classes and functions aren't treated
# as tests by nose.
from pythoscope.store import TestClass, TestMethod
from pythoscope.generator import add_tests_to_project, TestMethodDescription, \
    TestGenerator
from pythoscope.generator.adder import add_test_case, add_test_case_to_project, \
    find_test_module, module_path_to_test_path, replace_test_case

TestClass.__test__ = False
TestMethod.__test__ = False

add_tests_to_project.__test__ = False
TestMethodDescription.__test__ = False
TestGenerator.__test__ = False

add_test_case.__test__ = False
add_test_case_to_project.__test__ = False
find_test_module.__test__ = False
module_path_to_test_path.__test__ = False
replace_test_case.__test__ = False

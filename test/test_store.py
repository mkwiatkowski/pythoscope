from nose.tools import assert_equal

from pythoscope.astvisitor import parse
from pythoscope.store import Module, TestClass, module_path_to_test_path

from helper import CustomSeparator

class TestModule:
    def test_can_add_test_cases_to_empty_modules(self):
        module = Module(subpath="module.py", code=parse("# only comments"), project=None)
        test_class = TestClass(name="TestSomething", code=parse("# some test code"))
        module.add_test_case(test_class)
        # Make sure it doesn't raise any exceptions.

class TestStoreWithCustomSeparator(CustomSeparator):
    def test_uses_system_specific_path_separator(self):
        module = Module(subpath="some#path.py", project=None)
        assert_equal("some.path", module.locator)

    def test_module_path_to_test_path_uses_system_specific_path_separator(self):
        assert_equal("test_pythoscope_store.py",
                     module_path_to_test_path("pythoscope#store.py"))
        assert_equal("test_pythoscope.py",
                     module_path_to_test_path("pythoscope#__init__.py"))

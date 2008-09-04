from nose.tools import assert_equal

from pythoscope.store import Module, module_path_to_test_path

from helper import CustomSeparator

class TestStoreWithCustomSeparator(CustomSeparator):
    def test_uses_system_specific_path_separator(self):
        module = Module("some#path.py")
        assert_equal("some.path", module.locator)

    def test_module_path_to_test_path_uses_system_specific_path_separator(self):
        assert_equal("test_pythoscope_store.py",
                     module_path_to_test_path("pythoscope#store.py"))
        assert_equal("test_pythoscope.py",
                     module_path_to_test_path("pythoscope#__init__.py"))

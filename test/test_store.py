from nose.tools import assert_equal

from pythoscope.astvisitor import parse
from pythoscope.store import Class, LiveObject, Module, PointOfEntry, \
     TestClass, Project

from helper import CustomSeparator, assert_length

# Let nose know that those aren't test cases.
TestClass.__test__ = False

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

# Avoid a name clash with pythoscope.store.TestClass.
class TestForClass:
    def test_remove_live_objects_from(self):
        project = Project('.')
        klass = Class('SomeClass')
        first = PointOfEntry(project, 'first')
        second = PointOfEntry(project, 'second')
        live_objects = [LiveObject(1, klass, first), LiveObject(2, klass, first), LiveObject(1, klass, second)]

        for lo in live_objects:
            klass.add_live_object(lo)

        klass.remove_live_objects_from(first)

        assert_length(klass.live_objects.values(), 1)
        assert_equal(('second', 1), klass.live_objects.values()[0].unique_id)

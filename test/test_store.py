from nose.tools import assert_equal

from pythoscope.astvisitor import parse
from pythoscope.store import Class, Function, FunctionCall, Module, \
    PointOfEntry, Project, TestClass, UserObject

from helper import CustomSeparator, assert_equal_sets, assert_length

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

def inject_user_object(poe, obj, klass):
    def create_user_object():
        return UserObject(obj, klass)
    user_object = poe.execution._retrieve_or_capture(obj, create_user_object)
    klass.add_user_object(user_object)
    return user_object

def inject_function_call(poe, function):
    call = FunctionCall(function, {})
    poe.execution.captured_calls.append(call)
    function.add_call(call)
    return call

class TestPointOfEntry:
    def _create_project_with_two_points_of_entry(self, obj):
        project = Project('.')
        project.create_module("module.py", objects=[obj])
        self.first = PointOfEntry(project, 'first')
        self.second = PointOfEntry(project, 'second')

    def test_clear_previous_run_removes_user_objects_from_classes(self):
        klass = Class('SomeClass')
        self._create_project_with_two_points_of_entry(klass)

        obj1 = inject_user_object(self.first, 1, klass)
        obj2 = inject_user_object(self.first, 2, klass)
        obj3 = inject_user_object(self.second, 1, klass)

        self.first.clear_previous_run()

        # Only the UserObject from the second POE remains.
        assert_length(klass.user_objects, 1)
        assert_equal_sets([obj3], klass.user_objects)

    def test_clear_previous_run_removes_function_calls_from_functions(self):
        function = Function('some_function')
        self._create_project_with_two_points_of_entry(function)

        call1 = inject_function_call(self.first, function)
        call2 = inject_function_call(self.first, function)
        call3 = inject_function_call(self.second, function)

        self.first.clear_previous_run()

        # Only the FunctionCall from the second POE remains.
        assert_length(function.calls, 1)
        assert_equal_sets([call3], function.calls)

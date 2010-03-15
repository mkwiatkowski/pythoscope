from pythoscope.astbuilder import EmptyCode
from pythoscope.point_of_entry import PointOfEntry
from pythoscope.serializer import ImmutableObject, UnknownObject,\
    SequenceObject, MapObject
from pythoscope.store import Class, Function, FunctionCall, GeneratorObject,\
    Method, UserObject

from assertions import *
from helper import EmptyProject


def inject_user_object(poe, obj, klass):
    def create_user_object(_):
        return UserObject(obj, klass)
    user_object = poe.execution._retrieve_or_capture(obj, create_user_object)
    klass.add_user_object(user_object)
    return user_object

def inject_function_call(poe, function, args={}):
    call = FunctionCall(function, args)
    poe.execution.captured_calls.append(call)
    for arg in args.values():
        poe.execution.captured_objects[id(arg)] = arg
    function.add_call(call)
    return call

def inject_generator_object(poe, obj, *args):
    return poe.execution._retrieve_or_capture(obj,
        lambda _:GeneratorObject(obj, *args))

class TestPointOfEntry:
    def _create_project_with_two_points_of_entry(self, *objs):
        project = EmptyProject()
        project.create_module("module.py", code=EmptyCode(), objects=list(objs))
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
        assert_equal_sets([obj3], klass.user_objects)

    def test_clear_previous_run_removes_function_calls_from_functions(self):
        function = Function('some_function')
        self._create_project_with_two_points_of_entry(function)

        call1 = inject_function_call(self.first, function)
        call2 = inject_function_call(self.first, function)
        call3 = inject_function_call(self.second, function)

        self.first.clear_previous_run()

        # Only the FunctionCall from the second POE remains.
        assert_equal_sets([call3], function.calls)

    def test_clear_previous_run_removes_generator_objects_from_functions(self):
        function = Function('generator', is_generator=True)
        method = Method('generator_method', is_generator=True)
        klass = Class('ClassWithGenerators', methods=[method])
        self._create_project_with_two_points_of_entry(function, klass)

        user_object = inject_user_object(self.first, 1, klass)
        inject_generator_object(self.first, 2, function, {}, function)
        inject_generator_object(self.first, 3, method, {}, user_object)

        self.first.clear_previous_run()

        assert_equal([], klass.user_objects)
        assert_equal([], function.calls)

    def test_clear_previous_run_ignores_not_referenced_objects(self):
        function = Function('some_function')
        self._create_project_with_two_points_of_entry(function)

        args = {'i': ImmutableObject(123), 'u': UnknownObject(None),
                's': SequenceObject([], None), 'm': MapObject({}, None)}
        inject_function_call(self.first, function, args)

        self.first.clear_previous_run()
        # Make sure it doesn't raise any exceptions.

import array
import os
import re
import sys
import time
import types

from nose import SkipTest

from pythoscope.generator import add_tests_to_project, constructor_as_string
from pythoscope.inspector.static import inspect_code
from pythoscope.serializer import ImmutableObject
from pythoscope.store import Class, Function, Method, ModuleNeedsAnalysis, \
    ModuleSaveError, TestClass, TestMethod, MethodCall, FunctionCall, \
    UserObject, GeneratorObject
from pythoscope.compat import sets, sorted
from pythoscope.util import read_file_contents, get_last_modification_time

from assertions import *
from helper import CapturedDebugLogger, CapturedLogger, P, \
    ProjectInDirectory, EmptyProject, TestableProject, \
    generate_single_test_module, get_test_cases, \
    EmptyProjectExecution, putfile, TempDirectory, make_fresh_serialize

# Let nose know that those aren't test functions/classes.
add_tests_to_project.__test__ = False
TestClass.__test__ = False
TestMethod.__test__ = False

def stable_serialize_call_arguments(execution, args):
    """Work just like execution.serialize_call_arguments, but serialize
    arguments in lexicographical order, so test outputs are stable.

    This doesn't change semantics of the serialization process (as objects
    identity will be preserved), yet it makes testing it much easier.
    """
    serialized_args = {}
    for key, value in sorted(args.iteritems()):
        serialized_args[key] = execution.serialize(value)
    return serialized_args

def create_method_call(method, args, output, call_type, execution):
    sargs = stable_serialize_call_arguments(execution, args)
    if call_type == 'output':
        return MethodCall(method, sargs, output=execution.serialize(output))
    elif call_type == 'exception':
        return MethodCall(method, sargs, exception=execution.serialize(output))
    elif call_type == 'generator':
        return GeneratorObject(method, sargs, map(execution.serialize, output))

def ClassWithMethods(classname, methods, call_type='output'):
    """call_type has to be one of 'output', 'exception' or 'generator'.
    """
    execution = EmptyProjectExecution()
    method_objects = []
    method_calls = []

    for name, calls in methods:
        method = Method(name)
        method_objects.append(method)
        for args, output in calls:
            method_calls.append(create_method_call(method, args, output, call_type, execution))

    klass = Class(classname, methods=method_objects)
    user_object = UserObject(None, klass)
    user_object.calls = method_calls
    klass.add_user_object(user_object)

    return klass

def ClassWithInstanceWithoutReconstruction(name):
    # Cheating a bit, as this class won't be the same as one defined in
    # module.py.
    return Class(name), types.ClassType(name, (object,), {})()

def FunctionWithCalls(funcname, calls):
    execution = EmptyProjectExecution()
    function = Function(funcname)
    function.calls = [FunctionCall(function,
                                   stable_serialize_call_arguments(execution, i),
                                   execution.serialize(o)) for (i,o) in calls]
    return function

def FunctionWithSingleCall(funcname, input, output):
    return FunctionWithCalls(funcname, [(input, output)])

def FunctionWithExceptions(funcname, calls):
    execution = EmptyProjectExecution()
    function = Function(funcname)
    function.calls = [FunctionCall(function,
                                   stable_serialize_call_arguments(execution, i),
                                   exception=execution.serialize(e)) for (i,e) in calls]
    return function

def FunctionWithSingleException(funcname, input, exception):
    return FunctionWithExceptions(funcname, [(input, exception)])

def GeneratorWithYields(genname, input, yields):
    execution = EmptyProjectExecution()
    generator = Function(genname, is_generator=True)
    gobject = GeneratorObject(generator,
                              stable_serialize_call_arguments(execution, input),
                              map(execution.serialize, yields))
    generator.calls = [gobject]
    return generator

def GeneratorWithSingleException(genname, input, exception):
    execution = EmptyProjectExecution()
    generator = Function(genname, is_generator=True)
    gobject = GeneratorObject(generator,
                              stable_serialize_call_arguments(execution, input),
                              exception=execution.serialize(exception))
    generator.calls = [gobject]
    return generator

class TestGenerator:
    def test_generates_unittest_boilerplate(self):
        result = generate_single_test_module(objects=[Function('function')])
        assert_contains(result, "import unittest")
        assert_contains(result, "if __name__ == '__main__':\n    unittest.main()")

    def test_generates_test_class_for_each_production_class(self):
        objects = [Class('SomeClass', [Method('some_method')]),
                   Class('AnotherClass', [Method('another_method')])]
        result = generate_single_test_module(objects=objects)
        assert_contains(result, "class TestSomeClass(unittest.TestCase):")
        assert_contains(result, "class TestAnotherClass(unittest.TestCase):")

    def test_generates_test_class_for_each_stand_alone_function(self):
        objects=[Function('some_function'), Function('another_function')]
        result = generate_single_test_module(objects=objects)
        assert_contains(result, "class TestSomeFunction(unittest.TestCase):")
        assert_contains(result, "class TestAnotherFunction(unittest.TestCase):")

    def test_generates_test_method_for_each_production_method_and_function(self):
        objects = [Class('SomeClass', [Method('some_method')]),
                   Class('AnotherClass', map(Method, ['another_method', 'one_more'])),
                   Function('a_function')]
        result = generate_single_test_module(objects=objects)
        assert_contains(result, "def test_some_method(self):")
        assert_contains(result, "def test_another_method(self):")
        assert_contains(result, "def test_one_more(self):")
        assert_contains(result, "def test_a_function(self):")

    def test_generates_conventional_name_for_init_method(self):
        objects = [Class('SomeClass', [Method('__init__')])]
        result = generate_single_test_module(objects=objects)
        assert_contains(result, "def test___init__(self):")

    def test_ignores_empty_classes(self):
        result = generate_single_test_module(objects=[Class('SomeClass', [])])
        assert_doesnt_contain(result, "class TestSomeClass(unittest.TestCase):")

    def test_can_generate_nose_style_tests(self):
        objects = [Class('AClass', [Method('a_method')]), Function('a_function')]
        result = generate_single_test_module(template='nose', objects=objects)

        assert_doesnt_contain(result, "import unittest")
        assert_contains(result, "from nose import SkipTest")

        assert_contains(result, "class TestAClass:")
        assert_contains(result, "class TestAFunction:")

        assert_contains(result, "raise SkipTest")
        assert_doesnt_contain(result, "assert False")

        assert_doesnt_contain(result, "if __name__ == '__main__':\n    unittest.main()")

    def test_doesnt_generate_skiptest_import_for_nose_tests_that_dont_use_it(self):
        objects = [FunctionWithSingleCall('a_function', {'x': 1}, 2)]
        result = generate_single_test_module(template='nose', objects=objects)

        assert_doesnt_contain(result, "from nose import SkipTest")

    def test_ignores_private_methods(self):
        objects = [Class('SomeClass', map(Method, ['_semiprivate', '__private']))]
        result = generate_single_test_module(objects=objects)
        assert_doesnt_contain(result, "class TestSomeClass(unittest.TestCase):")

    def test_doesnt_ignore_special_methods(self):
        objects = [Class('SomeClass', map(Method, ['__eq__', '__init__']))]
        result = generate_single_test_module(objects=objects)
        assert_contains(result, "class TestSomeClass(unittest.TestCase):")
        assert_contains(result, "def test___eq__(self):")
        assert_contains(result, "def test___init__(self):")

    def test_ignores_private_functions(self):
        result = generate_single_test_module(objects=[Function('_function')])
        assert_doesnt_contain(result, "class")

    def test_ignores_exception_classes(self):
        objects = [Class('ExceptionClass', [Method('method')], bases=['Exception'])]
        result = generate_single_test_module(objects=objects)
        assert_doesnt_contain(result, "class TestExceptionClass(unittest.TestCase):")

    def test_ignores_unittest_classes(self):
        objects = [TestClass('TestClass', [TestMethod('test_method')])]
        result = generate_single_test_module(objects=objects)
        assert_doesnt_contain(result, "class TestTestClass(unittest.TestCase):")

    def test_generates_content_in_right_order(self):
        result = generate_single_test_module(objects=[Function('function')])

        assert_matches(r"import unittest.*?class TestFunction.*?if __name__ == '__main__'", result)

    def test_ignores_test_modules(self):
        result = generate_single_test_module()
        assert_equal("", result)

    def test_generates_test_case_for_each_function_call_with_numbers(self):
        objects = [FunctionWithSingleCall('square', {'x': 4}, 16)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_square_returns_16_for_4(self):")
        assert_contains(result, "self.assertEqual(16, square(x=4))")

    def test_generates_test_case_for_each_function_call_with_strings(self):
        objects = [FunctionWithSingleCall('underscore', {'name': 'John Smith'}, 'john_smith')]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_underscore_returns_john_smith_for_John_Smith(self):")
        assert_contains(result, "self.assertEqual('john_smith', underscore(name='John Smith'))")

    def test_generates_test_case_for_each_method_call(self):
        klass = ClassWithMethods('Something', [('method', [({'arg': 111}, 'one one one')])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_method_returns_one_one_one_for_111(self):")
        assert_contains(result, "something = Something()")
        assert_contains(result, "self.assertEqual('one one one', something.method(arg=111))")

    def test_generates_imports_needed_for_function_calls(self):
        objects = [FunctionWithSingleCall('square', {}, 42)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "from module import square")

    def test_generates_imports_needed_for_method_calls(self):
        klass = ClassWithMethods('Something', [('method', [({}, 42)])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "from module import Something")

    def test_generates_imports_needed_for_arguments_of_init_methods(self):
        klass = ClassWithMethods('Something', [('__init__', [({'fun': read_file_contents}, None)])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "from pythoscope.util import read_file_contents")

    def test_ignores_repeated_calls(self):
        objects = [FunctionWithCalls('square', 2*[({'x': 4}, 16)])]

        result = generate_single_test_module(objects=objects)

        assert_contains_once(result, 'def test_square_returns_16_for_4(self):')

    def test_sorts_new_test_methods_by_name(self):
        objects = [FunctionWithCalls('square', [({'x': 2}, 4), ({'x': 3}, 9)])]

        result = generate_single_test_module(objects=objects)

        assert re.search('test_square_returns_4_for_2.*test_square_returns_9_for_3', result, re.DOTALL)

    def test_generates_proper_setup_for_test_objects_with_init(self):
        klass = ClassWithMethods('Something', [('__init__', [({'arg1': 1, 'arg2': 2}, None)]),
                                               ('sum', [({}, 3)])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_sum_returns_3_after_creation_with_arg1_equal_1_and_arg2_equal_2(self):")
        assert_contains(result, "something = Something(arg1=1, arg2=2)")
        assert_contains(result, "self.assertEqual(3, something.sum())")

    def test_generates_nice_name_for_tests_with_init_that_takes_no_arguments(self):
        klass = ClassWithMethods('Something', [('__init__', [({}, None)]),
                                               ('fire', [({}, 'kaboom')])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_fire_returns_kaboom(self):")

    def test_generates_nice_name_for_tests_with_init_only_that_takes_no_arguments(self):
        klass = ClassWithMethods('Something', [('__init__', [({}, None)])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_creation(self):")

    def test_ignores_internal_object_calls(self):
        klass = ClassWithMethods('Something', [('method', [({'argument': 1}, 'result')])])
        user_object = klass.user_objects[0]
        method_call = user_object.calls[0]

        subcall = MethodCall(Method('private'), {'argument': ImmutableObject(2)}, ImmutableObject(False))
        method_call.add_subcall(subcall)
        user_object.add_call(subcall)

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_method_returns_result_for_1(self):")
        assert_contains(result, "self.assertEqual('result', something.method(argument=1))")
        assert_doesnt_contain(result, "def test_private_returns_false_for_2(self):")
        assert_doesnt_contain(result, "self.assertEqual(False, something.private(argument=2))")

    def test_generates_nice_names_for_test_cases_that_test_init_only(self):
        klass = ClassWithMethods('Something', [('__init__', [({'param': 1}, None)])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_creation_with_1(self):")
        assert_contains(result, "# Make sure it doesn't raise any exceptions.")
        assert_doesnt_contain(result, "assert False")

    def test_generates_object_creation_stub_for_init_with_uncomplete_arguments(self):
        klass = ClassWithMethods('Something', [('__init__', [({'param': lambda: 42}, None)])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_creation_with_function(self):")
        assert_contains(result, "# something = Something(param=<TODO: function>)")
        assert_contains(result, "# Make sure it doesn't raise any exceptions.")

    def test_comments_all_assertions_if_the_object_creation_is_uncomplete(self):
        klass = ClassWithMethods('Something', [('__init__', [({'param': lambda: 42}, None)]),
                                               ('method', [({}, 1)])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_method_returns_1_after_creation_with_function(self):")
        assert_contains(result, "# something = Something(param=<TODO: function>)")
        assert_contains(result, "# self.assertEqual(1, something.method()")

    def test_generates_assert_equal_type_for_functions_returning_functions(self):
        objects = [FunctionWithSingleCall('higher', {}, lambda: 42)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "import types")
        assert_contains(result, "def test_higher_returns_function(self):")
        assert_contains(result, "self.assertEqual(types.FunctionType, type(higher()))")

    def test_generates_assert_equal_test_stub_for_functions_which_take_functions_as_arguments(self):
        objects = [FunctionWithSingleCall('higher', {'f': lambda: 42}, True)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_higher_returns_true_for_function(self):")
        assert_contains(result, "# self.assertEqual(True, higher(f=<TODO: function>))")

    def test_generates_assert_equal_type_for_functions_returning_generator_objects(self):
        def generator():
            yield 1
        objects = [FunctionWithSingleCall('gengen', {}, generator())]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "import types")
        assert_contains(result, "def test_gengen_returns_generator(self):")
        assert_contains(result, "self.assertEqual(types.GeneratorType, type(gengen()))")

    def test_generates_assert_equal_test_stub_for_functions_which_take_generator_objects_as_arguments(self):
        def generator():
            yield 1
        objects = [FunctionWithSingleCall('ungen', {'g': generator()}, True)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_ungen_returns_true_for_generator(self):")
        assert_contains(result, "# self.assertEqual(True, ungen(g=<TODO: generator>))")

    def test_generates_assert_equal_type_test_stub_for_functions_which_take_and_return_functions(self):
        objects = [FunctionWithSingleCall('highest', {'f': lambda: 42}, lambda: 43)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_highest_returns_function_for_function(self):")
        assert_contains(result, "# self.assertEqual(types.FunctionType, type(highest(f=<TODO: function>)))")

    def test_handles_regular_expression_pattern_objects(self):
        objects = [FunctionWithSingleCall('matches', {'x': re.compile('abcd')}, True)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "import re")
        assert_contains(result, "def test_matches_returns_true_for_abcd_pattern(self):")
        assert_contains(result, "self.assertEqual(True, matches(x=re.compile('abcd')))")

    def test_lists_names_of_tested_methods_in_longer_test_cases(self):
        klass = ClassWithMethods('Something', [('__init__', [({'arg1': 1, 'arg2': 2}, None)]),
                                               ('sum', [({}, 3)]),
                                               ('power', [({}, 1)])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_power_and_sum_after_creation_with_arg1_equal_1_and_arg2_equal_2(self):")

    def test_lists_names_of_tested_methods_called_multiple_times_in_longer_test_cases(self):
        klass = ClassWithMethods('Developer', [('look_at', [({'what': 'bad code'}, 'sad'),
                                                            ({'what': 'good code'}, 'happy')]),
                                               ('modify', [({}, True)])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_look_at_2_times_and_modify(self):")

    def test_generates_assert_equal_for_generator_functions(self):
        objects = [GeneratorWithYields('random', {'seed': 1}, [1, 8, 7, 2])]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_random_yields_1_then_8_then_7_then_2_for_1(self):")
        assert_contains(result, "self.assertEqual([1, 8, 7, 2], list(islice(random(seed=1), 4)))")

    def test_generates_assert_equal_for_generator_methods(self):
        klass = ClassWithMethods('SuperGenerator', [('degenerate', [({'what': 'strings'}, ['one', 'two'])])], call_type='generator')

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_degenerate_yields_one_then_two_for_strings(self):")
        assert_contains(result, "super_generator = SuperGenerator()")
        assert_contains(result, "self.assertEqual(['one', 'two'], list(islice(super_generator.degenerate(what='strings'), 2)))")

    def test_generates_assert_equal_stub_for_generator_functions_with_unpickable_inputs(self):
        objects = [GeneratorWithYields('call_twice', {'x': lambda: 1}, [1, 1])]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_call_twice_yields_1_then_1_for_function(self):")
        assert_contains(result, "# self.assertEqual([1, 1], list(islice(call_twice(x=<TODO: function>), 2)))")

    def test_generates_assert_equal_types_for_generator_functions_with_unpickable_outputs(self):
        objects = [GeneratorWithYields('lambdify', {'x': 1}, [lambda: 1, lambda: 2])]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_lambdify_yields_function_then_function_for_1(self):")
        assert_contains(result, "self.assertEqual([types.FunctionType, types.FunctionType], map(type, list(islice(lambdify(x=1), 2))))")

    def test_takes_slice_of_generated_values_list_to_work_around_infinite_generators(self):
        objects = [GeneratorWithYields('nats', {'start': 1}, [1, 2, 3])]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "from itertools import islice")
        assert_contains(result, "def test_nats_yields_1_then_2_then_3_for_1(self):")
        assert_contains(result, "self.assertEqual([1, 2, 3], list(islice(nats(start=1), 3)))")

    def test_doesnt_test_unused_generators(self):
        objects = [GeneratorWithYields('useless', {'anything': 123}, [])]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "assert False")
        assert_doesnt_contain(result, "  self.assertEqual")
        assert_doesnt_contain(result, "  self.assertRaises")

    def test_handles_unicode_objects(self):
        objects = [FunctionWithSingleCall('characterize', {'x': u'\xf3'}, "o-acute")]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_characterize_returns_oacute_for_unicode_string(self):")
        assert_contains(result, "self.assertEqual('o-acute', characterize(x=u'\\xf3'))")

    def test_handles_localizable_function_objects(self):
        objects = [FunctionWithSingleCall('store', {'fun': read_file_contents}, None)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "from pythoscope.util import read_file_contents")
        assert_contains(result, "def test_store_returns_None_for_read_file_contents_function(self):")
        assert_contains(result, "self.assertEqual(None, store(fun=read_file_contents))")

    def test_handles_the_same_object_used_twice(self):
        obj = []
        objects = [FunctionWithSingleCall('compare', {'x': obj, 'y': obj}, True)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_compare_returns_true_for_x_equal_list_and_y_equal_list(self):")
        assert_contains(result, "alist = []")
        assert_contains(result, "self.assertEqual(True, compare(x=alist, y=alist))")

    def test_handles_two_objects_used_many_times(self):
        obj1, obj2 = [], []
        objects = [FunctionWithSingleCall('four', {'w': obj1, 'x': obj2,
                                                   'y': obj1, 'z': obj2}, False)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_four_returns_false_for_w_equal_list_and_x_equal_list_and_y_equal_list_and_z_equal_list(self):")
        assert_contains(result, "alist1 = []")
        assert_contains(result, "alist2 = []")
        assert_contains(result, "self.assertEqual(False, four(w=alist1, x=alist2, y=alist1, z=alist2))")

    def test_handles_many_objects_used_many_times(self):
        obj1, obj2, obj3 = {}, {}, {}
        objects = [FunctionWithSingleCall('six', {'a': obj1, 'b': obj2,
                                                  'c': obj3, 'd': obj1,
                                                  'e': obj2, 'f': obj3}, False)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_six_returns_false_for_a_equal_dict_and_b_equal_dict_and_c_equal_dict_and_d_equal_dict_and_e_equal_dict_and_f_equal_dict(self):")
        assert_contains(result, "adict1 = {}")
        assert_contains(result, "adict2 = {}")
        assert_contains(result, "adict3 = {}")
        assert_contains(result, "self.assertEqual(False, six(a=adict1, b=adict2, c=adict3, d=adict1, e=adict2, f=adict3))")

    def test_uses_argument_name_when_argument_is_used_as_return_value(self):
        obj = []
        objects = [FunctionWithSingleCall('identity', {'x': obj}, obj)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_identity_returns_x_for_x_equal_list(self):")
        assert_contains(result, "alist = []")
        assert_contains(result, "self.assertEqual(alist, identity(x=alist))")

    def test_handles_objects_that_depend_on_each_other(self):
        inner = {}
        outer = [inner]
        objects = [FunctionWithSingleCall('contains', {'inner': inner, 'outer': outer}, True)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_contains_returns_true_for_inner_equal_dict_and_outer_equal_list(self):")
        assert_contains(result, "adict = {}")
        assert_contains(result, "self.assertEqual(True, contains(inner=adict, outer=[adict]))")

    def test_handles_objects_which_setups_depend_on_each_other(self):
        inner = []
        outer = [inner]
        objects = [FunctionWithSingleCall('mangle', {'a1': inner, 'a2': outer, 'a3': outer}, False)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_mangle_returns_false_for_a1_equal_list_and_a2_equal_list_and_a3_equal_list(self):")
        assert_contains(result, "alist1 = []")
        assert_contains(result, "alist2 = [alist1]")
        assert_contains(result, "self.assertEqual(False, mangle(a1=alist1, a2=alist2, a3=alist2))")

    def test_handles_reused_objects_in_method_calls(self):
        alist = []
        klass = ClassWithMethods('Doubler', [('double', [({'lst': alist}, (alist, alist))])])

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_double_returns_tuple_for_list(self):")
        assert_contains(result, "alist = []")
        assert_contains(result, "doubler = Doubler()")
        assert_contains(result, "self.assertEqual((alist, alist), doubler.double(lst=alist))")

    def test_generates_sample_assertions_in_test_stubs_for_functions(self):
        objects = [Function('something', args=['arg1', 'arg2', '*rest'])]
        result = generate_single_test_module(template='nose', objects=objects)

        assert_contains(result, "class TestSomething:")
        assert_contains(result, "# assert_equal(expected, something(arg1, arg2, *rest))")
        assert_contains(result, "raise SkipTest # TODO: implement your test here")

    def test_generates_sample_setup_and_sample_assertions_in_test_stubs_for_classes_without_init(self):
        objects = [Class('Something', [Method('method', args=['**kwds'])])]
        result = generate_single_test_module(template='nose', objects=objects)

        assert_contains(result, "class TestSomething:")
        assert_contains(result, "def test_method(self):")
        assert_contains(result, "# something = Something()")
        assert_contains(result, "# assert_equal(expected, something.method(**kwds))")
        assert_contains(result, "raise SkipTest # TODO: implement your test here")

    def test_generates_sample_setup_and_sample_assertions_in_test_stubs_for_classes_with_init(self):
        objects = [Class('SomethingElse', [Method('__init__', args=['self', 'arg'])])]
        result = generate_single_test_module(template='nose', objects=objects)

        assert_contains(result, "class TestSomethingElse:")
        assert_contains(result, "def test___init__(self):")
        assert_contains(result, "# something_else = SomethingElse(arg)")
        assert_doesnt_contain(result, "# assert_equal(expected, something_else.__init__(arg))")
        assert_contains(result, "raise SkipTest # TODO: implement your test here")

    def test_generates_sample_setup_and_sample_assertions_in_test_stubs_for_classes_with_new(self):
        objects = [Class('SomethingCompletelyDifferent', [Method('__new__', args=['self', 'x'])])]
        result = generate_single_test_module(template='nose', objects=objects)

        assert_contains(result, "class TestSomethingCompletelyDifferent:")
        assert_contains(result, "def test___new__(self):")
        assert_contains(result, "# something_completely_different = SomethingCompletelyDifferent(x)")
        assert_doesnt_contain(result, "# assert_equal(expected, something_completely_different.__new__(x))")
        assert_contains(result, "raise SkipTest # TODO: implement your test here")

    def test_generates_valid_setup_in_test_stubs_for_classes_with_init_that_uses_nested_arguments(self):
        objects = [Class('Something', [Method('__init__', args=['self', ('narg1', 'narg2')])])]
        result = generate_single_test_module(template='nose', objects=objects)

        assert_contains(result, "# something = Something((narg1, narg2))")

    def test_generates_valid_assertions_in_test_stubs_for_functions_that_use_nested_arguments(self):
        objects = [Function('something', args=['arg1', ('narg1', 'narg2'), 'arg2'])]
        result = generate_single_test_module(template='nose', objects=objects)

        assert_contains(result, "# assert_equal(expected, something(arg1, (narg1, narg2), arg2))")

class TestRaisedExceptions:
    def test_generates_assert_raises_for_functions_with_exceptions(self):
        function = FunctionWithSingleException('square', {'x': 'hello'}, TypeError())

        result = generate_single_test_module(objects=[function])

        assert_contains(result, "def test_square_raises_type_error_for_hello(self):")
        assert_contains(result, "self.assertRaises(TypeError, lambda: square(x='hello'))")

    def test_generates_assert_raises_stub_for_functions_with_string_exceptions(self):
        function = FunctionWithSingleException('bad_function', {}, "bad error")

        result = generate_single_test_module(objects=[function])

        assert_contains(result, "def test_bad_function_raises_bad_error(self):")
        assert_contains(result, "# self.assertRaises(<TODO: 'bad error'>, lambda: bad_function())")

    def test_generates_assert_raises_for_init_methods_with_exceptions(self):
        klass = ClassWithMethods('Something', [('__init__', [({'x': 123}, ValueError())])], 'exception')

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_creation_with_123_raises_value_error(self):")
        assert_contains(result, "self.assertRaises(ValueError, lambda: Something(x=123))")

    def test_generates_assert_raises_stub_for_init_methods_with_exceptions(self):
        klass = ClassWithMethods('Something', [('__init__', [({'x': lambda: 42}, ValueError())])], 'exception')

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_creation_with_function_raises_value_error(self):")
        assert_contains(result, "# self.assertRaises(ValueError, lambda: Something(x=<TODO: function>))")

    def test_generates_assert_raises_for_normal_methods_with_exceptions(self):
        klass = ClassWithMethods('Something', [('method', [({}, KeyError())])], 'exception')

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_method_raises_key_error(self):")
        assert_contains(result, "something = Something()")
        assert_contains(result, "self.assertRaises(KeyError, lambda: something.method())")

    def test_generates_imports_for_user_defined_exceptions(self):
        klass = Class("UserDefinedException")
        function = Function("throw")
        function.calls = [FunctionCall(function, {}, exception=UserObject(None, klass))]

        result = generate_single_test_module(objects=[function, klass])

        assert_contains(result, "from module import UserDefinedException")

    def test_doesnt_generate_imports_for_builtin_exceptions(self):
        function = FunctionWithSingleException('throw', {}, Exception())

        result = generate_single_test_module(objects=[function])

        assert_doesnt_contain(result, "import Exception")

    def test_generates_assert_raises_test_stub_for_functions_which_take_functions_as_arguments(self):
        function = FunctionWithSingleException('high', {'f': lambda: 42}, NotImplementedError())

        result = generate_single_test_module(objects=[function])

        assert_contains(result, "def test_high_raises_not_implemented_error_for_function(self):")
        assert_contains(result, "# self.assertRaises(NotImplementedError, lambda: high(f=<TODO: function>))")

    def test_generates_assert_raises_for_generator_functions_with_exceptions(self):
        objects = [GeneratorWithSingleException('throw', {'string': {}}, TypeError())]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_throw_raises_type_error_for_dict(self):")
        assert_contains(result, "self.assertRaises(TypeError, lambda: list(islice(throw(string={}), 1)))")

class TestExceptionsPassedAsValues:
    def test_generates_assert_equal_for_exception_returned_as_value(self):
        objects = [FunctionWithSingleCall('error_factory', {}, MemoryError(0, "OOM!"))]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_error_factory_returns_memory_error(self):")
        assert_contains(result, "self.assertEqual(MemoryError(0, 'OOM!'), error_factory())")

    def test_handles_environment_error_with_two_arguments(self):
        objects = [FunctionWithSingleCall('arg_list_too_long',
                                          {}, EnvironmentError(7, 'Arg list too long'))]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_arg_list_too_long_returns_environment_error(self):")
        assert_contains(result, "self.assertEqual(EnvironmentError(7, 'Arg list too long'), arg_list_too_long())")

    def test_handles_environment_error_with_three_arguments(self):
        objects = [FunctionWithSingleCall('bad_address',
                                          {}, EnvironmentError(14, 'Bad address', 'module.py'))]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_bad_address_returns_environment_error(self):")
        assert_contains(result, "self.assertEqual(EnvironmentError(14, 'Bad address', 'module.py'), bad_address())")

class TestGeneratorOnTheFilesystem(TempDirectory):
    def test_uses_existing_destination_directory(self):
        project = ProjectInDirectory(self.tmpdir)
        add_tests_to_project(project, [], 'unittest')
        # Simply make sure it doesn't raise any exceptions.

    def test_doesnt_generate_test_files_with_no_test_cases(self):
        project = ProjectInDirectory(self.tmpdir).with_modules(["module.py"])
        test_file = os.path.join(project.path, "test_module.py")

        add_tests_to_project(project, [os.path.join(project.path, "module.py")], 'unittest')

        assert not os.path.exists(test_file)

    def test_doesnt_overwrite_existing_files_which_werent_analyzed(self):
        TEST_CONTENTS = "# test"
        project = TestableProject(self.tmpdir)
        # File exists, but project does NOT contain corresponding test module.
        existing_file = os.path.join(project.new_tests_directory, "test_module.py")
        putfile(project.path, existing_file, TEST_CONTENTS)

        def add_and_save():
            add_tests_to_project(project, [os.path.join(project.path, "module.py")], 'unittest')
            project.save()

        assert_raises(ModuleNeedsAnalysis, add_and_save)
        assert_equal(TEST_CONTENTS, read_file_contents(project._path_for_test("test_module.py")))

    def test_creates_new_test_module_if_no_of_the_existing_match(self):
        project = TestableProject(self.tmpdir, ["test_other.py"])

        add_tests_to_project(project, [os.path.join(project.path, "module.py")], 'unittest')

        project_test_cases = get_test_cases(project)
        assert_length(project_test_cases, 1)
        assert_length(project["test_other"].test_cases, 0)

    def test_doesnt_overwrite_existing_files_which_were_modified_since_last_analysis(self):
        TEST_CONTENTS = "# test"
        project = TestableProject(self.tmpdir, ["test_module.py"])
        # File exists, and project contains corresponding, but outdated, test module.
        existing_file = putfile(project.path, "test_module.py", TEST_CONTENTS)
        project["test_module"].created = time.time() - 3600

        def add_and_save():
            add_tests_to_project(project, [os.path.join(project.path, "module.py")], 'unittest')
            project.save()

        assert_raises(ModuleNeedsAnalysis, add_and_save)
        assert_equal(TEST_CONTENTS, read_file_contents(existing_file))

class TestGeneratorWithTestDirectoryAsFile(TempDirectory):
    def setUp(self):
        super(TestGeneratorWithTestDirectoryAsFile, self).setUp()

        self.project = TestableProject(self.tmpdir)
        putfile(self.project.path, self.project.new_tests_directory, "its content")
        self.module_path = os.path.join(self.project.path, "module.py")
        def add_and_save():
            add_tests_to_project(self.project, [self.module_path], 'unittest')
            self.project.save()
        self.add_and_save = add_and_save

    def test_raises_an_exception_if_destdir_is_a_file(self):
        assert_raises(ModuleSaveError, self.add_and_save)

    def test_doesnt_save_pickle_file_if_module_save_error_is_raised(self):
        mtime = get_last_modification_time(self.project._get_pickle_path())
        assert_raises(ModuleSaveError, self.add_and_save)
        assert_equal(mtime, get_last_modification_time(self.project._get_pickle_path()))

class TestGeneratorWithSingleModule:
    def setUp(self):
        self.project = EmptyProject().with_modules(["module.py", "test_module.py"], create_files=False)
        self.project["module"].add_object(Function("function"))
        self.module_path = os.path.join(self.project.path, "module.py")

    def test_adds_imports_to_existing_test_files_only_if_they_arent_present(self):
        self.project["test_module"].imports = ['unittest']
        add_tests_to_project(self.project, [self.module_path], 'unittest')
        assert_equal(['unittest'], self.project["test_module"].imports)

        self.project["test_module"].imports = [('nose', 'SkipTest')]
        add_tests_to_project(self.project, [self.module_path], 'unittest')
        assert_equal_sets(['unittest', ('nose', 'SkipTest')], self.project["test_module"].imports)

    def test_appends_new_test_classes_to_existing_test_files(self):
        TEST_CONTENTS = "class TestSomething: pass\n\n"
        module = inspect_code(self.project, "test_module.py", TEST_CONTENTS)

        add_tests_to_project(self.project, [self.module_path], 'unittest')

        assert_contains(module.get_content(), TEST_CONTENTS)
        assert_contains(module.get_content(), "class TestFunction(unittest.TestCase):")

    def test_associates_test_cases_with_application_modules(self):
        add_tests_to_project(self.project, [self.module_path], 'unittest')

        project_test_cases = get_test_cases(self.project)
        assert_length(project_test_cases, 1)
        assert_equal(project_test_cases[0].associated_modules, [self.project["module"]])

    def test_chooses_the_right_existing_test_module_for_new_test_case(self):
        self.project.create_module("test_other.py")

        add_tests_to_project(self.project, [self.module_path], 'unittest')

        assert_length(self.project["test_module"].test_cases, 1)
        assert_length(self.project["test_other"].test_cases, 0)

    def test_comments_assertions_with_user_objects_that_cannot_be_constructed(self):
        klass, instance = ClassWithInstanceWithoutReconstruction("Something")

        function = FunctionWithSingleCall("nofun", {'x': instance}, "something else")
        self.project["module"].add_objects([klass, function])

        add_tests_to_project(self.project, [self.module_path], 'unittest')
        result = self.project["test_module"].get_content()

        assert_contains(result, "def test_nofun_returns_something_else_for_something_instance(self):")
        assert_contains(result, "# self.assertEqual('something else', nofun(x=<TODO: test.test_generator.Something>))")

    def test_generates_type_assertions_for_calls_with_composite_objects_which_elements_cannot_be_constructed(self):
        klass, instance = ClassWithInstanceWithoutReconstruction("Unspeakable")

        function = FunctionWithSingleCall("morefun", {}, [instance])
        self.project["module"].add_objects([klass, function])

        add_tests_to_project(self.project, [self.module_path], 'unittest')
        result = self.project["test_module"].get_content()

        assert_contains(result, "def test_morefun_returns_list(self):")
        assert_contains(result, "self.assertEqual(list, type(morefun()))")

class TestGeneratorMessages(CapturedLogger):
    def test_reports_each_module_it_generates_tests_for(self):
        paths = ["first.py", "another.py", P("one/more.py")]
        project = EmptyProject().with_modules(paths, create_files=False)

        add_tests_to_project(project, paths, 'unittest')

        for path in paths:
            assert_contains_once(self._get_log_output(),
                                 "Generating tests for module %s." % path)

    def test_reports_each_added_test_class(self):
        objects = [Class('SomeClass', [Method('some_method')]), Function('some_function')]
        generate_single_test_module(objects=objects)

        assert_contains_once(self._get_log_output(),
                             "Adding generated TestSomeClass to %s." % P("tests/test_module.py"))
        assert_contains_once(self._get_log_output(),
                             "Adding generated TestSomeFunction to %s." % P("tests/test_module.py"))

class TestGeneratorDebugMessages(CapturedDebugLogger):
    def test_debug_output_includes_packages_and_module_names(self):
        project = EmptyProject().with_modules(["module.py"], create_files=False)
        project["module"].add_object(Function('some_function'))

        add_tests_to_project(project, ["module"], 'unittest')

        assert_matches(r"\d+\.\d+ generator:\d+ INFO: Generating tests for module module.py.\n",
                       self._get_log_output(), anywhere=True)
        assert_matches(r"\d+\.\d+ generator\.adder:\d+ INFO: Adding generated TestSomeFunction to %s.\n" % re.escape(P("tests/test_module.py")),
                       self._get_log_output(), anywhere=True)

class TestConstructorAsString:
    def setUp(self):
        self.serialize = make_fresh_serialize()

    def test_reconstructs_set_from_sets_module(self):
        call_string = constructor_as_string(self.serialize(sets.Set([1, 2, 3])))

        assert_equal_strings("Set([1, 2, 3])", call_string)
        assert_equal_sets([("sets", "Set")], call_string.imports)

    def test_reconstructs_immutable_set_from_sets_module(self):
        call_string = constructor_as_string(self.serialize(sets.ImmutableSet([1, 2, 3])))

        assert_equal_strings("ImmutableSet([1, 2, 3])", call_string)
        assert_equal_sets([("sets", "ImmutableSet")], call_string.imports)

    def test_reconstructs_builtin_set(self):
        # Set builtin was added in Python 2.4.
        if sys.version_info < (2, 4):
            raise SkipTest

        call_string = constructor_as_string(self.serialize(set([1, 2, 3])))

        assert_equal_strings("set([1, 2, 3])", call_string)
        assert_equal_sets([], call_string.imports)

    def test_reconstructs_builtin_frozenset(self):
        # Frozenset builtin was added in Python 2.4.
        if sys.version_info < (2, 4):
            raise SkipTest

        call_string = constructor_as_string(self.serialize(frozenset([1, 2, 3])))

        assert_equal_strings("frozenset([1, 2, 3])", call_string)
        assert_equal_sets([], call_string.imports)

    def test_reconstructs_integer_arrays(self):
        call_string = constructor_as_string(self.serialize(array.array('I', [1, 2, 3, 4])))

        assert_equal_strings("array.array('I', [1L, 2L, 3L, 4L])", call_string)
        assert_equal_sets(['array'], call_string.imports)

    def test_reconstructs_floating_point_arrays(self):
        call_string = constructor_as_string(self.serialize(array.array('d', [1, 2, 3, 4])))

        assert_equal_strings("array.array('d', [1.0, 2.0, 3.0, 4.0])", call_string)
        assert_equal_sets(['array'], call_string.imports)

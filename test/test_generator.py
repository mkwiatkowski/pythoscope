import os
import re
import time

from fixture import TempIO
from nose.tools import assert_equal, assert_not_equal, assert_raises

from pythoscope.astvisitor import parse
from pythoscope.generator import add_tests_to_project
from pythoscope.store import Project, Module, Class, Method, Function, \
     ModuleNeedsAnalysis, ModuleSaveError, TestClass, TestMethod, \
     MethodCall, FunctionCall, LiveObject, wrap_call_arguments, \
     wrap_object, PointOfEntry
from pythoscope.util import read_file_contents, get_last_modification_time

from helper import assert_contains, assert_doesnt_contain, assert_length,\
     CustomSeparator, generate_single_test_module, ProjectInDirectory, \
     ProjectWithModules, TestableProject, assert_contains_once, \
     PointOfEntryMock, get_test_cases, assert_equal_sets

# Let nose know that those aren't test functions/classes.
add_tests_to_project.__test__ = False
TestClass.__test__ = False
TestMethod.__test__ = False


def ClassWithMethods(classname, methods, exit_point='output'):
    method_objects = []
    method_calls = []

    for name, calls in methods:
        method = Method(name)
        method_objects.append(method)
        for input, output in calls:
            if exit_point == 'output':
                method_calls.append(MethodCall(method, wrap_call_arguments(input), output=wrap_object(output)))
            elif exit_point == 'exception':
                method_calls.append(MethodCall(method, wrap_call_arguments(input), exception=wrap_object(output())))

    klass = Class(classname, methods=method_objects)
    live_object = LiveObject(12345, klass, PointOfEntry(Project('.'), 'poe'))
    live_object.calls = method_calls
    klass.add_live_object(live_object)

    return klass

def FunctionWithCalls(funcname, calls):
    poe = PointOfEntryMock()
    function = Function(funcname)
    function.calls = [FunctionCall(poe, function, wrap_call_arguments(i), wrap_object(o)) for (i,o) in calls]
    return function

def FunctionWithSingleCall(funcname, input, output):
    return FunctionWithCalls(funcname, [(input, output)])

def FunctionWithExceptions(funcname, calls):
    poe = PointOfEntryMock()
    function = Function(funcname)
    function.calls = [FunctionCall(poe, function, wrap_call_arguments(i), exception=wrap_object(e())) for (i,e) in calls]
    return function

def FunctionWithSingleException(funcname, input, exception):
    return FunctionWithExceptions(funcname, [(input, exception)])

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

    def test_generates_nice_name_for_init_method(self):
        objects = [Class('SomeClass', [Method('__init__')])]
        result = generate_single_test_module(objects=objects)
        assert_contains(result, "def test_object_initialization(self):")

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
        objects = [Class('SomeClass', map(Method, ['_semiprivate', '__private', '__eq__']))]
        result = generate_single_test_module(objects=objects)
        assert_doesnt_contain(result, "class TestSomeClass(unittest.TestCase):")

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

        assert re.match(r"import unittest.*?class TestFunction.*?if __name__ == '__main__'", result, re.DOTALL)

    def test_ignores_test_modules(self):
        result = generate_single_test_module()
        assert_equal("", result)

    def test_uses_existing_destination_directory(self):
        project = ProjectInDirectory()
        add_tests_to_project(project, [], 'unittest')
        # Simply make sure it doesn't raise any exceptions.

    def test_doesnt_generate_test_files_with_no_test_cases(self):
        project = ProjectWithModules(["module.py"], ProjectInDirectory)
        test_file = os.path.join(project.path, "test_module.py")

        add_tests_to_project(project, [os.path.join(project.path, "module.py")], 'unittest')

        assert not os.path.exists(test_file)

    def test_doesnt_overwrite_existing_files_which_werent_analyzed(self):
        TEST_CONTENTS = "# test"
        project = TestableProject()
        # File exists, but project does NOT contain corresponding test module.
        existing_file = os.path.join(project.new_tests_directory, "test_module.py")
        project.path.putfile(existing_file, TEST_CONTENTS)

        def add_and_save():
            add_tests_to_project(project, [os.path.join(project.path, "module.py")], 'unittest')
            project.save()

        assert_raises(ModuleNeedsAnalysis, add_and_save)
        assert_equal(TEST_CONTENTS, read_file_contents(project._path_for_test("test_module.py")))

    def test_creates_new_test_module_if_no_of_the_existing_match(self):
        project = TestableProject(["test_other.py"], ProjectInDirectory)

        add_tests_to_project(project, [os.path.join(project.path, "module.py")], 'unittest')

        project_test_cases = get_test_cases(project)
        assert_length(project_test_cases, 1)
        assert_length(project["test_other"].test_cases, 0)

    def test_doesnt_overwrite_existing_files_which_were_modified_since_last_analysis(self):
        TEST_CONTENTS = "# test"
        project = TestableProject(["test_module.py"])
        # File exists, and project contains corresponding, but outdated, test module.
        existing_file = project.path.putfile("test_module.py", TEST_CONTENTS)
        project["test_module"].created = time.time() - 3600

        def add_and_save():
            add_tests_to_project(project, [os.path.join(project.path, "module.py")], 'unittest')
            project.save()

        assert_raises(ModuleNeedsAnalysis, add_and_save)
        assert_equal(TEST_CONTENTS, read_file_contents(existing_file))

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

    def test_ignores_internal_object_calls(self):
        klass = ClassWithMethods('Something', [('method', [({'argument': 1}, 'result')])])
        live_object = klass.live_objects[('poe', 12345)]
        method_call = live_object.calls[0]

        subcall = MethodCall(Method('private'), {'argument': wrap_object(2)}, wrap_object(False))
        method_call.add_subcall(subcall)
        live_object.add_call(subcall)

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

    def test_generates_assert_raises_for_functions_with_exceptions(self):
        function = FunctionWithSingleException('square', {'x': 'hello'}, TypeError)

        result = generate_single_test_module(objects=[function])

        assert_contains(result, "def test_square_raises_type_error_for_hello(self):")
        assert_contains(result, "self.assertRaises(TypeError, lambda: square(x='hello'))")

    def test_generates_assert_raises_for_init_methods_with_exceptions(self):
        klass = ClassWithMethods('Something', [('__init__', [({'x': 123}, ValueError)])], 'exception')

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_creation_with_123_raises_value_error(self):")
        assert_contains(result, "self.assertRaises(ValueError, lambda: Something(x=123))")

    def test_generates_assert_raises_stub_for_init_methods_with_exceptions(self):
        klass = ClassWithMethods('Something', [('__init__', [({'x': lambda: 42}, ValueError)])], 'exception')

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_creation_with_function_raises_value_error(self):")
        assert_contains(result, "# self.assertRaises(ValueError, lambda: Something(x=<TODO: function>))")

    def test_generates_assert_raises_for_normal_methods_with_exceptions(self):
        klass = ClassWithMethods('Something', [('method', [({}, KeyError)])], 'exception')

        result = generate_single_test_module(objects=[klass])

        assert_contains(result, "def test_method_raises_key_error(self):")
        assert_contains(result, "something = Something()")
        assert_contains(result, "self.assertRaises(KeyError, lambda: something.method())")

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

    def test_generates_assert_equal_type_test_stub_for_functions_which_take_and_return_functions(self):
        objects = [FunctionWithSingleCall('highest', {'f': lambda: 42}, lambda: 43)]

        result = generate_single_test_module(objects=objects)

        assert_contains(result, "def test_highest_returns_function_for_function(self):")
        assert_contains(result, "# self.assertEqual(types.FunctionType, type(highest(f=<TODO: function>)))")

    def test_generates_assert_raises_test_stub_for_functions_which_take_functions_as_arguments(self):
        function = FunctionWithSingleException('high', {'f': lambda: 42}, NotImplementedError)

        result = generate_single_test_module(objects=[function])

        assert_contains(result, "def test_high_raises_not_implemented_error_for_function(self):")
        assert_contains(result, "# self.assertRaises(NotImplementedError, lambda: high(f=<TODO: function>))")

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

class TestGeneratorWithTestDirectoryAsFile:
    def setUp(self):
        self.project = TestableProject()
        self.project.path.putfile(self.project.new_tests_directory, "its content")
        self.module_path = os.path.join(self.project.path, "module.py")
        def add_and_save():
            add_tests_to_project(self.project, [self.module_path], 'unittest')
            self.project.save()
        self.add_and_save = add_and_save

    def test_raises_an_exception_if_destdir_is_a_file(self):
        assert_raises(ModuleSaveError, self.add_and_save)

    def test_doesnt_save_pickle_file_if_module_save_error_is_raised(self):
        mtime = get_last_modification_time(self.project._get_pickle_path())
        try: self.add_and_save()
        except ModuleSaveError: pass
        assert_equal(mtime, get_last_modification_time(self.project._get_pickle_path()))

class TestGeneratorWithSingleModule:
    def setUp(self):
        self.project = ProjectWithModules(["module.py", "test_module.py"])
        self.project["module"].objects = [Function("function")]
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
        self.project["test_module"].code = parse(TEST_CONTENTS)

        add_tests_to_project(self.project, [self.module_path], 'unittest')

        assert_contains(self.project["test_module"].get_content(), TEST_CONTENTS)
        assert_contains(self.project["test_module"].get_content(), "class TestFunction(unittest.TestCase):")

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

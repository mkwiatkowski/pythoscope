from nose.tools import assert_equal
from nose.plugins.skip import SkipTest

from pythoscope.inspector.dynamic import trace_function, trace_exec, \
     inspect_point_of_entry
from pythoscope.store import Function, Method

from helper import TestableProject, assert_length


class ProjectMock(object):
    def __init__(self):
        self._methods = {}
        self._functions = {}

    def find_method(self, name, classname, modulepath):
        method_id = (name, classname, modulepath)
        if not self._methods.has_key(method_id):
            self._methods[method_id] = Method(name)
        return self._methods[method_id]

    def find_function(self, name, modulepath):
        function_id = (name, modulepath)
        if not self._functions.has_key(function_id):
            self._functions[function_id] = Function(name)
        return self._functions[function_id]

    def get_callables(self):
        return self._methods.values() + self._functions.values()

class PointOfEntryMock(object):
    def __init__(self, project, content):
        self.project = project
        self.content = content

    def get_content(self):
        return self.content

def collect_callables(fun):
    project = ProjectMock()
    trace_function(project, fun)
    return project.get_callables()

def collect_callables_from_string(string):
    project = ProjectMock()
    trace_exec(project, string)
    return project.get_callables()

def assert_function_call(expected_input, expected_output, function_call):
    assert_equal(expected_input, function_call.input)
    assert_equal(expected_output, function_call.output)


was_run = False
def function_setting_was_run():
    global was_run
    was_run = True

def function_doing_nothing():
    pass

def function_calling_other_function():
    def other_function():
        pass
    other_function()
    other_function()

def function_calling_two_different_functions():
    def first_function():
        pass
    def second_function():
        pass
    first_function()
    second_function()

def function_calling_another_with_two_required_arguments():
    def function(x, y):
        return x + y
    function(7, 13)
    function(1, 2)
    function(42, 43)

def function_calling_another_with_optional_arguments():
    def function(x, y, w=4, z="!"):
        return x + " " + y + w * z
    function("Hello", "world")
    function("Bye", "world", 2)
    function("Humble", "hello", 1, ".")

def function_calling_another_with_keyword_arguments():
    def function(x, y=1):
        return x - y
    function(1)
    function(x=2)
    function(3, y=4)
    function(x=5, y=6)

def function_calling_another_with_varargs():
    def function(x, *rest):
        return list(rest) + [x]
    function(1)
    function(2, 3)
    function(4, 5, 6)

def function_calling_another_with_varargs_only():
    def function(*args):
        return len(args)
    function()

def function_calling_another_with_nested_arguments():
    def function((a, b), c):
        return [c, b, a]
    function((1, 2), 3)

def function_calling_another_with_varkw():
    def function(x, **kwds):
        return kwds.get(x, 42)
    function('a')
    function('b', a=1, b=2)
    function('c', y=3, w=4, z=5)

def function_calling_recursive_function():
    def fac(x):
        if x == 0:
            return 1
        return x * fac(x-1)
    fac(4)

def function_creating_new_style_class():
    class New(object):
        pass

def function_creating_old_style_class():
    class New:
        pass

def function_creating_class_with_function_calls():
    def function(x):
        return x + 1
    class New(object):
        function(42)

def function_calling_a_method():
    class Class(object):
        def method(self):
            pass
    Class().method()

def function_calling_methods_with_strangely_named_self():
    class Class(object):
        def strange_method(s):
            pass
        def another_strange_method(*args):
            pass
    Class().strange_method()
    Class().another_strange_method()

def function_calling_two_methods_with_the_same_name_from_different_classes():
    class FirstClass(object):
        def method(self):
            pass
    class SecondClass(object):
        def method(self):
            pass
    FirstClass().method()
    SecondClass().method()

def function_calling_other_which_uses_name_and_module_variables():
    def function():
        try:
            __name__
            __module__
        except:
            pass
    function()

class TestTraceFunction:
    "trace_function"
    def test_runs_given_function(self):
        collect_callables(function_setting_was_run)

        assert was_run, "Function wasn't executed."

    def test_returns_empty_list_when_no_calls_to_other_functions_were_made(self):
        trace = collect_callables(function_doing_nothing)

        assert_equal([], trace)

    def test_returns_a_list_with_a_single_element_when_calls_to_a_single_functions_were_made(self):
        trace = collect_callables(function_calling_other_function)

        assert_equal(1, len(trace))

    def test_returns_a_list_with_function_objects(self):
        trace = collect_callables(function_calling_two_different_functions)

        assert all(isinstance(obj, Function) for obj in trace)

    def test_returns_function_objects_corresponding_to_functions_that_were_called(self):
        trace = collect_callables(function_calling_two_different_functions)

        assert_equal(set(['first_function', 'second_function']),
                     set(f.name for f in trace))

    def test_returns_function_objects_with_all_calls_recorded(self):
        trace = collect_callables(function_calling_other_function)
        function = trace.pop()

        assert_equal(2, len(function.calls))

    def test_returns_function_objects_with_calls_that_use_required_arguments(self):
        trace = collect_callables(function_calling_another_with_two_required_arguments)
        function = trace.pop()

        assert_function_call({'x':7,  'y':13},  20, function.calls[0])
        assert_function_call({'x':1,  'y':2},    3, function.calls[1])
        assert_function_call({'x':42, 'y':43},  85, function.calls[2])

    def test_returns_function_objects_with_calls_that_use_optional_arguments(self):
        trace = collect_callables(function_calling_another_with_optional_arguments)
        function = trace.pop()

        assert_function_call({'x': "Hello",  'y': "world", 'w': 4, 'z': "!"}, "Hello world!!!!", function.calls[0])
        assert_function_call({'x': "Bye",    'y': "world", 'w': 2, 'z': "!"}, "Bye world!!",     function.calls[1])
        assert_function_call({'x': "Humble", 'y': "hello", 'w': 1, 'z': "."}, "Humble hello.",   function.calls[2])

    def test_returns_function_objects_with_calls_that_use_keyword_arguments(self):
        trace = collect_callables(function_calling_another_with_keyword_arguments)
        function = trace.pop()

        assert_function_call({'x': 1, 'y': 1},  0, function.calls[0])
        assert_function_call({'x': 2, 'y': 1},  1, function.calls[1])
        assert_function_call({'x': 3, 'y': 4}, -1, function.calls[2])
        assert_function_call({'x': 5, 'y': 6}, -1, function.calls[3])

    def test_returns_function_objects_with_calls_that_use_varargs(self):
        trace = collect_callables(function_calling_another_with_varargs)
        function = trace.pop()

        assert_function_call({'x': 1, 'rest': ()},     [1],     function.calls[0])
        assert_function_call({'x': 2, 'rest': (3,)},   [3,2],   function.calls[1])
        assert_function_call({'x': 4, 'rest': (5, 6)}, [5,6,4], function.calls[2])

    def test_returns_function_objects_with_calls_that_use_varargs(self):
        trace = collect_callables(function_calling_another_with_varargs_only)
        function = trace.pop()

        assert_function_call({'args': ()}, 0, function.calls[0])

    def test_returns_function_objects_with_calls_that_use_nested_arguments(self):
        trace = collect_callables(function_calling_another_with_nested_arguments)
        function = trace.pop()

        assert_function_call({'a': 1, 'b': 2, 'c': 3}, [3, 2, 1], function.calls[0])

    def test_returns_function_objects_with_calls_that_use_varkw(self):
        trace = collect_callables(function_calling_another_with_varkw)
        function = trace.pop()

        assert_function_call({'x': 'a', 'kwds': {}},                       42, function.calls[0])
        assert_function_call({'x': 'b', 'kwds': {'a': 1, 'b': 2}},          2, function.calls[1])
        assert_function_call({'x': 'c', 'kwds': {'y': 3, 'w': 4, 'z': 5}}, 42, function.calls[2])

    def test_interprets_recursive_calls_properly(self):
        trace = collect_callables(function_calling_recursive_function)
        function = trace.pop()

        assert_function_call({'x': 0}, 1, function.calls[0])
        assert_function_call({'x': 1}, 1, function.calls[1])
        assert_function_call({'x': 2}, 2, function.calls[2])
        assert_function_call({'x': 3}, 6, function.calls[3])
        assert_function_call({'x': 4}, 24, function.calls[4])

    def test_ignores_new_style_class_creation(self):
        trace = collect_callables(function_creating_new_style_class)

        assert_equal([], trace)

    def test_ignores_old_style_class_creation(self):
        trace = collect_callables(function_creating_old_style_class)

        assert_equal([], trace)

    def test_traces_function_calls_inside_class_definitions(self):
        trace = collect_callables(function_creating_class_with_function_calls)
        function = trace.pop()

        assert_function_call({'x': 42}, 43, function.calls[0])

    def test_returns_a_list_with_method_objects(self):
        trace = collect_callables(function_calling_a_method)

        assert all(isinstance(obj, Method) for obj in trace)

    def test_handles_methods_with_strangely_named_self(self):
        trace = collect_callables(function_calling_methods_with_strangely_named_self)

        assert all(isinstance(obj, Method) for obj in trace)
        assert_equal(set(['strange_method', 'another_strange_method']),
                     set(m.name for m in trace))

    def test_distinguishes_between_methods_with_the_same_name_from_different_classes(self):
        trace = collect_callables(function_calling_two_methods_with_the_same_name_from_different_classes)

        assert_equal([('method', 1), ('method', 1)],
                     [(f.name, len(f.calls)) for f in trace])

    def test_distinguishes_between_classes_and_functions(self):
        trace = collect_callables(function_calling_other_which_uses_name_and_module_variables)

        assert_equal(1, len(trace))

class TestTraceExec:
    "trace_exec"
    def test_returns_function_objects_with_all_calls_recorded(self):
        trace = collect_callables_from_string("f = lambda x: x + 1; f(5); f(42)")
        function = trace.pop()

        assert_function_call({'x': 5},  6,  function.calls[0])
        assert_function_call({'x': 42}, 43, function.calls[1])

class TestInspectPointOfEntry:
    def test_properly_gathers_all_input_and_output_values(self):
        project = TestableProject()
        project.path.putfile("module.py", "def function(x):\n  return x + 1\n")
        poe = PointOfEntryMock(project, "from module import function\nfunction(42)\n")

        inspect_point_of_entry(poe)

        assert_length(project["module"].functions, 1)
        assert_length(project["module"].functions[0].calls, 1)
        assert_function_call({'x': 42}, 43, project["module"].functions[0].calls[0])

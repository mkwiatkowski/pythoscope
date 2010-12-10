from pythoscope.side_effect import ListAppend, ListExtend, ListInsert, ListPop,\
    GlobalRebind

from assertions import *
from inspector_assertions import *
from inspector_helper import *


def function_doing_to_list(action, *args, **kwds):
    alist = kwds.get('alist', [])
    def fun():
        def foo(x):
            getattr(x, action)(*args)
        foo(alist)
    return fun

def assert_builtin_method_side_effects(se, klass, obj, *args):
    assert_instance(se, klass)
    assert_serialized(obj, se.obj)
    assert_collection_of_serialized(list(args), list(se.args))

class TestMutation:
    def test_handles_list_append(self):
        fun = function_doing_to_list('append', 1)
        call = inspect_returning_single_call(fun)
        se = assert_one_element_and_return(call.side_effects)
        assert_builtin_method_side_effects(se, ListAppend, [], 1)

    def test_handles_list_extend(self):
        fun = function_doing_to_list('extend', [2])
        call = inspect_returning_single_call(fun)
        se = assert_one_element_and_return(call.side_effects)
        assert_builtin_method_side_effects(se, ListExtend, [], [2])

    def test_handles_list_insert(self):
        fun = function_doing_to_list('insert', 0, 3)
        call = inspect_returning_single_call(fun)
        se = assert_one_element_and_return(call.side_effects)
        assert_builtin_method_side_effects(se, ListInsert, [], 0, 3)

    def test_handles_list_pop_without_arguments(self):
        fun = function_doing_to_list('pop', alist=[1, 2, 3])
        call = inspect_returning_single_call(fun)
        se = assert_one_element_and_return(call.side_effects)
        assert_builtin_method_side_effects(se, ListPop, [1, 2, 3])

    def test_handles_list_pop_with_an_argument(self):
        fun = function_doing_to_list('pop', 1, alist=[1, 2, 3])
        call = inspect_returning_single_call(fun)
        se = assert_one_element_and_return(call.side_effects)
        assert_builtin_method_side_effects(se, ListPop, [1, 2, 3], 1)

    def test_handles_list_pop_without_arguments_on_empty_list(self):
        def fun():
            def foo(x):
                try:
                    x.pop()
                except IndexError:
                    pass
            foo([])
        call = inspect_returning_single_call(fun)
        assert_equal([], call.side_effects)

class TestGlobalVariables:
    def test_handles_rebinding(self):
        def function_rebinding_global_variable():
            def function():
                global was_run
                was_run = False
            function()
        call = inspect_returning_single_call(function_rebinding_global_variable)
        se = assert_one_element_and_return(call.side_effects)
        assert_instance(se, GlobalRebind)
        assert_equal('test.test_tracing_side_effects', se.module)
        assert_equal('was_run', se.name)
        assert_serialized(False, se.value)

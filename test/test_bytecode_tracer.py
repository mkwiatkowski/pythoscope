import cPickle
import dis
import os
import shutil
import sys
import tempfile

from nose import SkipTest
from nose.tools import assert_equal

from pythoscope.store import CodeTree
from pythoscope.util import write_content_to_file

from bytecode_tracer import BytecodeTracer, rewrite_function


return_value = None
class TestBytecodeTracer:
    def setup(self):
        self._traces = []
        self._ignored_events = ['load_global', 'store_global']
        self.btracer = BytecodeTracer()

    def _trace(self, frame, event, arg):
        try:
            if arg is not sys.settrace:
                for ret in self.btracer.trace(frame, event):
                    if ret[0] is not None and ret[0] not in self._ignored_events:
                        self._traces.append(ret)
        except TypeError:
            pass
        return self._trace

    def assert_trace(self, *traces):
        assert_equal(self._traces, list(traces))

    def assert_trace_slice(self, start, end, *traces):
        assert_equal(self._traces[start:end], list(traces))

    def trace_function(self, fun):
        dis.dis(fun.func_code)
        rewrite_function(fun)
        self.btracer.setup()
        sys.settrace(self._trace)
        try:
            fun()
        finally:
            sys.settrace(None)
            self.btracer.teardown()

class TestBytecodeTracerWithDifferentArgumentsCombinations(TestBytecodeTracer):
    def test_traces_builtin_functions_with_no_arguments(self):
        def fun():
            list()
        self.trace_function(fun)
        self.assert_trace(('c_call', (list, [], {})),
                          ('c_return', []))

    def test_traces_builtin_functions_with_single_argument(self):
        def fun():
            repr(4)
        self.trace_function(fun)
        self.assert_trace(('c_call', (repr, [4], {})),
                          ('c_return', "4"))

    def test_traces_builtin_functions_with_two_arguments(self):
        def fun():
            pow(2, 3)
        self.trace_function(fun)
        self.assert_trace(('c_call', (pow, [2, 3], {})),
                          ('c_return', 8))

    def test_traces_builtin_functions_with_keyword_argument(self):
        def fun():
            global return_value
            return_value = property(doc="asdf")
        self.trace_function(fun)
        self.assert_trace(('c_call', (property, [], {'doc': "asdf"})),
                          ('c_return', return_value))

    def test_traces_builtin_functions_with_varargs(self):
        def fun():
            x = [1, 10]
            range(*x)
        self.trace_function(fun)
        self.assert_trace(('c_call', (range, [1, 10], {})),
                          ('c_return', [1, 2, 3, 4, 5, 6, 7, 8, 9]))

    def test_traces_builtin_functions_with_kwargs(self):
        def fun():
            z = {'real': 1, 'imag': 2}
            complex(**z)
        self.trace_function(fun)
        self.assert_trace(('c_call', (complex, [], {'real': 1, 'imag': 2})),
                          ('c_return', complex(1, 2)))

    def test_traces_builtin_functions_with_keyword_and_kwargs(self):
        def fun():
            z = {'imag': 2}
            complex(real=1, **z)
        self.trace_function(fun)
        self.assert_trace(('c_call', (complex, [], {'real': 1, 'imag': 2})),
                          ('c_return', complex(1, 2)))

    def test_traces_builtin_functions_with_keyword_and_varargs(self):
        def fun():
            a = (1,)
            complex(imag=2, *a)
        self.trace_function(fun)
        self.assert_trace(('c_call', (complex, [1], {'imag': 2})),
                          ('c_return', complex(1, 2)))

    def test_traces_builtin_functions_with_both_varargs_and_kwargs(self):
        def fun():
            a = ("asdf", "ascii")
            k = {'errors': 'ignore'}
            unicode(*a, **k)
        self.trace_function(fun)
        self.assert_trace(('c_call', (unicode, ["asdf", "ascii"], {'errors': 'ignore'})),
                          ('c_return', unicode('asdf')))

    def test_traces_builtin_functions_with_keyword_varargs_and_kwargs(self):
        def fun():
            a = ("asdf",)
            k = {'encoding': 'ascii'}
            unicode(errors='ignore', *a, **k)
        self.trace_function(fun)
        self.assert_trace(('c_call', (unicode, ["asdf"], {'encoding': 'ascii', 'errors': 'ignore'})),
                          ('c_return', unicode('asdf')))

    def test_traces_builtin_functions_with_positional_argument_and_kwargs(self):
        def fun():
            z = {'imag': 2}
            complex(1, **z)
        self.trace_function(fun)
        self.assert_trace(('c_call', (complex, [1], {'imag': 2})),
                          ('c_return', complex(1, 2)))

    def test_traces_builtin_functions_with_positional_argument_and_varargs(self):
        def fun():
            global return_value
            a = ("", 'eval')
            return_value = compile("1", *a)
        self.trace_function(fun)
        self.assert_trace(('c_call', (compile, ["1", "", 'eval'], {})),
                          ('c_return', return_value))

    def test_traces_builtin_functions_with_positional_argument_varargs_and_kwargs(self):
        def fun():
            a = ('ascii',)
            k = {'errors': 'ignore'}
            unicode("asdf", *a, **k)
        self.trace_function(fun)
        self.assert_trace(('c_call', (unicode, ["asdf", "ascii"], {'errors': 'ignore'})),
                          ('c_return', unicode('asdf')))

    def test_traces_builtin_functions_with_positional_argument_and_keyword_argument(self):
        def fun():
            unicode("asdf", "ascii", errors='ignore')
        self.trace_function(fun)
        self.assert_trace(('c_call', (unicode, ["asdf", "ascii"], {'errors': 'ignore'})),
                          ('c_return', unicode('asdf')))

    def test_traces_builtin_functions_with_positional_argument_and_keyword_and_kwargs(self):
        def fun():
            k = {'errors': 'ignore'}
            unicode("asdf", encoding='ascii', **k)
        self.trace_function(fun)
        self.assert_trace(('c_call', (unicode, ["asdf"], {'encoding': 'ascii', 'errors': 'ignore'})),
                          ('c_return', unicode('asdf')))

    def test_traces_builtin_functions_with_positional_argument_and_keyword_and_varargs(self):
        def fun():
            a = ("ascii",)
            unicode("asdf", errors='ignore', *a)
        self.trace_function(fun)
        self.assert_trace(('c_call', (unicode, ["asdf", "ascii"], {'errors': 'ignore'})),
                          ('c_return', unicode('asdf')))

    def test_traces_builtin_functions_with_positional_argument_and_keyword_and_varargs_and_kwargs(self):
        def fun():
            global return_value
            a = (1,)
            k = {'doc': ""}
            return_value = property(2, fdel=3, *a, **k)
        self.trace_function(fun)
        self.assert_trace(('c_call', (property, [2, 1], {'fdel': 3, 'doc': ""})),
                          ('c_return', return_value))

class TestBytecodeTracerReturnValues(TestBytecodeTracer):
    def test_traces_builtin_functions_returning_multiple_values(self):
        def fun():
            coerce(1, 1.25)
        self.trace_function(fun)
        self.assert_trace(('c_call', (coerce, [1, 1.25], {})),
                          ('c_return', (1.0, 1.25)))

class TestBytecodeTracerLanguageConstructs(TestBytecodeTracer):
    def test_traces_for_loop(self):
        def fun():
            for x in range(3):
                complex(0, x)
        self.trace_function(fun)
        self.assert_trace(('c_call', (range, [3], {})),
                          ('c_return', [0, 1, 2]),
                          ('c_call', (complex, [0, 0], {})),
                          ('c_return', complex(0, 0)),
                          ('c_call', (complex, [0, 1], {})),
                          ('c_return', complex(0, 1)),
                          ('c_call', (complex, [0, 2], {})),
                          ('c_return', complex(0, 2)))

    def test_traces_for_loop_with_an_iterator_continue_and_else(self):
        def fun():
            global return_value
            return_value = xrange(5)
            for x in return_value:
                if x < 3:
                    continue
                chr(97+x)
            else:
                complex(2, 3)
        self.trace_function(fun)
        self.assert_trace(('c_call', (xrange, [5], {})),
                          ('c_return', return_value),
                          ('c_call', (chr, [100], {})),
                          ('c_return', 'd'),
                          ('c_call', (chr, [101], {})),
                          ('c_return', 'e'),
                          ('c_call', (complex, [2, 3], {})),
                          ('c_return', complex(2, 3)))

    def test_traces_chained_calls(self):
        def fun():
            complex(sum(range(1,11)), 3)
        self.trace_function(fun)
        self.assert_trace(('c_call', (range, [1, 11], {})),
                          ('c_return', [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
                          ('c_call', (sum, [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]], {})),
                          ('c_return', 55),
                          ('c_call', (complex, [55, 3], {})),
                          ('c_return', complex(55, 3)))

    def test_traces_chained_calls_with_extra_computation(self):
        def fun():
            range(sum([1, 2]) + 3)
        self.trace_function(fun)
        self.assert_trace(('c_call', (sum, [[1, 2]], {})),
                          ('c_return', 3),
                          ('c_call', (range, [6], {})),
                          ('c_return', [0, 1, 2, 3, 4, 5]))

    def test_traces_with_blocks(self):
        if sys.version_info < (2, 5):
            raise SkipTest("with statement was added in Python 2.5")
        code = "from __future__ import with_statement; import threading; lock = threading.Lock()\nwith lock: chr(102)"
        def fun():
            eval(compile(code, '<string>', 'exec'))
        self.trace_function(fun)
        # Skip compile, eval, and lock allocation.
        self.assert_trace_slice(-3, -1,
                                ('c_call', (chr, [102], {})),
                                ('c_return', 'f'))

class TestBytecodeTracerWithExceptions(TestBytecodeTracer):
    def test_keeps_tracing_properly_after_an_exception(self):
        def fun():
            try:
                chr(256)
            except ValueError:
                pass
            chr(90)
        self.trace_function(fun)
        self.assert_trace(('c_call', (chr, [256], {})),
                          ('c_return', None),
                          ('c_call', (chr, [90], {})),
                          ('c_return', 'Z'))

    def test_keeps_tracing_properly_after_no_arguments_exception(self):
        def fun():
            try:
                abs()
            except TypeError:
                pass
            chr(65)
        self.trace_function(fun)
        self.assert_trace(('c_call', (abs, [], {})),
                          ('c_return', None),
                          ('c_call', (chr, [65], {})),
                          ('c_return', 'A'))

    def test_keeps_tracing_properly_after_bad_arguments_exception(self):
        def fun():
            try:
                abs("a")
            except TypeError:
                pass
            chr(97)
        self.trace_function(fun)
        self.assert_trace(('c_call', (abs, ["a"], {})),
                          ('c_return', None),
                          ('c_call', (chr, [97], {})),
                          ('c_return', 'a'))

    def test_keeps_tracing_properly_after_not_callable_is_passed_when_it_was_expected(self):
        def fun():
            try:
                map(1, [2, 3])
            except TypeError: # 'int' object is not callable
                pass
            chr(66)
        self.trace_function(fun)
        self.assert_trace(('c_call', (map, [1, [2, 3]], {})),
                          ('c_return', None),
                          ('c_call', (chr, [66], {})),
                          ('c_return', 'B'))

    def test_keeps_tracing_properly_after_exception_in_callback_code(self):
        def bad(x):
            if x > 0:
                raise ValueError
        def fun():
            try:
                map(bad, [0, 1, 2])
            except ValueError:
                pass
            chr(67)
        self.trace_function(fun)
        self.assert_trace(('c_call', (map, [bad, [0, 1, 2]], {})),
                          ('c_return', None),
                          ('c_call', (chr, [67], {})),
                          ('c_return', 'C'))

    def test_keeps_tracing_finally_block_after_an_exception(self):
        def fun():
            try:
                try:
                    raise AttributeError
                except AttributeError:
                    pass
            finally:
                chr(68)
        self.trace_function(fun)
        self.assert_trace(('c_call', (chr, [68], {})),
                          ('c_return', 'D'))

    def test_keeps_tracing_except_block_after_an_exception(self):
        def fun():
            try:
                raise NameError
            except NameError:
                complex(1, 2)
        self.trace_function(fun)
        self.assert_trace(('c_call', (complex, [1, 2], {})),
                          ('c_return', complex(1, 2)))

class TestPrint(TestBytecodeTracer):
    def test_handles_normal_print_with_newline(self):
        def fun():
            print "foo"
        self.trace_function(fun)
        self.assert_trace(('print', "foo"),
                          ('print', os.linesep))

    def test_handles_normal_print_without_newline(self):
        def fun():
            print "foo",
        self.trace_function(fun)
        self.assert_trace(('print', "foo"))

    def test_handles_extended_print_with_newline(self):
        def fun():
            print>>sys.stdout, "foo"
        self.trace_function(fun)
        self.assert_trace(('print_to', ("foo", sys.stdout)),
                          ('print_to', (os.linesep, sys.stdout)))

    def test_handles_extended_print_without_newline(self):
        def fun():
            print>>sys.stdout, "foo",
        self.trace_function(fun)
        self.assert_trace(('print_to', ("foo", sys.stdout)))

class TestBytecodeTracerAutomaticRewriting(TestBytecodeTracer):
    def test_automatically_traces_bytecodes_of_other_callables_being_called(self):
        def other():
            abs(-2)
        def fun():
            other()
        self.trace_function(fun)
        self.assert_trace(('c_call', (abs, [-2], {})),
                          ('c_return', 2))

    def test_handles_python_functions_called_from_within_c_functions(self):
        def other(x):
            return x + 1
        def fun():
            map(other, [1, 2, 3])
        self.trace_function(fun)
        self.assert_trace(('c_call', (map, [other, [1, 2, 3]], {})),
                          ('c_return', [2, 3, 4]))

    def test_handles_c_function_called_from_python_functions_called_from_c_functions(self):
        def other(x):
            return abs(x)
        def fun():
            map(other, [-1, 0, 1])
        self.trace_function(fun)
        self.assert_trace(('c_call', (map, [other, [-1, 0, 1]], {})),
                          ('c_call', (abs, [-1], {})),
                          ('c_return', 1),
                          ('c_call', (abs, [0], {})),
                          ('c_return', 0),
                          ('c_call', (abs, [1], {})),
                          ('c_return', 1),
                          ('c_return', [1, 0, 1]))

    def test_rewrites_each_function_only_once(self):
        def other():
            pass
        def fun():
            other()
            other()
        rewrite_function(other)
        rewritten_code = other.func_code
        self.trace_function(fun)
        assert other.func_code is rewritten_code

    def test_rewrites_code_returned_by_compile(self):
        def fun():
            global return_value
            return_value = compile('abs(-1)', '', 'exec')
            eval(return_value)
        self.trace_function(fun)
        self.assert_trace(('c_call', (compile, ['abs(-1)', '', 'exec'], {})),
                          ('c_return', return_value),
                          ('c_call', (eval, [return_value], {})),
                          ('c_call', (abs, [-1], {})),
                          ('c_return', 1),
                          ('c_return', None))

    def test_rewrites_modules_during_import(self):
        tmpdir = tempfile.mkdtemp()
        write_content_to_file("abs(-2)", os.path.join(tmpdir, 'mod.py'))
        sys.path.insert(0, tmpdir)
        try:
            def fun():
                import mod
            self.trace_function(fun)
            self.assert_trace(('c_call', (abs, [-2], {})),
                              ('c_return', 2))
        finally:
            shutil.rmtree(tmpdir)

    def test_handles_methods(self):
        class Class:
            def method(self, x):
                return abs(x)
        def fun():
            global return_value
            return_value = c = Class()
            c.method(-1)
        self.trace_function(fun)
        self.assert_trace(('c_call', (Class, [], {})),
                          ('c_return', return_value),
                          ('c_call', (abs, [-1], {})),
                          ('c_return', 1))

class TestBytecodeTracerRebinding(TestBytecodeTracer):
    def test_handles_instance_variable_rebinding(self):
        class Class(object):
            def method(self, x):
                self.x = x
        def fun():
            global return_value
            return_value = c = Class()
            c.method(-1)
        self.trace_function(fun)
        self.assert_trace(('c_call', (Class, [], {})),
                          ('c_return', return_value),
                          ('store_attr', (return_value, 'x', -1)))

    def test_handles_instance_variable_rebinding_with_setattr(self):
        class Class(object):
            def method(self, x):
                setattr(self, 'x', x)
        def fun():
            global return_value
            return_value = c = Class()
            c.method(-1)
        self.trace_function(fun)
        self.assert_trace(('c_call', (Class, [], {})),
                          ('c_return', return_value),
                          ('c_call', (setattr, [return_value, 'x', -1], {})),
                          ('c_return', None))

    def test_handles_class_variable_rebinding_with_setattr(self):
        class Class(object):
            pass
        def fun():
            Class.x = 1
        self.trace_function(fun)
        self.assert_trace(('store_attr', (Class, 'x', 1)))

    def test_handles_instance_variable_unbinding(self):
        class Class(object):
            def __init__(self):
                self.x = 1
            def method(self):
                del self.x
        def fun():
            global return_value
            return_value = c = Class()
            c.method()
        self.trace_function(fun)
        self.assert_trace(('c_call', (Class, [], {})),
                          ('c_return', return_value),
                          ('delete_attr', (return_value, 'x')))

class TestBytecodeTracerGlobalAccessAndRebinding(TestBytecodeTracer):
    def setup(self):
        TestBytecodeTracer.setup(self)
        self._ignored_events = []

    def test_handles_global_variable_reading(self):
        global return_value
        return_value = 42
        def fun():
            return return_value
        self.trace_function(fun)
        self.assert_trace(('load_global', ('test.test_bytecode_tracer', 'return_value', 42)))

    def test_handles_global_variable_rebinding(self):
        def fun():
            global return_value
            return_value = 123
        self.trace_function(fun)
        self.assert_trace(('store_global', ('test.test_bytecode_tracer', 'return_value', 123)))

    def test_handles_global_variable_unbinding(self):
        def fun():
            global return_value
            del return_value
        self.trace_function(fun)
        self.assert_trace(('delete_global', ('test.test_bytecode_tracer', 'return_value')))

class TestRewriteFunction:
    def test_handles_functions_with_free_variables(self):
        x = 1
        def fun():
            return x + 1
        rewrite_function(fun)
        assert_equal(fun(), 2)

    def test_handles_bound_methods(self):
        class Class:
            def method(self, x):
                return x + 1
        meth = Class().method
        rewrite_function(meth)
        assert_equal(meth(1), 2)

class TestImportSupportWithOtherModules(TestBytecodeTracer):
    def test_support_with_pickle(self):
        self.btracer.setup()
        # This can raise any number of exceptions.
        #
        # Before I've copied imputil.py version from Python 2.6 sources over,
        # under Python 2.3 it would raise:
        #   PicklingError: Can't pickle <class 'pythoscope.store.CodeTree'>: attribute lookup pythoscope.store.CodeTree failed
        #
        # Before I added support for level argument of the __import__ hook,
        # under Python 2.6 it would raise:
        #   TypeError: _import_hook() takes at most 5 arguments (6 given)
        cPickle.dumps(CodeTree(None), cPickle.HIGHEST_PROTOCOL)
        self.btracer.teardown()

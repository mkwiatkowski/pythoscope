import inspect
import sys
import types

from pythoscope.util import compact, get_self_from_method

from bytecode_tracer import BytecodeTracer, rewrite_function,\
    has_been_rewritten, rewrite_lnotab


# Pythons <= 2.4 surround `exec`uted code with a block named "?",
# while Pythons > 2.4 use "<module>".
IGNORED_NAMES = ["?", "<module>", "<genexpr>"]

def find_variable(frame, varname):
    """Find variable named varname in the scope of a frame.

    Raise a KeyError when the varname cannot be found.
    """
    try:
        return frame.f_locals[varname]
    except KeyError:
        return frame.f_globals[varname]

def callable_type(frame):
    """Return a type of a called frame or raise a KeyError if it can't be
    retrieved.

    The latter is the case for class definitions and method calls, which are
    not refrenced neither in local nor global scope.
    """
    return type(find_variable(frame.f_back, frame.f_code.co_name))

def is_class_definition(frame):
    "Return True if given frame represents a class definition."
    try:
        # Old-style classes are of type "ClassType", while new-style
        # classes or of type "type".
        return callable_type(frame) in [types.ClassType, type]
    except KeyError:
        return frame.f_code.co_names[:2] == ('__name__', '__module__')

class NotMethodFrame(Exception):
    pass

def get_method_information(frame):
    """Analyze the frame and return relevant information about the method
    call it presumably represents.

    Returns a tuple: (self_object, input_dictionary).

    If the frame doesn't represent a method call, raises NotMethodFrame
    exception.
    """
    try:
        args, varargs, varkw, locals = inspect.getargvalues(frame)
        if args:
            # Will raise TypeError if args[0] is a list.
            self = locals[args[0]]
        else:
            # Will raise an IndexError if no arguments were passed.
            self = locals[varargs][0]

        methodname = frame.f_code.co_name
        # Will raise AttributeError when the self is None or doesn't
        # have method with given name.
        method = getattr(self, methodname)

        # This isn't a call on the first argument's method.
        if not method.im_func.func_code == frame.f_code:
            raise NotMethodFrame

        # Remove the "self" argument.
        if args:
            args.pop(0)
        elif varargs and locals[varargs]:
            # No pop(), because locals[varargs] is a tuple.
            locals[varargs] = locals[varargs][1:]
        else:
            raise NotMethodFrame

        return (self, input_from_argvalues(args, varargs, varkw, locals))
    except (AttributeError, KeyError, TypeError, IndexError):
        raise NotMethodFrame

def resolve_args(names, locals):
    """Returns a list of tuples representing argument names and values.

    Handles nested arguments lists well.
        >>> resolve_args([['a', 'b'], 'c'], {'.0': (1, 2), 'c': 3})
        [('a', 1), ('b', 2), ('c', 3)]

        >>> resolve_args(['a', ['b', 'c']], {'.1': (8, 7), 'a': 9})
        [('a', 9), ('b', 8), ('c', 7)]
    """
    result = []
    for i, name in enumerate(names):
        if isinstance(name, list):
            result.extend(zip(name, locals['.%d' % i]))
        else:
            result.append((name, locals[name]))
    return result

def input_from_argvalues(args, varargs, varkw, locals):
    return dict(resolve_args(args + compact([varargs, varkw]), locals))

def make_callable(code):
    if isinstance(code, str):
        code = rewrite_lnotab(compile(code, "<string>", "exec"))
        def function():
            exec code in {}
        return function
    return code

def is_generator_exit(obj):
    try:
        return obj is GeneratorExit
    # Pythons 2.4 and lower don't have GeneratorExit exceptions at all.
    except NameError:
        return False

class StandardTracer(object):
    """Wrapper around basic C{sys.settrace} mechanism that maps 'call', 'return'
    and 'exception' events into more meaningful callbacks.

    See L{ICallback} for details on events that tracer reports.
    """
    def __init__(self, callback):
        self.callback = callback

        self.btracer = BytecodeTracer()

        self.top_level_function = None
        self.sys_modules = None

    # :: function | str -> None
    def trace(self, code):
        """Trace execution of given code. Code may be either a function
        or a string with Python code.

        This method may be invoked many times for a single tracer instance.
        """
        self.setup(code)
        self.btracer.setup()
        rewrite_function(self.top_level_function)
        sys.settrace(self.tracer)
        try:
            self.top_level_function()
        finally:
            sys.settrace(None)
            self.teardown()
            self.btracer.teardown()

    def setup(self, code):
        self.top_level_function = make_callable(code)
        self.sys_modules = sys.modules.keys()

    def teardown(self):
        # Revert any changes to sys.modules.
        # This unfortunatelly doesn't include changes to the modules' state itself.
        # Replaced module instances in sys.modules are also not reverted.
        modnames = [m for m in sys.modules.keys() if m not in self.sys_modules]
        for modname in modnames:
            del sys.modules[modname]

        self.top_level_function = None
        self.sys_modules = None

    def tracer(self, frame, event, arg):
        # Bytecode tracing is unreliable without the rewrite step, so we have
        # to ignore all interactions inside that code. That usually concerns
        # modules that were imported before the tracer started.
        if not has_been_rewritten(frame.f_code):
            return
        bytecode_events = list(self.btracer.trace(frame, event))
        if bytecode_events:
            for ev, args in bytecode_events:
                # Exceptions originating in C code are reported only after
                # execution goes back to the Python level. To regain
                # consistency with other exception events, we simulate
                # an exception raised inside C code just before its return.
                if ev == 'c_return' and event == 'exception':
                    self.handle_standard_tracer_event(frame, event, arg)
                self.handle_bytecode_tracer_event(ev, args)
        return self.handle_standard_tracer_event(frame, event, arg)

    def handle_bytecode_tracer_event(self, event, args):
        if event == 'c_call':
            self.record_c_call(*args)
        elif event == 'c_return':
            self.callback.c_returned(args)
        elif event == 'print':
            pass # TODO
        elif event == 'print_to':
            value, output = args
            pass # TODO

    def handle_standard_tracer_event(self, frame, event, arg):
        if event == 'call':
            if not self.should_ignore_frame(frame):
                if self.record_call(frame):
                    return self.tracer
        elif event == 'return':
            self.callback.returned(arg)
        elif event == 'exception':
            if not is_generator_exit(arg[0]):
                # There are three cases here, each requiring different handling
                # of values in arg[0] and arg[1]. First, we may get a regular
                # exception generated by the `raise` statement. Second, we may
                # get an exception generated inside the interpreter, like an
                # IndexError or NameError. Finally, code in Python < 2.6 can
                # raise a string exception.
                #
                # In each case, arg[0] and arg[1] have different values,
                # described in the table below.
                #
                #               +------------------+---------------------------+
                #               |      arg[0]      |          arg[1]           |
                # +-------------+------------------+---------------------------+
                # | regular     | exception type   | exception instance        |
                # |  exceptions |  (e.g. TypeError)|                           |
                # +-------------+------------------+---------------------------+
                # | interpreter | exception type   | message (a string) or     |
                # |  exceptions |  (e.g. NameError)|  exception initialization |
                # |             |                  |  arguments (a tuple)      |
                # +-------------+------------------+---------------------------+
                # | string      | string itself    | value or None             |
                # |  exceptions |  (e.g. "Error")  |                           |
                # +-------------+------------------+---------------------------+
                #
                # arg[2] in all cases contains an exception traceback.
                if isinstance(arg[0], str):
                    # Return the string itself as an exception and ignore
                    # the value, as it's not used during test generation,
                    # at least for now.
                    exception = arg[0]
                elif isinstance(arg[1], str):
                    # Recreate instance of a single-argument interpreter
                    # exception.
                    exception = arg[0](arg[1])
                elif isinstance(arg[1], tuple):
                    # Recreate instance of a multi-argument interpreter
                    # exception.
                    exception = arg[0](*arg[1])
                else:
                    exception = arg[1]
                self.callback.raised(exception, arg[2])

    def should_ignore_frame(self, frame):
        return is_class_definition(frame) or self.is_ignored_code(frame.f_code)

    def is_ignored_code(self, code):
        if code.co_name in IGNORED_NAMES:
            return True
        if self.top_level_function is not None \
                and code is self.top_level_function.func_code:
            return True
        return False

    def record_call(self, frame):
        code = frame.f_code
        name = code.co_name

        try:
            obj, input = get_method_information(frame)
            return self.callback.method_called(name, obj, input, code, frame)
        except NotMethodFrame:
            input = input_from_argvalues(*inspect.getargvalues(frame))
            return self.callback.function_called(name, input, code, frame)

    def record_c_call(self, func, pargs, kargs):
        func_name = func.__name__
        obj = get_self_from_method(func)
        if obj is not None:
            klass = type(obj)
            self.callback.c_method_called(obj, klass, func_name, pargs)
        else:
            self.callback.c_function_called(func_name, pargs)

class Python23Tracer(StandardTracer):
    """Version of the tracer working around a subtle difference in exception
    handling of Python 2.3.

    In Python 2.4 and higher, when a function (or method) exits with
    an exception, interpreter reports two events to a trace function:
    first 'exception' and then 'return' right after that.

    In Python 2.3 the second event isn't reported, i.e. only 'exception'
    events are passed to a trace function. For the sake of consistency this
    version of the tracer will inject a 'return' event before each consecutive
    exception reported.
    """
    def __init__(self, *args):
        super(Python23Tracer, self).__init__(*args)
        self.propagating_exception = False

    def handle_standard_tracer_event(self, frame, event, arg):
        retval = super(Python23Tracer, self).handle_standard_tracer_event(frame, event, arg)
        if event == 'exception':
            if self.propagating_exception:
                # Don't recur or the propagating_exception flag will be erased
                # and we don't want that.
                # Invoking the method in the superclass instead.
                super(Python23Tracer, self).handle_standard_tracer_event(frame, 'return', None)
            else:
                self.propagating_exception = True
        elif event in ['call', 'return']:
            self.propagating_exception = False
        return retval

if sys.version_info < (2, 4):
    Tracer = Python23Tracer
else:
    Tracer = StandardTracer

class ICallback(object):
    """Interface that Tracer's callback object should adhere to.
    """
    # :: (str, object, dict, code, frame) -> bool
    def method_called(self, name, obj, args, code, frame):
        """Reported when a method with given name is called on a given object.
        'args' represent rest of method arguments (i.e. without bounded object).

        Return value of this method decides whether tracer should simply ignore
        execution of this method, or should it continue tracing its contents.
        True value means 'continue', anything else means 'ignore'.
        """
        raise NotImplementedError("Method method_called() not defined.")

    # :: (str, dict, code, frame) -> bool
    def function_called(self, name, args, code, frame):
        """Reported when a function with given name is called.

        Return value of this method decides whether tracer should simply ignore
        execution of this function, or should it continue tracing its contents.
        True value means 'continue', anything else means 'ignore'.
        """
        raise NotImplementedError("Method function_called() not defined.")

    # :: (object, type, str, tuple) -> None
    def c_method_called(self, obj, klass, name, pargs):
        """Reported when a call to method implemented in C occurs.

        Return value is ignored.
        """
        raise NotImplementedError("Method c_method_called() not defined.")

    # :: (str, tuple) -> None
    def c_function_called(self, name, pargs):
        """Reported when a call to function implemented in C occurs.

        Return value is ignored.
        """
        raise NotImplementedError("Method c_function_called() not defined.")

    # :: object -> None
    def returned(self, output):
        """Reported when function or method returns.

        Return value is ignored.
        """
        raise NotImplementedError("Method returned() not defined.")

    # :: object -> None
    def c_returned(self, output):
        """Reported when a C function or method returns.

        Return value is ignored.
        """
        raise NotImplementedError("Method c_returned() not defined.")

    # :: (exception|str, traceback) -> None
    def raised(self, exception, traceback):
        """Reported when exception is raised.

        Return value is ignored.
        """
        raise NotImplementedError("Method raised() not defined.")

import inspect
import sys
import types

from pythoscope.util import compact


IGNORED_NAMES = ["<module>", "<genexpr>"]

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
        def function():
            exec code in {}
        return function
    return code

class Tracer(object):
    """Wrapper around basic C{sys.settrace} mechanism that maps 'call', 'return'
    and 'exception' events into more meaningful callbacks.

    See L{ICallback} for details on events that Tracer reports.
    """
    def __init__(self, callback):
        self.callback = callback

        self.top_level_function = None
        self.sys_modules = None

    # :: function | str -> None
    def trace(self, code):
        """Trace execution of given code. Code may be either a function
        or a string with Python code.

        This method may be invoked many times for a single Tracer instance.
        """
        self.setup(code)
        sys.settrace(self.tracer)
        try:
            self.top_level_function()
        finally:
            sys.settrace(None)
            self.teardown()

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
        if event == 'call':
            if not self.should_ignore_frame(frame):
                if self.record_call(frame):
                    return self.tracer
        elif event == 'return':
            self.callback.returned(arg)
        elif event == 'exception':
            if arg[0] is not GeneratorExit:
                self.callback.raised(arg[1], arg[2])

    def should_ignore_frame(self, frame):
        return is_class_definition(frame) or self.is_ignored_code(frame.f_code)

    def is_ignored_code(self, code):
        if code.co_name in IGNORED_NAMES:
            return True
        if code in [self.top_level_function.func_code]:
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

    # :: object -> None
    def returned(self, output):
        """Reported when function or method returns.

        Return value is ignored.
        """
        raise NotImplementedError("Method returned() not defined.")

    # :: (type, traceback) -> None
    def raised(self, exception, traceback):
        """Reported when exception is raised.

        Return value is ignored.
        """
        raise NotImplementedError("Method raised() not defined.")

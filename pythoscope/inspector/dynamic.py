import inspect
import optparse
import sys
import types


IGNORED_NAMES = ["<module>", "<genexpr>"]

_traced_callables = None
_top_level_function = None
_sys_modules = None
_point_of_entry = None
_call_stack = None

class CallStack(object):
    def __init__(self):
        self.last_traceback = None
        self.stack = []
        self.top_level_calls = []

    def called(self, call):
        if self.stack:
            self.stack[-1].add_subcall(call)
        else:
            self.top_level_calls.append(call)
        self.stack.append(call)

    def returned(self, output):
        if self.stack:
            caller = self.stack.pop()
            caller.set_output(output)

            # If the last exception is reported by sys.exc_info() it means
            # it was handled inside the returning call.
            handled_traceback = sys.exc_info()[2]
            if handled_traceback is self.last_traceback:
                caller.clear_exception()

    def raised(self, exception, traceback):
        if self.stack:
            caller = self.stack[-1]
            caller.set_exception(exception)
            self.last_traceback = traceback

def compact(list):
    "Remove all occurences of None from the given list."
    return [x for x in list if x is not None]

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

def get_code_from(thing):
    # Frames have f_code attribute.
    if hasattr(thing, 'f_code'):
        return thing.f_code
    # Function objects have func_code attribute.
    elif hasattr(thing, 'func_code'):
        return thing.func_code
    else:
        raise TypeError("Don't know how to get code from %s" % thing)

def is_ignored_code(code):
    if code.co_name in IGNORED_NAMES:
        return True
    if code in [_top_level_function.func_code, stop_tracing.func_code]:
        return True
    return False

def create_call(frame):
    code = get_code_from(frame)
    name = code.co_name
    modulepath = code.co_filename

    if not is_ignored_code(code):
        try:
            self, input = get_method_information(frame)
            classname = self.__class__.__name__
            return _point_of_entry.create_method_call(name, classname, modulepath, self, input)
        except NotMethodFrame:
            input = input_from_argvalues(*inspect.getargvalues(frame))
            return _point_of_entry.create_function_call(name, modulepath, input)

def tracer(frame, event, arg):
    if event == 'call':
        if not is_class_definition(frame):
            call = create_call(frame)
            if call:
                _call_stack.called(call)
                return tracer
    elif event == 'return':
        _call_stack.returned(arg)
    elif event == 'exception':
        _call_stack.raised(arg[1], arg[2])

def start_tracing():
    sys.settrace(tracer)

def stop_tracing():
    sys.settrace(None)

def trace_function(fun):
    """Trace given function and add Calls to given PointOfEntry instance.
    """
    global _top_level_function
    _top_level_function = fun

    start_tracing()
    try:
        fun()
    finally:
        stop_tracing()

def trace_exec(exec_string, scope={}):
    def fun():
        exec exec_string in scope
    return trace_function(fun)

def setup_tracing(point_of_entry):
    global _sys_modules, _point_of_entry, _call_stack

    # Put project's path into PYTHONPATH, so point of entry's imports work.
    sys.path.insert(0, point_of_entry.project.path)
    point_of_entry.clear_previous_run()    

    _call_stack = CallStack()
    _point_of_entry = point_of_entry
    _sys_modules = sys.modules.keys()

def teardown_tracing(point_of_entry):
    global _sys_modules, _point_of_entry, _call_stack

    # Revert any changes to sys.modules.
    # This unfortunatelly doesn't include changes to the modules' state itself.
    # Replaced module instances in sys.modules are also not reverted.
    modnames = [m for m in sys.modules.keys() if m not in _sys_modules]
    for modname in modnames:
        del sys.modules[modname]

    # Copy the call graph structure to the point of entry.
    _point_of_entry.call_graph = _call_stack.top_level_calls
    _point_of_entry.finalize_inspection()

    _point_of_entry = None
    _call_stack = None
    sys.path.remove(point_of_entry.project.path)

def inspect_point_of_entry(point_of_entry):
    setup_tracing(point_of_entry)
    try:
        trace_exec(point_of_entry.get_content())
    finally:
        teardown_tracing(point_of_entry)

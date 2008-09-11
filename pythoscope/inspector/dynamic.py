import inspect
import optparse
import sys
import types

from pythoscope.store import Call, Function, Method


IGNORED_NAMES = ["<module>", "<genexpr>"]

_traced_callables = None
_top_level_function = None
_sys_modules = None
_point_of_entry = None

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
    result = []
    for name in names:
        if isinstance(name, list):
            result.extend(resolve_args(name, locals))
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

def create_function_call(calling_frame, return_vaule):
    input = input_from_argvalues(*inspect.getargvalues(calling_frame))
    return FunctionCall(input, return_value)

def create_method_call(calling_frame, return_vaule):
    args, varargs, varkw, locals = argvalues_without_self(calling_frame)
    input = dict(resolve_args(args + compact([varargs, varkw]), locals))

    return FunctionCall(input, return_value)

def is_ignored_code(code):
    if code.co_name in IGNORED_NAMES:
        return True
    if code in [_top_level_function.func_code, stop_tracing.func_code]:
        return True
    return False

def add_call_to(calling_frame, return_value):
    code = get_code_from(calling_frame)
    name = code.co_name
    modulepath = code.co_filename

    if not is_ignored_code(code):
        try:
            self, input = get_method_information(calling_frame)
            classname = self.__class__.__name__
            _point_of_entry.add_method_call(name, classname, modulepath, id(self), input, return_value)
        except NotMethodFrame:
            input = input_from_argvalues(*inspect.getargvalues(calling_frame))
            _point_of_entry.add_function_call(name, modulepath, input, return_value)

def create_tracer(calling_frame):
    def tracer(frame, event, arg):
        if event == 'call':
            if not is_class_definition(frame):
                return create_tracer(frame)
        elif event == 'return':
            add_call_to(calling_frame, arg)
    return tracer

def start_tracing():
    sys.settrace(create_tracer(None))

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
    # TODO: Intercept and record unhandled exceptions.
    finally:
        stop_tracing()

def trace_exec(exec_string, scope={}):
    def fun():
        exec exec_string in scope
    return trace_function(fun)

def setup_tracing(point_of_entry):
    global _sys_modules, _point_of_entry

    # Put project's path into PYTHONPATH, so point of entry's imports work.
    sys.path.insert(0, point_of_entry.project.path)
    point_of_entry.clear_previous_run()    
    _point_of_entry = point_of_entry
    _sys_modules = sys.modules.keys()

def teardown_tracing(point_of_entry):
    global _sys_modules, _point_of_entry

    # Revert any changes to sys.modules.
    # This unfortunatelly doesn't include changes to the modules' state itself.
    # Replaced module instances in sys.modules are also not reverted.
    modnames = [m for m in sys.modules.keys() if m not in _sys_modules]
    for modname in modnames:
        del sys.modules[modname]

    _point_of_entry = None
    sys.path.remove(point_of_entry.project.path)

def inspect_point_of_entry(point_of_entry):
    setup_tracing(point_of_entry)
    calls = trace_exec(point_of_entry.get_content())
    teardown_tracing(point_of_entry)

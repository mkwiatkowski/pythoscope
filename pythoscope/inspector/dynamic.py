import inspect
import optparse
import sys
import types

from pythoscope.store import Call, Function, Method


IGNORED_NAMES = ["<module>", "<genexpr>"]

_traced_callables = None
_top_level_function = None
_project = None

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
        return callable_type(frame) is types.ClassType
    except KeyError:
        return frame.f_code.co_names[:2] == ('__name__', '__module__')

def get_self_from_frame(frame):
    """Try to get the self object from the given frame.

    Returns None if the frame doesn't reference a method call.
    """
    try:
        args, varargs, _, locals = inspect.getargvalues(frame)
        if args:
            # Will raise TypeError if args[0] is a list.
            return locals[args[0]]
        else:
            # Will raise an IndexError if no arguments were passed.
            return locals[varargs][0]
    except (KeyError, TypeError, IndexError):
        return None

def is_method_call(frame):
    "Return True if given frame represents a method call."
    try:
        self       = get_self_from_frame(frame)
        methodname = frame.f_code.co_name
        method     = getattr(self, methodname)
        return method.im_func.func_code == frame.f_code
    except AttributeError:
        return False

def resolve_args(names, locals):
    result = []
    for name in names:
        if isinstance(name, list):
            result.extend(resolve_args(name, locals))
        else:
            result.append((name, locals[name]))
    return result

def get_code_from(thing):
    # Frames have f_code attribute.
    if hasattr(thing, 'f_code'):
        return thing.f_code
    # Function objects have func_code attribute.
    elif hasattr(thing, 'func_code'):
        return thing.func_code
    else:
        raise TypeError("Don't know how to get code from %s" % thing)

def get_name_and_modulename_from(thing):
    code = get_code_from(thing)
    return (code.co_name, code.co_filename)

def create_call(calling_frame, return_value):
    args, varargs, varkw, locals = inspect.getargvalues(calling_frame)
    input = dict(resolve_args(args + compact([varargs, varkw]), locals))

    return Call(input, return_value)

def find_method(project, frame):
    name, modulename = get_name_and_modulename_from(frame)
    object = get_self_from_frame(frame)
    classname = object.__class__.__name__

    return project.find_method(name=name, classname=classname, modulename=modulename)

def find_function(project, frame):
    name, modulename = get_name_and_modulename_from(frame)

    return project.find_function(name=name, modulename=modulename)

def find_callable(project, frame):
    """Based on the frame, find the right callable object.
    """
    if is_method_call(frame):
        return find_method(project, frame)
    else:
        return find_function(project, frame)

def is_ignored_call(frame):
    name, modulename = get_name_and_modulename_from(frame)
    if name in IGNORED_NAMES:
        return True

    code = get_code_from(frame)
    if code in [_top_level_function.func_code, stop_tracing.func_code]:
        return True

    return False

def add_call_to(calling_frame, return_value):
    if not is_ignored_call(calling_frame):
        callable = find_callable(_project, calling_frame)
        # If we can't find the callable in Project, we don't care about it.
        # This way we don't record any information about thid-party and
        # dynamically created code.
        if callable:
            call = create_call(calling_frame, return_value)
            callable.add_call(call)

def create_tracer(calling_frame):
    def tracer(frame, event, arg):
        if event == 'call':
            if not is_class_definition(frame):
                return create_tracer(frame)
        elif event == 'return':
            add_call_to(calling_frame, arg)
    return tracer

def start_tracing(project):
    global _project
    _project = project
    sys.settrace(create_tracer(None))

def stop_tracing():
    sys.settrace(None)
    global _project
    _project = None

def trace_function(project, fun):
    """Trace given function and add Calls to given Project instance.
    """
    global _top_level_function
    _top_level_function = fun

    start_tracing(project)
    fun()
    stop_tracing()

def trace_exec(project, exec_string, scope={}):
    def fun():
        exec exec_string in scope
    return trace_function(project, fun)

def inspect_point_of_entry(project, point_of_entry):
    calls = trace_exec(project, point_of_entry.get_content())

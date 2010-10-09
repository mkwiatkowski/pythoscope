from copy import copy

from pythoscope.event import Event
from pythoscope.generator.dependencies import sorted_by_timestamp

from pythoscope.serializer import BuiltinException, ImmutableObject, MapObject,\
    UnknownObject, SequenceObject
from pythoscope.side_effect import SideEffect
from pythoscope.store import FunctionCall, UserObject, MethodCall,\
    GeneratorObject, GeneratorObjectInvocation
from pythoscope.util import flatten


class AssertionLine(Event):
    def __init__(self, timestamp):
        # We don't call Event.__init__ on purpose, we set our own timestamp.
        self.timestamp = timestamp

class EqualAssertionLine(AssertionLine):
    def __init__(self, expected, actual, timestamp):
        AssertionLine.__init__(self, timestamp)
        self.expected = expected
        self.actual = actual

# :: SerializedObject -> SerializedObject
def object_copy(obj):
    new_obj = copy(obj)
    new_obj.timestamp = obj.timestamp+0.5
    return new_obj

# :: Call -> int
def last_call_action_timestamp(call):
    if call.side_effects:
        return call.side_effects[-1].timestamp
    return call.timestamp

# :: Call -> [AssertionLine]
def assertions_for_call(call):
    after_call_timestamp = last_call_action_timestamp(call)
    if call.output.timestamp < call.timestamp:
        # If object existed before the call we need two assertions: one for
        # identity, the other for value.
        return [EqualAssertionLine(call.output, call, after_call_timestamp+0.25),
                EqualAssertionLine(object_copy(call.output), call.output, after_call_timestamp+0.5)]
    else:
        # If it didn't exist before the call we just need a value assertion.
        return [EqualAssertionLine(object_copy(call.output), call, after_call_timestamp+0.5)]

# :: AssertionLine -> [Event]
def expand_into_timeline(assertion_line):
    return sorted_by_timestamp(list(set(get_contained_events([assertion_line.expected, assertion_line.actual]))) + [assertion_line])

# :: SerializedObject | Call | [SerializedObject] | [Call] -> [Event]
def get_contained_events(obj):
    """Return a list of Events this object requires during testing.

    This function will descend recursively if objects contained within given
    object are composite themselves.
    """
    if isinstance(obj, list):
        return flatten(map(get_contained_events, obj))
    elif isinstance(obj, ImmutableObject):
        # ImmutableObjects are self-sufficient.
        return []
    elif isinstance(obj, UnknownObject):
        return []
    elif isinstance(obj, SequenceObject):
        return get_those_and_contained_events(obj.contained_objects)
    elif isinstance(obj, MapObject):
        return get_those_and_contained_events(flatten(obj.mapping))
    elif isinstance(obj, BuiltinException):
        return get_those_and_contained_events(obj.args)
    elif isinstance(obj, UserObject):
        return get_contained_events(obj.get_init_and_external_calls())
    elif isinstance(obj, (FunctionCall, MethodCall, GeneratorObjectInvocation)):
        if obj.raised_exception():
            output = obj.exception
        else:
            output = obj.output
        return get_those_and_contained_events(obj.input.values() + [output] + list(obj.side_effects))
    elif isinstance(obj, GeneratorObject):
        if obj.is_activated():
            return get_those_and_contained_events(obj.args.values()) +\
                get_contained_events(obj.calls)
        else:
            return []
    elif isinstance(obj, SideEffect):
        return [obj] + get_those_and_contained_events(list(obj.affected_objects))
    else:
        raise TypeError("Wrong argument to get_contained_events: %r." % obj)

# :: [Event] -> [Event]
def get_those_and_contained_events(objs):
    """Return a list containing given objects and all objects contained within
    them.
    """
    return objs + get_contained_events(objs)

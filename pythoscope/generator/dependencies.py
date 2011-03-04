from pythoscope.generator.lines import *
from pythoscope.generator.method_call_context import MethodCallContext
from pythoscope.serializer import BuiltinException, ImmutableObject, MapObject,\
    UnknownObject, SequenceObject, SerializedObject, LibraryObject
from pythoscope.store import FunctionCall, UserObject, MethodCall,\
    GeneratorObject, GeneratorObjectInvocation, CallToC
from pythoscope.side_effect import SideEffect
from pythoscope.util import all_of_type, flatten


# :: [SerializedObject|Call] -> [SerializedObject|Call]
def sorted_by_timestamp(objects):
    return sorted(objects, key=lambda o: o.timestamp)

# :: ([Event], int) -> [Event]
def older_than(events, reference_timestamp):
    return filter(lambda e: e.timestamp < reference_timestamp, events)

# :: Call -> Call
def top_caller(call):
    if call.caller is None:
        return call
    return top_caller(call.caller)

# :: (Call, int) -> [Call]
def subcalls_before_timestamp(call, reference_timestamp):
    for c in older_than(call.subcalls, reference_timestamp):
        yield c
        for sc in subcalls_before_timestamp(c, reference_timestamp):
            yield sc

# :: Call -> [Call]
def calls_before(call):
    """Go up the call graph and return all calls that happened before
    the given one.

    >>> class Call(object):
    ...     def __init__(self, caller, timestamp):
    ...         self.subcalls = []
    ...         self.caller = caller
    ...         self.timestamp = timestamp
    ...         if caller:
    ...             caller.subcalls.append(self)
    >>> top = Call(None, 1)
    >>> branch1 = Call(top, 2)
    >>> leaf1 = Call(branch1, 3)
    >>> branch2 = Call(top, 4)
    >>> leaf2 = Call(branch2, 5)
    >>> leaf3 = Call(branch2, 6)
    >>> leaf4 = Call(branch2, 7)
    >>> branch3 = Call(top, 8)
    >>> calls_before(branch3) == [top, branch1, leaf1, branch2, leaf2, leaf3, leaf4]
    True
    >>> calls_before(leaf3) == [top, branch1, leaf1, branch2, leaf2]
    True
    >>> calls_before(branch2) == [top, branch1, leaf1]
    True
    >>> calls_before(branch1) == [top]
    True
    """
    top = top_caller(call)
    return [top] + list(subcalls_before_timestamp(top, call.timestamp))

# :: [Call] -> [SideEffect]
def side_effects_of(calls):
    return flatten(map(lambda c: c.side_effects, calls))

# :: Call -> [SideEffect]
def side_effects_before(call):
    return older_than(side_effects_of(calls_before(call)), call.timestamp)

# :: [SideEffect] -> [SerializedObject]
def objects_affected_by_side_effects(side_effects):
    return flatten(map(lambda se: se.affected_objects, side_effects))

# :: [Event] -> [SerializedObject]
def resolve_dependencies(events):
    events_so_far = set()
    def get_those_and_contained_objects(objs):
        return all_of_type(objs, SerializedObject) + get_contained_objects(objs)
    def get_contained_objects(obj):
        if isinstance(obj, list):
            return flatten(map(get_contained_objects, obj))
        if obj in events_so_far:
            return []
        else:
            events_so_far.add(obj)
        if isinstance(obj, SequenceObject):
            return get_those_and_contained_objects(obj.contained_objects)
        elif isinstance(obj, MapObject):
            return get_those_and_contained_objects(flatten(obj.mapping))
        elif isinstance(obj, LibraryObject):
            return get_those_and_contained_objects(obj.arguments)
        elif isinstance(obj, BuiltinException):
            return get_those_and_contained_objects(obj.args)
        elif isinstance(obj, UserObject):
            return get_contained_objects(obj.get_init_call() or [])
        elif isinstance(obj, (FunctionCall, MethodCall, GeneratorObjectInvocation)):
            return get_those_and_contained_objects(obj.input.values())
        elif isinstance(obj, GeneratorObject):
            if obj.is_activated():
                return get_those_and_contained_objects(obj.args.values() + obj.calls)
            return []
        elif isinstance(obj, SideEffect):
            return get_those_and_contained_objects(list(obj.affected_objects))
        elif isinstance(obj, MethodCallContext):
            return get_those_and_contained_objects([obj.call, obj.user_object])
        elif isinstance(obj, EqualAssertionLine):
            return get_those_and_contained_objects([obj.expected, obj.actual])
        elif isinstance(obj, GeneratorAssertionLine):
            return get_contained_objects(obj.generator_call)
        elif isinstance(obj, RaisesAssertionLine):
            return get_those_and_contained_objects([obj.call, obj.expected_exception])
        elif isinstance(obj, Assign):
            if isinstance(obj.obj, SerializedObject):
                return get_those_and_contained_objects([obj.obj])
            return []
        elif isinstance(obj, (ImmutableObject, UnknownObject, CallToC, CommentLine,
                              SkipTestLine, EqualAssertionStubLine, VariableReference)):
            return []
        else:
            raise TypeError("Wrong argument to get_contained_objects: %s." % repr(obj))
    return get_contained_objects(events)

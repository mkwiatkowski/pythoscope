from pythoscope.serializer import SerializedObject
from pythoscope.side_effect import SideEffect
from pythoscope.util import flatten


class Dependencies(object):
    def __init__(self, all=None):
        if all is None:
            all = []
        self.all = all

    def get_objects(self):
        return filter(lambda x: isinstance(x, SerializedObject), self.all)

    def replace_pair_with_event(self, event1, event2, new_event):
        """Replaces pair of events with a single event. The second event
        must be a SideEffect.

        Optimizer only works on values with names, which means we don't really
        have to traverse the whole Project tree and replace all occurences
        of an object. It is sufficient to replace it on the dependencies
        timeline, which will be used as a base for naming objects and their
        later usage.
        """
        if not isinstance(event2, SideEffect):
            raise TypeError("Second argument to replace_pair_with_object has to be a SideEffect, was %r instead." % event2)
        new_event.timestamp = event1.timestamp
        self.all[self.all.index(event1)] = new_event
        if isinstance(event1, SerializedObject):
            if not isinstance(new_event, SerializedObject):
                raise TypeError("Expected new_event to be of the same type as event1 in a call to replace_pair_with_object, got %r instead." % new_event)
        self.all.remove(event2)

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

# :: ([SideEffect], set([SerializedObject])) -> [SideEffect]
def side_effects_that_affect_objects(side_effects, objects):
    "Filter out side effects that are irrelevant to given set of objects."
    for side_effect in side_effects:
        for obj in side_effect.affected_objects:
            if obj in objects:
                yield side_effect

# :: [SideEffect] -> [SerializedObject]
def objects_affected_by_side_effects(side_effects):
    return flatten(map(lambda se: se.affected_objects, side_effects))

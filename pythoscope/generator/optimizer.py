from pythoscope.serializer import SequenceObject
from pythoscope.side_effect import SideEffect, ListAppend


class NonSerializingSequenceObject(SequenceObject):
    def __init__(self, contained_objects):
        super(NonSerializingSequenceObject, self).__init__([], lambda x:x)
        self.contained_objects = contained_objects

# :: ([Event], Event, SideEffect, Event) -> [Event]
def replace_pair_with_event(timeline, event1, event2, new_event):
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
    timeline[timeline.index(event1)] = new_event
    timeline.remove(event2)

def optimize(timeline):
    """Shorten a chain of events, by replacing pairs with single events.

    For example, a creation of an empty list and appending to it a number:

        >>> x = []
        >>> x.append(1)

    can be shortened to a single creation:

        >>> x = [1]

    and that's exactly what this optimizer does.
    """
    i = 0
    while i+1 < len(timeline):
        e1 = timeline[i]
        e2 = timeline[i+1]
        # "x = [y..]" and "x.append(z)" is "x = [y..z]"
        if isinstance(e1, SequenceObject) and isinstance(e2, ListAppend) and e2.obj == e1:
            replace_pair_with_event(timeline, e1, e2, NonSerializingSequenceObject(e1.contained_objects + list(e2.args)))
            continue
        i += 1
    return timeline

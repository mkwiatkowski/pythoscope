from copy import copy

from pythoscope.event import Event


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

# :: Call -> [AssertionLine]
def assertions_for_call(call):
    if call.output.timestamp < call.timestamp:
        # If object existed before the call we need two assertions: one for
        # identity, the other for value.
        return [EqualAssertionLine(call.output, call, call.timestamp+0.25),
                EqualAssertionLine(object_copy(call.output), call.output, call.timestamp+0.75)]
    else:
        # If it didn't exist before the call we just need a value assertion.
        return [EqualAssertionLine(object_copy(call.output), call, call.timestamp+0.75)]

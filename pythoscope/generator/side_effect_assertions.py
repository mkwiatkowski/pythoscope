from copy import copy

from pythoscope.event import Event


class AssertionLine(Event):
    def __init__(self):
        # We don't call Event.__init__ on purpose, we set our own timestamp.
        pass # TODO

class EqualAssertionLine(AssertionLine):
    def __init__(self, expected, actual):
        AssertionLine.__init__(self)
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
        return [EqualAssertionLine(call.output, call),
                EqualAssertionLine(object_copy(call.output), call.output)]
    else:
        # If it didn't exist before the call we just need a value assertion.
        return [EqualAssertionLine(object_copy(call.output), call)]

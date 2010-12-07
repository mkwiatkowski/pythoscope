from pythoscope.event import Event


__all__ = ['EqualAssertionLine', 'EqualAssertionStubLine',
           'GeneratorAssertionLine', 'RaisesAssertionLine',
           'CommentLine', 'SkipTestLine']

class AssertionLine(Event):
    def __init__(self, timestamp):
        # We don't call Event.__init__ on purpose, we set our own timestamp.
        self.timestamp = timestamp

class EqualAssertionLine(AssertionLine):
    def __init__(self, expected, actual, timestamp):
        AssertionLine.__init__(self, timestamp)
        self.expected = expected
        self.actual = actual

class EqualAssertionStubLine(AssertionLine):
    def __init__(self, actual, timestamp):
        AssertionLine.__init__(self, timestamp)
        self.actual = actual

class GeneratorAssertionLine(AssertionLine):
    def __init__(self, generator_call, timestamp):
        AssertionLine.__init__(self, timestamp)
        self.generator_call = generator_call

class RaisesAssertionLine(AssertionLine):
    def __init__(self, expected_exception, call, timestamp):
        AssertionLine.__init__(self, timestamp)
        self.expected_exception = expected_exception
        self.call = call

class CommentLine(AssertionLine):
    def __init__(self, comment, timestamp):
        AssertionLine.__init__(self, timestamp)
        self.comment = comment

class SkipTestLine(AssertionLine):
    def __init__(self, timestamp):
        AssertionLine.__init__(self, timestamp)


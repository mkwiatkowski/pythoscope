from pythoscope.event import Event


__all__ = ['EqualAssertionLine', 'EqualAssertionStubLine',
           'GeneratorAssertionLine', 'RaisesAssertionLine',
           'CommentLine', 'SkipTestLine',
           'ModuleVariableReference', 'ObjectAttributeReference',
           'BindingChange', 'Assign']

class Line(Event):
    def __init__(self, timestamp):
        # We don't call Event.__init__ on purpose, we set our own timestamp.
        self.timestamp = timestamp

class EqualAssertionLine(Line):
    def __init__(self, expected, actual, timestamp):
        Line.__init__(self, timestamp)
        self.expected = expected
        self.actual = actual

    def __repr__(self):
        return "EqualAssertionLine(expected=%r, actual=%r)" % (self.expected, self.actual)

class EqualAssertionStubLine(Line):
    def __init__(self, actual, timestamp):
        Line.__init__(self, timestamp)
        self.actual = actual

class GeneratorAssertionLine(Line):
    def __init__(self, generator_call, timestamp):
        Line.__init__(self, timestamp)
        self.generator_call = generator_call

class RaisesAssertionLine(Line):
    def __init__(self, expected_exception, call, timestamp):
        Line.__init__(self, timestamp)
        self.expected_exception = expected_exception
        self.call = call

class CommentLine(Line):
    def __init__(self, comment, timestamp):
        Line.__init__(self, timestamp)
        self.comment = comment

class SkipTestLine(Line):
    def __init__(self, timestamp):
        Line.__init__(self, timestamp)

class ModuleVariableReference(Line):
    def __init__(self, module, name, timestamp):
        Line.__init__(self, timestamp)
        self.module = module
        self.name = name

class ObjectAttributeReference(Line):
    def __init__(self, obj, name, timestamp):
        Line.__init__(self, timestamp)
        self.obj = obj
        self.name = name

    def __repr__(self):
        return "ObjectAttributeReference(obj=%r, name=%r)" % (self.obj, self.name)

# This is a virtual line, not necessarily appearing in a test case. It is used
# to notify builder of a change in name bidning that happened under-the-hood,
# e.g. during a function call.
class BindingChange(Line):
    def __init__(self, name, obj, timestamp):
        Line.__init__(self, timestamp)
        self.name = name
        self.obj = obj

    def __repr__(self):
        return "%s(name=%r, obj=%r)" % (self.__class__.__name__, self.name, self.obj)

# Assignment statement.
class Assign(BindingChange):
    pass

from pythoscope.store import Function


class MissingSideEffectType(Exception):
    def __repr__(self):
        return "<MissingSideEffectType(%s)>" % self.args

def create_side_effect(klass, *args):
    try:
        subclass = globals()[klass]
        return subclass(*args)
    except KeyError:
        raise MissingSideEffectType(klass)

class SideEffect(object):
    def __init__(self, referenced_objects):
        self.referenced_objects = referenced_objects

class BuiltinMethodWithPositionArgsSideEffect(SideEffect):
    definition = None # set in a subclass

    def __init__(self, obj, *args):
        super(BuiltinMethodWithPositionArgsSideEffect, self).__init__([obj]+list(args))
        self.obj = obj
        self.args = args

    def args_mapping(self):
        return dict(zip(self.definition.args, self.args))

class ListAppend(BuiltinMethodWithPositionArgsSideEffect):
    definition = Function('append', ['object'])

class ListExtend(BuiltinMethodWithPositionArgsSideEffect):
    definition = Function('extend', ['iterable'])

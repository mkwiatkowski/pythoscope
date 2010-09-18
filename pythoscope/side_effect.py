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

class BuiltinMethodSideEffect(SideEffect):
    def __init__(self, obj, *args):
        super(BuiltinMethodSideEffect, self).__init__([obj]+list(args))
        self.obj = obj
        self.args = args

class ListAppend(BuiltinMethodSideEffect):
    definition = Function('append', ['object'])

class ListExtend(BuiltinMethodSideEffect):
    definition = Function('extend', ['iterable'])

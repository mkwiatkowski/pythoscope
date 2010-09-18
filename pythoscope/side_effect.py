from pythoscope.store import Function


class MissingSideEffectType(Exception):
    def __repr__(self):
        return "<MissingSideEffectType(%r)>" % self.args

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


known_side_effects = {
    (list, 'append') : ListAppend,
    (list, 'extend') : ListExtend,
}
def recognize_side_effect(klass, func_name):
    try:
        return known_side_effects[(klass, func_name)]
    except KeyError:
        raise MissingSideEffectType(klass, func_name)

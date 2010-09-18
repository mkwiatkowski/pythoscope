from pythoscope.store import Function


class MissingSideEffectType(Exception):
    def __repr__(self):
        return "<MissingSideEffectType(%r)>" % self.args

known_side_effects = {}
def register_side_effect_type(trigger, klass):
    if known_side_effects.has_key(trigger):
        raise ValueError("Side effect for trigger %r already registered by %r." %\
                             (trigger, known_side_effects[trigger]))
    known_side_effects[trigger] = klass

def recognize_side_effect(klass, func_name):
    try:
        return known_side_effects[(klass, func_name)]
    except KeyError:
        raise MissingSideEffectType(klass, func_name)

class MetaSideEffect(type):
    """This metaclass will register a side effect when a class is created.
    """
    def __init__(cls, *args, **kwds):
        super(MetaSideEffect, cls).__init__(*args, **kwds)
        if hasattr(cls, 'trigger'):
            register_side_effect_type(cls.trigger, cls)

class SideEffect(object):
    __metaclass__ = MetaSideEffect
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
    trigger = (list, 'append')
    definition = Function('append', ['object'])

class ListExtend(BuiltinMethodWithPositionArgsSideEffect):
    trigger = (list, 'extend')
    definition = Function('extend', ['iterable'])

class ListInsert(BuiltinMethodWithPositionArgsSideEffect):
    trigger = (list, 'insert')
    definition = Function('insert', ['index', 'object'])

class ListPop(BuiltinMethodWithPositionArgsSideEffect):
    trigger = (list, 'pop')
    definition = Function('pop', ['index'])

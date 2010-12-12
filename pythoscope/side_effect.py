from pythoscope.store import Function
from pythoscope.event import Event


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

class SideEffect(Event):
    __metaclass__ = MetaSideEffect
    def __init__(self, affected_objects, only_referenced_objects):
        super(SideEffect, self).__init__()
        self.affected_objects = affected_objects
        self.referenced_objects = affected_objects + only_referenced_objects

class GlobalVariableSideEffect(SideEffect):
    def get_full_name(self):
        return "%s.%s" % (self.module, self.name)

    def __repr__(self):
        return "%s(%r, %r, %r)" % (self.__class__.__name__, self.module, self.name, self.value)

class GlobalRead(GlobalVariableSideEffect):
    def __init__(self, module, name, value):
        super(GlobalRead, self).__init__([], [])
        self.module = module
        self.name = name
        self.value = value

class GlobalRebind(GlobalVariableSideEffect):
    def __init__(self, module, name, value):
        super(GlobalRebind, self).__init__([], []) # TODO: module's __dict__ is affected
        self.module = module
        self.name = name
        self.value = value

class BuiltinMethodWithPositionArgsSideEffect(SideEffect):
    definition = None # set in a subclass

    def __init__(self, obj, *args):
        super(BuiltinMethodWithPositionArgsSideEffect, self).__init__([obj], list(args))
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

class ListRemove(BuiltinMethodWithPositionArgsSideEffect):
    trigger = (list, 'remove')
    definition = Function('remove', ['value'])

class ListReverse(BuiltinMethodWithPositionArgsSideEffect):
    trigger = (list, 'reverse')
    definition = Function('reverse', [])

class ListSort(BuiltinMethodWithPositionArgsSideEffect):
    trigger = (list, 'sort')
    definition = Function('sort', [])

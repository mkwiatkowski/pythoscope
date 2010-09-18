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

class ListAppend(SideEffect):
    definition = Function('append', ['object'])
    def __init__(self, alist, element):
        super(ListAppend, self).__init__([alist, element])
        self.alist = alist
        self.element = element

class ListExtend(SideEffect):
    definition = Function('extend', ['iterable'])
    def __init__(self, alist, iterable):
        super(ListExtend, self).__init__([alist, iterable])
        self.alist = alist
        self.iterable = iterable

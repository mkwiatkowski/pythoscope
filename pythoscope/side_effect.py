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
    def __init__(self, alist, element):
        super(ListAppend, self).__init__([alist, element])
        self.alist = alist
        self.element = element

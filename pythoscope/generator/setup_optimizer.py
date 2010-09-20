from pythoscope.serializer import SequenceObject
from pythoscope.side_effect import ListAppend


class NonSerializingSequenceObject(SequenceObject):
    def __init__(self, contained_objects):
        super(NonSerializingSequenceObject, self).__init__([], lambda x:x)
        self.contained_objects = contained_objects

def optimize(dependencies):
    i = 0
    while i+1 < len(dependencies.all):
        e1 = dependencies.all[i]
        e2 = dependencies.all[i+1]
        # "x = [y..]" and "x.append(z)" is "x = [y..z]"
        if isinstance(e1, SequenceObject) and isinstance(e2, ListAppend) and e2.obj == e1:
            dependencies.replace_pair_with_event(e1, e2, NonSerializingSequenceObject(e1.contained_objects + list(e2.args)))
            continue
        i += 1

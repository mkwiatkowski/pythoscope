from pythoscope.generator.setup_and_teardown import Dependencies
from pythoscope.serializer import UnknownObject, SequenceObject
from pythoscope.side_effect import SideEffect
from pythoscope.store import FunctionCall

from assertions import *
from factories import create


def put_on_timeline(*objects):
    timestamp = 1
    for obj in objects:
        obj.timestamp = timestamp
        timestamp += 1

def create_parent_call_with_side_effects(call, side_effects):
    parent_call = create(FunctionCall)
    parent_call.add_subcall(call)
    map(parent_call.add_side_effect, side_effects)

class TestDependencies:
    def test_resolves_dependencies_between_side_effects_and_contained_objects(self):
        # Relations between objects have been summarized below.
        # +-------+                          +---+
        # |Parent |                      /-->|o1 |
        # | Call  |   +--------+   /-----    +---+
        # +-------+-->|  Call  |--------       +---+
        #    |        |        |--      \----->|o2 |
        #    |        +--------+  \---         +---+
        #    |                        \-   +---+     +---+
        #    |                          \->|o3 |     |o4 |
        #    |         +---+               +---+   ->+---+
        #    |         |o5 |<-          _/      _-/   _^
        #    \_        +---+ /         /  ___--/     /
        #      \__    +-----/---------/--/----------/---+
        #         \   |  +----+     +----+     +----+   |
        #          \->|  |se1 |     |se2 |     |se3 |   |
        #             |  +----+     +----+     +----+   |
        #             +---------------------------------+
        #
        obj1 = create(UnknownObject)
        obj2 = create(UnknownObject)
        obj3 = create(UnknownObject)
        call = create(FunctionCall, args={'a': obj1, 'b': obj2}, output=obj3)
        obj4 = create(UnknownObject)
        obj5 = create(UnknownObject)

        se1 = SideEffect([obj5])
        se2 = SideEffect([obj3, obj4])
        se3 = SideEffect([obj4])
        create_parent_call_with_side_effects(call, [se1, se2, se3])

        put_on_timeline(obj1, obj2, obj3, obj4, obj5, se1, se2, se3, call)

        assert_equal(Dependencies(call).sorted(), [obj1, obj2, obj3, obj4, se2, se3])

    def test_resolves_dependencies_contained_within_objects_referenced_by_side_effects(self):
        output = create(UnknownObject)
        seq = create(SequenceObject, obj=[1])
        obj = seq.contained_objects[0]
        call = create(FunctionCall, output=output)

        se = SideEffect([output, seq])
        create_parent_call_with_side_effects(call, [se])

        put_on_timeline(obj, seq, se, output, call)

        assert_equal(Dependencies(call).sorted(), [obj, seq, se, output])

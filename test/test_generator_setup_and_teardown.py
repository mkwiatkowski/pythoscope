from pythoscope.generator.setup_and_teardown import Dependencies, assign_names_and_setup, setup_for_side_effect
from pythoscope.serializer import UnknownObject, ImmutableObject, SequenceObject
from pythoscope.side_effect import SideEffect, ListAppend, ListExtend
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

class TestAssignNamesAndSetup:
    def test_generates_setup_for_list_with_append_and_extend(self):
        alist = create(SequenceObject)
        alist2 = create(SequenceObject)
        se = ListAppend(alist, create(ImmutableObject, obj=1))
        se2 = ListExtend(alist, alist2)

        call = create(FunctionCall, output=alist)
        create_parent_call_with_side_effects(call, [se, se2])

        put_on_timeline(alist, alist2, se, se2, call)

        assert_equal_strings("alist1 = []\nalist2 = []\nalist1.append(1)\nalist1.extend(alist2)\n",
                             assign_names_and_setup(call, {}))

class TestSetupForSideEffect:
    def test_generates_setup_for_list_append(self):
        alist = create(SequenceObject)
        se = ListAppend(alist, create(ImmutableObject, obj=1))
        assert_equal_strings("alist.append(1)\n", setup_for_side_effect(se, {alist: 'alist'}))

    def test_generates_setup_for_list_extend(self):
        alist = create(SequenceObject)
        alist2 = create(SequenceObject)
        se = ListExtend(alist, alist2)
        assert_equal_strings("alist.extend(alist2)\n",
                             setup_for_side_effect(se, {alist: 'alist', alist2: 'alist2'}))

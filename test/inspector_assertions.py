from pythoscope.serializer import MapObject, UnknownObject, SequenceObject,\
    BuiltinException

from assertions import assert_equal
from helper import EmptyProjectExecution


__all__ = ["assert_serialized", "assert_collection_of_serialized",
    "assert_call_arguments", "serialize_value"]


def assert_serialized(expected_unserialized, actual_serialized):
    assert_equal_serialized(serialize_value(expected_unserialized), actual_serialized)
def assert_collection_of_serialized(expected_collection, actual_collection):
    assert_equal_serialized(serialize_collection(expected_collection), actual_collection)
def assert_call_arguments(expected_args, actual_args):
    assert_equal_serialized(serialize_arguments(expected_args), actual_args)

def serialize_value(value):
    return EmptyProjectExecution().serialize(value)
def serialize_collection(collection):
    return map(serialize_value, collection)
def serialize_arguments(args):
    return EmptyProjectExecution().serialize_call_arguments(args)

def assert_equal_serialized(obj1, obj2):
    """Equal assertion that ignores UnknownObjects, SequenceObjects and
    MapObjects identity. For testing purposes only.
    """
    def unknown_object_eq(o1, o2):
        if not isinstance(o2, UnknownObject):
            return False
        return o1.partial_reconstructor == o2.partial_reconstructor
    def sequence_object_eq(o1, o2):
        if not isinstance(o2, SequenceObject):
            return False
        return o1.constructor_format == o2.constructor_format \
            and o1.contained_objects == o2.contained_objects
    def map_object_eq(o1, o2):
        if not isinstance(o2, MapObject):
            return False
        return o1.mapping == o2.mapping
    def builtin_exception_eq(o1, o2):
        if not isinstance(o2, BuiltinException):
            return False
        return o1.args == o2.args
    try:
        UnknownObject.__eq__ = unknown_object_eq
        SequenceObject.__eq__ = sequence_object_eq
        MapObject.__eq__ = map_object_eq
        BuiltinException.__eq__ = builtin_exception_eq
        assert_equal(obj1, obj2)
    finally:
        del UnknownObject.__eq__
        del SequenceObject.__eq__
        del MapObject.__eq__
        del BuiltinException.__eq__

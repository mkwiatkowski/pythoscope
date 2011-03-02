from pythoscope.serializer import get_partial_reconstructor

from assertions import *


class TestGetPartialReconstructor:
    def test_uses_name_of_the_class_for_instances_of_new_style_classes(self):
        class SomeClass(object):
            pass
        assert_equal("test.test_serializer.SomeClass",
            get_partial_reconstructor(SomeClass()))

    def test_uses_name_of_the_class_for_instances_of_old_style_classes(self):
        class SomeClass:
            pass
        assert_equal("test.test_serializer.SomeClass",
            get_partial_reconstructor(SomeClass()))

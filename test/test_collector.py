from nose.tools import assert_equal
from helper import assert_length

import pythoscope

new_style_class = """
class AClass(object):
    def amethod(self):
        pass
"""

old_style_class = """
class OldStyleClass:
    def amethod(self):
        pass
"""

class_without_methods = """
class ClassWithoutMethods(object):
    pass
"""

stand_alone_function = """
def a_function():
    pass
"""

inner_classes_and_function = """
def outer_function():
    def inner_function():
        pass
    class InnerClass(object):
        pass

class OuterClass(object):
    class AnotherInnerClass(object):
        pass
"""

class_with_methods = """
class ClassWithThreeMethods(object):
    def first_method(self):
        pass
    def second_method(self, x):
        pass
    def third_method(self, x, y):
        pass
"""

class TestCollector:
    def test_collects_information_about_top_level_classes(self):
        info = pythoscope.collect_information(new_style_class)

        assert_length(info.classes, 1)
        assert_equal("AClass", info.classes[0].name)

    def test_collects_information_about_top_level_functions(self):
        info = pythoscope.collect_information(stand_alone_function)

        assert_length(info.functions, 1)
        assert_equal("a_function", info.functions[0].name)

    def test_doesnt_count_methods_as_functions(self):
        info = pythoscope.collect_information(new_style_class)

        assert_length(info.functions, 0)

    def test_collects_information_about_old_style_classes(self):
        info = pythoscope.collect_information(old_style_class)

        assert_length(info.classes, 1)
        assert_equal("OldStyleClass", info.classes[0].name)

    def test_collects_information_about_classes_without_methods(self):
        info = pythoscope.collect_information(class_without_methods)

        assert_length(info.classes, 1)
        assert_equal("ClassWithoutMethods", info.classes[0].name)

    def test_ignores_inner_classes_and_functions(self):
        info = pythoscope.collect_information(inner_classes_and_function)

        assert_length(info.classes, 1)
        assert_equal("OuterClass", info.classes[0].name)
        assert_length(info.functions, 1)
        assert_equal("outer_function", info.functions[0].name)

    def test_collects_information_about_methods_of_a_class(self):
        info = pythoscope.collect_information(class_with_methods)

        assert_equal(["first_method", "second_method", "third_method"],
                     info.classes[0].methods)

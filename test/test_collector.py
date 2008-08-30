import sys

from nose.tools import assert_equal
from nose.exc import SkipTest
from helper import assert_length, assert_single_class, assert_single_function

from pythoscope.collector import collect_information_from_code,\
     collect_information_from_test_code
from pythoscope.astvisitor import regenerate

# Let nose know that those aren't test functions.
collect_information_from_test_code.__test__ = False

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

syntax_error = """
a b c d e f g
"""

indentation_error = """
  def answer():
    42
"""

definitions_inside_try_except = """
try:
    def inside_function(): pass
    class InsideClass(object): pass
except:
    pass
"""

definitions_inside_if = """
if True:
    def inside_function(): pass
    class InsideClass(object): pass
"""

definitions_inside_while = """
while True:
    def inside_function(): pass
    class InsideClass(object): pass
"""

definitions_inside_for = """
for x in range(1):
    def inside_function(): pass
    class InsideClass(object): pass
"""

definitions_inside_with = """
from __future__ import with_statement
with x:
    def inside_function(): pass
    class InsideClass(object): pass
"""

lambda_definition = """
lambda_function = lambda x: not x
"""

class_without_parents = """
class ClassWithoutParents:
    pass
"""

class_with_one_parent = """
class ClassWithOneParent(object):
    pass
"""

class_with_two_parents = """
class ClassWithTwoParents(Mother, Father):
    pass
"""

class_inheriting_from_unittest_testcase = """
class TestClass(unittest.TestCase):
    pass
"""

class_with_inner_class = """
class OuterClass(object):
    def __init__(self):
        pass
    def outer_class_method(self):
        pass
    class InnerClass(object):
        def __init__(self):
            pass
        def inner_class_method(self):
            pass
"""

two_test_classes = """import unittest

class FirstTestClass(unittest.TestCase):
    def test_this(self):
        pass
    def test_that(self):
        pass

class TestMore:
    def test_more(self):
        pass
"""

strange_test_code = "# Tests will be here someday"

nose_style_test_functions = """import nose

def test_this():
    pass

def test_that():
    pass
"""

class TestCollector:
    def test_collects_information_about_top_level_classes(self):
        info = collect_information_from_code(new_style_class)

        assert_single_class(info, "AClass")

    def test_collects_information_about_top_level_functions(self):
        info = collect_information_from_code(stand_alone_function)

        assert_single_function(info, "a_function")

    def test_doesnt_count_methods_as_functions(self):
        info = collect_information_from_code(new_style_class)

        assert_length(info.functions, 0)

    def test_collects_information_about_old_style_classes(self):
        info = collect_information_from_code(old_style_class)

        assert_single_class(info, "OldStyleClass")

    def test_collects_information_about_classes_without_methods(self):
        info = collect_information_from_code(class_without_methods)

        assert_single_class(info, "ClassWithoutMethods")

    def test_ignores_inner_classes_and_functions(self):
        info = collect_information_from_code(inner_classes_and_function)

        assert_single_class(info, "OuterClass")
        assert_single_function(info, "outer_function")

    def test_collects_information_about_methods_of_a_class(self):
        info = collect_information_from_code(class_with_methods)

        assert_equal(["first_method", "second_method", "third_method"],
                     info.classes[0].methods)

    def test_collector_handles_syntax_errors(self):
        info = collect_information_from_code(syntax_error)

        assert_length(info.errors, 1)

    def test_collector_handles_indentation_errors(self):
        info = collect_information_from_code(indentation_error)

        assert_length(info.errors, 1)

    def test_collects_information_about_functions_and_classes_inside_other_blocks(self):
        suite = [definitions_inside_try_except, definitions_inside_if,
                 definitions_inside_while, definitions_inside_for]

        for case in suite:
            info = collect_information_from_code(case)
            assert_single_class(info, "InsideClass")
            assert_single_function(info, "inside_function")

    def test_collects_information_about_functions_and_classes_inside_with(self):
        # With statement was introduced in Python 2.5, so skip this test for
        # earlier versions.
        if sys.version_info < (2, 5):
            raise SkipTest

        info = collect_information_from_code(definitions_inside_with)
        assert_single_class(info, "InsideClass")
        assert_single_function(info, "inside_function")

    def test_collects_information_about_functions_defined_using_lambda(self):
        info = collect_information_from_code(lambda_definition)

        assert_single_function(info, "lambda_function")

    def test_collects_information_about_class_bases(self):
        suite = [class_without_parents, class_with_one_parent, class_with_two_parents]
        expected_results = [[], ["object"], ["Mother", "Father"]]

        for case, expected in zip(suite, expected_results):
            info = collect_information_from_code(case)
            assert_equal(expected, info.classes[0].bases)

    def test_correctly_collects_information_about_bases_from_other_modules(self):
        info = collect_information_from_code(class_inheriting_from_unittest_testcase)

        assert_equal(["unittest.TestCase"], info.classes[0].bases)

    def test_ignores_existance_of_any_inner_class_methods(self):
        info = collect_information_from_code(class_with_inner_class)

        assert_single_class(info, "OuterClass")
        assert_equal(["__init__", "outer_class_method"], info.classes[0].methods)

    def test_collects_information_about_test_modules(self):
        info = collect_information_from_test_code(two_test_classes)

        assert_equal(["unittest"], info.imports)
        assert_equal(["FirstTestClass", "TestMore"],
                     map(lambda c: c.name, info.test_classes))
        assert_equal(["test_this", "test_that"],
                     map(lambda c: c.name, info.test_classes[0].methods))
        assert_equal(["test_more"],
                     map(lambda c: c.name, info.test_classes[1].methods))

    def test_recognizes_unrecognized_chunks_of_test_code(self):
        info = collect_information_from_test_code(strange_test_code)

        assert_equal(strange_test_code, regenerate(info.code))

    def test_recognizes_nose_style_test_code(self):
        info = collect_information_from_test_code(nose_style_test_functions)

        assert_equal(["nose"], info.imports)
        assert_equal(nose_style_test_functions, regenerate(info.code))
        assert_equal(None, info.main_snippet)

import sys

from nose.tools import assert_equal
from nose.exc import SkipTest
from helper import assert_length, assert_single_class, assert_single_function, \
     assert_equal_sets, EmptyProject

from pythoscope.inspector.static import inspect_code
from pythoscope.astvisitor import regenerate
from pythoscope.util import get_names


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

class_inheriting_from_some_other_module_class = """
class SomeClass(othermodule.Class):
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

application_module_with_test_class = """import os
import unittest

def fib(x):
    if x in [0,1]:
        return x
    else:
        return fib(x-2) + fib(x-1)

class TestFib(unittest.TestCase):
    def test_one(self):
        assert fib(1) == 1
    def test_two(self):
        assert fib(2) == 1
    def test_three(self):
        assert fib(3) == 2

if __name__ == '__main__':
    unittest.main()
"""

class TestStaticInspector:
    def _inspect_code(self, code):
        return inspect_code(EmptyProject(), "module.py", code)

    def test_inspects_top_level_classes(self):
        info = self._inspect_code(new_style_class)

        assert_single_class(info, "AClass")

    def test_inspects_top_level_functions(self):
        info = self._inspect_code(stand_alone_function)

        assert_single_function(info, "a_function")

    def test_doesnt_count_methods_as_functions(self):
        info = self._inspect_code(new_style_class)

        assert_length(info.functions, 0)

    def test_inspects_old_style_classes(self):
        info = self._inspect_code(old_style_class)

        assert_single_class(info, "OldStyleClass")

    def test_inspects_classes_without_methods(self):
        info = self._inspect_code(class_without_methods)

        assert_single_class(info, "ClassWithoutMethods")

    def test_ignores_inner_classes_and_functions(self):
        info = self._inspect_code(inner_classes_and_function)

        assert_single_class(info, "OuterClass")
        assert_single_function(info, "outer_function")

    def test_inspects_methods_of_a_class(self):
        info = self._inspect_code(class_with_methods)

        assert_equal(["first_method", "second_method", "third_method"],
                     get_names(info.classes[0].methods))

    def test_collector_handles_syntax_errors(self):
        info = self._inspect_code(syntax_error)

        assert_length(info.errors, 1)

    def test_collector_handles_indentation_errors(self):
        info = self._inspect_code(indentation_error)

        assert_length(info.errors, 1)

    def test_inspects_functions_and_classes_inside_other_blocks(self):
        suite = [definitions_inside_try_except, definitions_inside_if,
                 definitions_inside_while, definitions_inside_for]

        for case in suite:
            info = self._inspect_code(case)
            assert_single_class(info, "InsideClass")
            assert_single_function(info, "inside_function")

    def test_inspects_functions_and_classes_inside_with(self):
        # With statement was introduced in Python 2.5, so skip this test for
        # earlier versions.
        if sys.version_info < (2, 5):
            raise SkipTest

        info = self._inspect_code(definitions_inside_with)
        assert_single_class(info, "InsideClass")
        assert_single_function(info, "inside_function")

    def test_inspects_functions_defined_using_lambda(self):
        info = self._inspect_code(lambda_definition)

        assert_single_function(info, "lambda_function")

    def test_inspects_class_bases(self):
        suite = [class_without_parents, class_with_one_parent, class_with_two_parents]
        expected_results = [[], ["object"], ["Mother", "Father"]]

        for case, expected in zip(suite, expected_results):
            info = self._inspect_code(case)
            assert_equal(expected, info.classes[0].bases)

    def test_correctly_inspects_bases_from_other_modules(self):
        info = self._inspect_code(class_inheriting_from_some_other_module_class)

        assert_length(info.objects, 1)
        assert_equal(["othermodule.Class"], info.objects[0].bases)

    def test_ignores_existance_of_any_inner_class_methods(self):
        info = self._inspect_code(class_with_inner_class)

        assert_single_class(info, "OuterClass")
        assert_equal(["__init__", "outer_class_method"],
                     get_names(info.classes[0].methods))

    def test_inspects_test_modules(self):
        info = self._inspect_code(two_test_classes)

        assert_equal(["unittest"], info.imports)
        assert_equal(["FirstTestClass", "TestMore"],
                     get_names(info.test_classes))
        assert_equal(["test_this", "test_that"],
                     get_names(info.test_classes[0].test_cases))
        assert_equal(["test_more"],
                     get_names(info.test_classes[1].test_cases))

    def test_recognizes_unrecognized_chunks_of_test_code(self):
        info = self._inspect_code(strange_test_code)

        assert_equal(strange_test_code, regenerate(info.code))

    def test_recognizes_nose_style_test_code(self):
        info = self._inspect_code(nose_style_test_functions)

        assert_equal(["nose"], info.imports)
        assert_equal(nose_style_test_functions, regenerate(info.code))
        assert_equal(None, info.main_snippet)

    def test_inspects_test_classes_inside_application_modules(self):
        info = self._inspect_code(application_module_with_test_class)

        assert_equal_sets(["os", "unittest"], info.imports)
        assert_equal(application_module_with_test_class, regenerate(info.code))
        assert info.main_snippet is not None
        assert_equal(["TestFib"], get_names(info.test_classes))
        assert_equal(["fib"], get_names(info.functions))

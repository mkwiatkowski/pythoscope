import sys

from nose import SkipTest

from pythoscope.inspector.static import inspect_code
from pythoscope.astbuilder import regenerate
from pythoscope.store import code_of
from pythoscope.util import get_names

from assertions import *
from helper import EmptyProject


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

standard_generator_definition = """def gen(x):
    yield x
    yield x + 1
"""

function_returning_generator_object = """def fun():
    def gen():
        yield 1
    return gen()
"""

class_with_method_generator_definition = """class SomeClass(object):
    def method_generator(self):
        yield 2
"""

function_with_default_argument_value = """def nofun(to='day'):
    return 'home'
"""

function_with_one_argument = """def fun(arg):
    pass
"""

function_with_many_arguments = """def fun3(arg1, arg2, arg3):
    pass
"""

function_with_many_arguments_and_default_values = """def optfun(arg, opt1=123, opt2='abc'):
    pass
"""

function_with_positional_and_keyword_arguments = """def morefun(arg, *args, **kwds):
    pass
"""

functions_with_nested_arguments = """def nestfun((a, b), c):
    pass
def nestfun2(a, (b, c)):
    pass
def nestfun3(a, (b, c), d):
    pass
"""

class TestStaticInspector:
    def _inspect_code(self, code):
        return inspect_code(EmptyProject(), "module.py", code)

    def test_inspects_top_level_classes(self):
        module = self._inspect_code(new_style_class)

        assert_single_class(module, "AClass")

    def test_inspects_top_level_functions(self):
        module = self._inspect_code(stand_alone_function)

        assert_single_function(module, "a_function")

    def test_doesnt_count_methods_as_functions(self):
        module = self._inspect_code(new_style_class)

        assert_length(module.functions, 0)

    def test_inspects_old_style_classes(self):
        module = self._inspect_code(old_style_class)

        assert_single_class(module, "OldStyleClass")

    def test_inspects_classes_without_methods(self):
        module = self._inspect_code(class_without_methods)

        assert_single_class(module, "ClassWithoutMethods")

    def test_ignores_inner_classes_and_functions(self):
        module = self._inspect_code(inner_classes_and_function)

        assert_single_class(module, "OuterClass")
        assert_single_function(module, "outer_function")

    def test_inspects_methods_of_a_class(self):
        module = self._inspect_code(class_with_methods)

        assert_equal(["first_method", "second_method", "third_method"],
                     get_names(module.classes[0].methods))

    def test_collector_handles_syntax_errors(self):
        module = self._inspect_code(syntax_error)

        assert_length(module.errors, 1)

    def test_collector_handles_indentation_errors(self):
        module = self._inspect_code(indentation_error)

        assert_length(module.errors, 1)

    def test_inspects_functions_and_classes_inside_other_blocks(self):
        suite = [definitions_inside_try_except, definitions_inside_if,
                 definitions_inside_while, definitions_inside_for]

        for case in suite:
            module = self._inspect_code(case)
            assert_single_class(module, "InsideClass")
            assert_single_function(module, "inside_function")

    def test_inspects_functions_and_classes_inside_with(self):
        # With statement was introduced in Python 2.5, so skip this test for
        # earlier versions.
        if sys.version_info < (2, 5):
            raise SkipTest

        module = self._inspect_code(definitions_inside_with)
        assert_single_class(module, "InsideClass")
        assert_single_function(module, "inside_function")

    def test_inspects_functions_defined_using_lambda(self):
        module = self._inspect_code(lambda_definition)

        assert_single_function(module, "lambda_function")

    def test_inspects_class_bases(self):
        suite = [class_without_parents, class_with_one_parent, class_with_two_parents]
        expected_results = [[], ["object"], ["Mother", "Father"]]

        for case, expected in zip(suite, expected_results):
            module = self._inspect_code(case)
            assert_equal(expected, module.classes[0].bases)

    def test_correctly_inspects_bases_from_other_modules(self):
        module = self._inspect_code(class_inheriting_from_some_other_module_class)

        assert_length(module.objects, 1)
        assert_equal(["othermodule.Class"], module.objects[0].bases)

    def test_correctly_inspects_calculated_bases(self):
        class_with_namedtuple = "import collections\n\n" +\
        "class ClassWithNamedtuple(collections.namedtuple('Point', 'x y')):\n" +\
        "    pass\n"
        module = self._inspect_code(class_with_namedtuple)
        assert_single_class(module, "ClassWithNamedtuple")
        assert_equal(["collections.namedtuple('Point', 'x y')"], module.objects[0].bases)

    def test_ignores_existance_of_any_inner_class_methods(self):
        module = self._inspect_code(class_with_inner_class)

        assert_single_class(module, "OuterClass")
        assert_equal(["__init__", "outer_class_method"],
                     get_names(module.classes[0].methods))

    def test_inspects_test_modules(self):
        module = self._inspect_code(two_test_classes)

        assert_equal(["unittest"], module.imports)
        assert_equal(["FirstTestClass", "TestMore"],
                     get_names(module.test_classes))
        assert_equal(["test_this", "test_that"],
                     get_names(module.test_classes[0].test_cases))
        assert_equal(["test_more"],
                     get_names(module.test_classes[1].test_cases))

    def test_recognizes_unrecognized_chunks_of_test_code(self):
        module = self._inspect_code(strange_test_code)

        assert_equal(strange_test_code, module.get_content())

    def test_recognizes_nose_style_test_code(self):
        module = self._inspect_code(nose_style_test_functions)

        assert_equal(["nose"], module.imports)
        assert_equal(nose_style_test_functions, module.get_content())
        assert_equal(None, code_of(module, 'main_snippet'))

    def test_inspects_test_classes_inside_application_modules(self):
        module = self._inspect_code(application_module_with_test_class)

        assert_equal_sets(["os", "unittest"], module.imports)
        assert_equal(application_module_with_test_class, module.get_content())
        assert code_of(module, 'main_snippet') is not None
        assert_equal(["TestFib"], get_names(module.test_classes))
        assert_equal(["fib"], get_names(module.functions))

    def test_recognizes_generator_definitions(self):
        module = self._inspect_code(standard_generator_definition)

        assert_single_function(module, "gen")
        assert module.functions[0].is_generator

    def test_treats_functions_returning_generator_objects_as_functions(self):
        module = self._inspect_code(function_returning_generator_object)

        assert_single_function(module, "fun")
        assert not module.functions[0].is_generator

    def test_recognizes_generator_methods(self):
        module = self._inspect_code(class_with_method_generator_definition)

        method = module.classes[0].methods[0]
        assert method.is_generator
        assert_equal("method_generator", method.name)

    def test_handles_functions_without_arguments(self):
        module = self._inspect_code(stand_alone_function)

        assert_single_function(module, "a_function", args=[])

    def test_handles_functions_with_one_argument(self):
        module = self._inspect_code(function_with_one_argument)

        assert_single_function(module, "fun", args=['arg'])

    def test_handles_functions_with_many_arguments(self):
        module = self._inspect_code(function_with_many_arguments)

        assert_single_function(module, "fun3", args=['arg1', 'arg2', 'arg3'])

    def test_handles_functions_with_default_argument_values(self):
        module = self._inspect_code(function_with_default_argument_value)

        assert_single_function(module, "nofun", args=['to'])

    def test_handles_functions_with_many_arguments_and_default_values(self):
        module = self._inspect_code(function_with_many_arguments_and_default_values)

        assert_single_function(module, "optfun", args=['arg', 'opt1', 'opt2'])

    def test_handles_functions_with_positional_and_keyword_arguments(self):
        module = self._inspect_code(function_with_positional_and_keyword_arguments)

        assert_single_function(module, "morefun", args=['arg', '*args', '**kwds'])

    def test_handles_arguments_of_lambda_definitions(self):
        module = self._inspect_code(lambda_definition)

        assert_single_function(module, "lambda_function", args=['x'])

    def test_handles_functions_with_nested_arguments(self):
        info = self._inspect_code(functions_with_nested_arguments)

        assert_length(info.functions, 3)
        assert_function(info.functions[0], "nestfun", [('a', 'b'), 'c'])
        assert_function(info.functions[1], "nestfun2", ['a', ('b', 'c')])
        assert_function(info.functions[2], "nestfun3", ['a', ('b', 'c'), 'd'])

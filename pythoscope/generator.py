import os
import re

from astvisitor import EmptyCode, descend, parse, ASTVisitor
from store import Class, Function, TestClass, TestMethod, ModuleNotFound
from util import camelize, underscore, sorted


def constructor_as_string(object):
    """For a given object return a string representing a code that will
    construct it.

    >>> constructor_as_string(123)
    '123'
    >>> constructor_as_string('string')
    "'string'"
    """
    return repr(object)

def call_as_string(object, input):
    """Generate code for calling an object with given input.

    >>> call_as_string(Function('fun'), {'a': 1, 'b': 2})
    'fun(a=1, b=2)'
    >>> call_as_string(Function('capitalize'), {'str': 'string'})
    "capitalize(str='string')"
    """
    return "%s(%s)" % (object.name, ', '.join(["%s=%s" % (arg, constructor_as_string(value)) for arg, value in input.iteritems()]))

def object2id(object):
    """Convert object to string that can be used as an identifier.
    """
    return re.sub(r'\.|\!', '', re.sub(r'\s+', '_', str(object).strip()))

def call2testname(object, input, output):
    """Generate a test method name that describes given object call.

    >>> call2testname(Function('do_this'), {}, True)
    'test_do_this_returns_true'
    >>> call2testname(Function('square'), {'x': 7}, 49)
    'test_square_returns_49_for_7'
    >>> call2testname(Function('capitalize'), {'str': 'a word.'}, 'A word.')
    'test_capitalize_returns_A_word_for_a_word'

    Two or more arguments are mentioned by name.
        >>> call2testname(Function('ackermann'), {'m': 3, 'n': 2}, 29)
        'test_ackermann_returns_29_for_m_equal_3_and_n_equal_2'

    Will sort arguments alphabetically.
        >>> call2testname(Function('concat'), {'s1': 'Hello ', 's2': 'world!'}, 'Hello world!')
        'test_concat_returns_Hello_world_for_s1_equal_Hello_and_s2_equal_world'

    Always starts and ends a word with a letter or number.
        >>> call2testname(Function('strip'), {'n': 1, 's': '  A bit of whitespace  '}, ' A bit of whitespace ')
        'test_strip_returns_A_bit_of_whitespace_for_n_equal_1_and_s_equal_A_bit_of_whitespace'
    """
    if input:
        if len(input) == 1:
            arguments = object2id(input.values()[0])
        else:
            arguments = "_and_".join(["%s_equal_%s" % (arg, object2id(value)) for arg, value in sorted(input.iteritems())])
        call_description = "%s_for_%s" % (object2id(output), arguments)
    else:
        call_description = str(output).lower()
    return "test_%s_returns_%s" % (underscore(object.name), call_description)

def sorted_test_method_descriptions(descriptions):
    def get_name(desc):
        if isinstance(desc, tuple):
            return desc[0]
        return desc
    return sorted(descriptions, key=get_name)

def name2testname(name):
    if name[0].isupper():
        return "Test%s" % name
    return "test_%s" % name

class UnknownTemplate(Exception):
    def __init__(self, template):
        Exception.__init__(self, "Couldn't find template %r." % template)
        self.template = template

def localize_method_code(code, method_name):
    """Return part of the code tree that corresponds to the given method
    definition.
    """
    class LocalizeMethodVisitor(ASTVisitor):
        def __init__(self):
            ASTVisitor.__init__(self)
            self.method_body = None
        def visit_function(self, name, args, body):
            if name == method_name:
                self.method_body = body

    return descend(code.children, LocalizeMethodVisitor).method_body

class TestGenerator(object):
    imports = []
    main_snippet = EmptyCode()

    def from_template(cls, template):
        if template == 'unittest':
            return UnittestTestGenerator()
        elif template == 'nose':
            return NoseTestGenerator()
        else:
            raise UnknownTemplate(template)
    from_template = classmethod(from_template)

    def ensure_import(self, import_):
        if import_ not in self.imports:
            self.imports.append(import_)

    def add_tests_to_project(self, project, modnames, force=False):
        for modname in modnames:
            module = project[modname]
            self._add_tests_for_module(module, project, force)

    def _add_tests_for_module(self, module, project, force):
        for test_case in self._generate_test_cases(module):
            project.add_test_case(test_case, force)

    def _generate_test_cases(self, module):
        for object in module.testable_objects:
            test_case = self._generate_test_case(object, module)
            if test_case:
                yield test_case

    def _generate_test_method_descriptions(self, object, module):
        if isinstance(object, Function):
            # We have at least one call registered, so use it.
            if object.calls:
                for call in object.get_unique_calls():
                    yield (call2testname(object, call.input, call.output),
                           constructor_as_string(call.output),
                           call_as_string(object, call.input))
                    # We're calling the object, so we have to make sure it will
                    # be imported in the test
                    self.ensure_import((module.locator, object.name))
            # No calls were traced, so we're go for a single test stub.
            else:
                yield name2testname(underscore(object.name))
        elif isinstance(object, Class):
            for method in object.methods:
                if method.name == '__init__':
                    yield name2testname("object_initialization")
                elif not method.name.startswith('_'):
                    yield name2testname(method.name)

    def _generate_test_case(self, object, module):
        class_name = name2testname(camelize(object.name))
        method_descriptions = sorted_test_method_descriptions(self._generate_test_method_descriptions(object, module))

        # Don't generate empty test classes.
        if method_descriptions:
            test_body = self.create_test_class(class_name, method_descriptions)
            test_code = parse(test_body)
            def methoddesc2testmethod(method_description):
                if isinstance(method_description, tuple):
                    name = method_description[0]
                else:
                    name = method_description
                return TestMethod(name=name, code=localize_method_code(test_code, name))
            return TestClass(name=class_name,
                             code=test_code,
                             test_cases=map(methoddesc2testmethod, method_descriptions),
                             imports=self.imports,
                             main_snippet=self.main_snippet,
                             associated_modules=[module])

class UnittestTestGenerator(TestGenerator):
    main_snippet = parse("if __name__ == '__main__':\n    unittest.main()\n")

    def __init__(self):
        self.imports = ['unittest']

    def create_test_class(self, class_name, method_descriptions):
        result = "class %s(unittest.TestCase):\n" % class_name
        for method_description in method_descriptions:
            if isinstance(method_description, tuple):
                method_name, expected, actual = method_description
                result += "    def %s(self):\n" % method_name
                result += "        self.assertEqual(%s, %s)\n\n" % (expected, actual)
            else:
                method_name = method_description
                result += "    def %s(self):\n" % method_name
                result += "        assert False # TODO: implement your test here\n\n"
        return result

class NoseTestGenerator(TestGenerator):
    def __init__(self):
        self.imports = [('nose', 'SkipTest')]

    def create_test_class(self, class_name, method_descriptions):
        result = "class %s:\n" % class_name
        for method_description in method_descriptions:
            if isinstance(method_descriptions, tuple):
                method_name, expected, actual = method_description
                result += "    def %s(self):\n" % method_name
                result += "        assert_equal(%s, %s)\n\n" % (expected, actual)
                self.ensure_import(('nose.tools', 'assert_equal'))
            else:
                method_name = method_description
                result += "    def %s(self):\n" % method_name
                result += "        raise SkipTest # TODO: implement your test here\n\n"
        return result

def add_tests_to_project(project, modnames, template, force=False):
    generator = TestGenerator.from_template(template)
    generator.add_tests_to_project(project, modnames, force)

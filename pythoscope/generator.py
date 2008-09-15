import os
import re

from astvisitor import EmptyCode, descend, parse, ASTVisitor
from store import Class, Function, TestClass, TestMethod, ModuleNotFound, \
     LiveObject, MethodCall, Method
from util import camelize, underscore, sorted


def constructor_as_string(object):
    """For a given object return a string representing a code that will
    construct it.

    >>> constructor_as_string(123)
    '123'
    >>> constructor_as_string('string')
    "'string'"
    >>> obj = LiveObject(None, Class('SomeClass'), None)
    >>> constructor_as_string(obj)
    'SomeClass()'
    >>> obj.add_call(MethodCall(Method('__init__'), {'arg': 'whatever'}, None))
    >>> constructor_as_string(obj)
    "SomeClass(arg='whatever')"
    """
    if isinstance(object, LiveObject):
        args = {}
        # Look for __init__ call and base the constructor on that.
        init_call = object.get_init_call()
        if init_call:
            args = init_call.input
        return call_as_string(object.klass.name, args)
    return repr(object)

def call_as_string(object_name, input):
    """Generate code for calling an object with given input.

    >>> call_as_string('fun', {'a': 1, 'b': 2})
    'fun(a=1, b=2)'
    >>> call_as_string('capitalize', {'str': 'string'})
    "capitalize(str='string')"
    """
    return "%s(%s)" % (object_name, ', '.join(["%s=%s" % (arg, constructor_as_string(value)) for arg, value in input.iteritems()]))

def object2id(object):
    """Convert object to string that can be used as an identifier.
    """
    if object is True:
        return 'true'
    elif object is False:
        return 'false'
    return re.sub(r'[^a-zA-Z0-9_]', '', re.sub(r'\s+', '_', str(object).strip()))

def exception2id(exception):
    """Convert given exception class into a string that can be used as an
    identifier,
    """
    return underscore(exception.__name__)

def input_as_string(input):
    """Generate an underscored description of given input arguments.

    >>> input_as_string({})
    ''
    >>> input_as_string({'x': 7, 'y': 13})
    'x_equal_7_and_y_equal_13'
    """
    if len(input) == 1:
        return object2id(input.values()[0])
    return "_and_".join(["%s_equal_%s" % (arg, object2id(value))
                         for arg, value in sorted(input.iteritems())])

def call2testname(object_name, input, output):
    """Generate a test method name that describes given object call.

    >>> call2testname('do_this', {}, True)
    'test_do_this_returns_true'
    >>> call2testname('compute', {}, 'whatever you say')
    'test_compute_returns_whatever_you_say'
    >>> call2testname('square', {'x': 7}, 49)
    'test_square_returns_49_for_7'
    >>> call2testname('capitalize', {'str': 'a word.'}, 'A word.')
    'test_capitalize_returns_A_word_for_a_word'

    Two or more arguments are mentioned by name.
        >>> call2testname('ackermann', {'m': 3, 'n': 2}, 29)
        'test_ackermann_returns_29_for_m_equal_3_and_n_equal_2'

    Will sort arguments alphabetically.
        >>> call2testname('concat', {'s1': 'Hello ', 's2': 'world!'}, 'Hello world!')
        'test_concat_returns_Hello_world_for_s1_equal_Hello_and_s2_equal_world'

    Always starts and ends a word with a letter or number.
        >>> call2testname('strip', {'n': 1, 's': '  A bit of whitespace  '}, ' A bit of whitespace ')
        'test_strip_returns_A_bit_of_whitespace_for_n_equal_1_and_s_equal_A_bit_of_whitespace'
    """
    if input:
        call_description = "%s_for_%s" % (object2id(output), input_as_string(input))
    else:
        call_description = object2id(output)
    return "test_%s_returns_%s" % (underscore(object_name), call_description)

def exccall2testname(object_name, input, exception):
    """Generate a test method name that describes given object call raising
    an exception.

    >>> exccall2testname('do_this', {}, Exception)
    'test_do_this_raises_exception'
    >>> exccall2testname('square', {'x': 'a string'}, TypeError)
    'test_square_raises_type_error_for_a_string'
    """
    if input:
        call_description = "%s_for_%s" % (exception2id(exception), input_as_string(input))
    else:
        call_description = exception2id(exception)
    return "test_%s_raises_%s" % (underscore(object_name), call_description)

def sorted_test_method_descriptions(descriptions):
    return sorted(descriptions, key=lambda md: md.name)

def name2testname(name):
    if name[0].isupper():
        return "Test%s" % name
    return "test_%s" % name

def in_lambda(string):
    return "lambda: %s" % string

def should_ignore_method(method):
    return method.name.startswith('_') and method.name != "__init__"

def method_descriptions_from_function(function):
    for call in function.get_unique_calls():
        if call.raised_exception():
            name = exccall2testname(function.name, call.input, call.exception)
            assertions = [('raises', call.exception.__name__,
                           in_lambda(call_as_string(function.name, call.input)))]
        else:
            name = call2testname(function.name, call.input, call.output)
            assertions = [('equal', constructor_as_string(call.output),
                           call_as_string(function.name, call.input))]
        yield TestMethodDescription(name, assertions)

def method_description_from_live_object(live_object):
    external_calls = live_object.get_external_calls()
    init_call = live_object.get_init_call()

    if len(external_calls) == 0 and init_call:
        test_name = "test_creation_with_%s" % input_as_string(init_call.input)
        if init_call.raised_exception():
            test_name += "_raises_%s" % exception2id(init_call.exception)
    elif len(external_calls) == 1:
        call = external_calls[0]
        if call.raised_exception():
            test_name = exccall2testname(call.callable.name, call.input, call.exception)
        else:
            test_name = call2testname(call.callable.name, call.input, call.output)
        if init_call:
            test_name += "_after_creation_with_%s" % input_as_string(init_call.input)
    else:
        # TODO: come up with a nicer name for methods with more than one call.
        test_name = "%s_%s" % (underscore(live_object.klass.name), live_object.id)

    # Before we call the method, we have to construct an object.
    local_name = underscore(live_object.klass.name)

    assertions = []

    # If the constructor raised an exception, object creation should be an assertion.
    if init_call and init_call.raised_exception():
        setup = ""
        assertions.append(('raises', init_call.exception.__name__,
                           in_lambda(constructor_as_string(live_object))))
    else:
        setup = "%s = %s\n" % (local_name, constructor_as_string(live_object))

    if len(external_calls) == 0 and init_call:
        assertions.append(('comment', "# Make sure it doesn't raise any exceptions."))
    for call in external_calls:
        name = "%s.%s" % (local_name, call.callable.name)
        if call.raised_exception():
            assertions.append(('raises', call.exception.__name__,
                               in_lambda(call_as_string(name, call.input))))
        else:
            assertions.append(('equal', constructor_as_string(call.output),
                               call_as_string(name, call.input)))

    return TestMethodDescription(test_name, assertions, setup)

class UnknownTemplate(Exception):
    def __init__(self, template):
        Exception.__init__(self, "Couldn't find template %r." % template)
        self.template = template

def find_method_code(code, method_name):
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

class TestMethodDescription(object):
    # Assertions should be tuples (type, attributes...), where type is a string
    # denoting a type of an assertion, e.g. 'equal' is an equality assertion.
    #
    # During test generation assertion attributes are passed to the corresponding
    # TestGenerator method as arguments. E.g. assertion of type 'equal' invokes
    # 'equal_assertion' method of the TestGenerator.
    def __init__(self, name, assertions=[], setup=""):
        self.name = name
        self.assertions = assertions
        self.setup = setup

class TestGenerator(object):
    main_snippet = EmptyCode()

    def from_template(cls, template):
        if template == 'unittest':
            return UnittestTestGenerator()
        elif template == 'nose':
            return NoseTestGenerator()
        else:
            raise UnknownTemplate(template)
    from_template = classmethod(from_template)

    def __init__(self):
        self.imports = []

    def ensure_import(self, import_):
        if import_ not in self.imports:
            self.imports.append(import_)

    def add_tests_to_project(self, project, modnames, force=False):
        for modname in modnames:
            module = project[modname]
            self._add_tests_for_module(module, project, force)

    def create_test_class(self, class_name, method_descriptions):
        result = "%s\n" % (self.test_class_header(class_name))
        for method_description in method_descriptions:
            if method_description.assertions:
                result += "    def %s(self):\n" % method_description.name
                result += "        " + method_description.setup
                for assertion in method_description.assertions:
                    apply_template = getattr(self, "%s_assertion" % assertion[0])
                    result += "        %s\n" % apply_template(*assertion[1:])
                result += "\n"
            else:
                result += "    def %s(self):\n" % method_description.name
                result += "        %s\n\n" % self.missing_assertion()
        return result

    def comment_assertion(self, comment):
        return comment

    def _add_tests_for_module(self, module, project, force):
        for test_case in self._generate_test_cases(module):
            project.add_test_case(test_case, force)

    def _generate_test_cases(self, module):
        for object in module.testable_objects:
            test_case = self._generate_test_case(object, module)
            if test_case:
                yield test_case

    def _generate_test_case(self, object, module):
        class_name = name2testname(camelize(object.name))
        method_descriptions = sorted_test_method_descriptions(self._generate_test_method_descriptions(object, module))

        # Don't generate empty test classes.
        if method_descriptions:
            test_body = self.create_test_class(class_name, method_descriptions)
            test_code = parse(test_body)
            def methoddesc2testmethod(method_description):
                name = method_description.name
                return TestMethod(name=name, code=find_method_code(test_code, name))
            return TestClass(name=class_name,
                             code=test_code,
                             test_cases=map(methoddesc2testmethod, method_descriptions),
                             imports=self.imports,
                             main_snippet=self.main_snippet,
                             associated_modules=[module])

    def _generate_test_method_descriptions(self, object, module):
        if isinstance(object, Function):
            return self._generate_test_method_descriptions_for_function(object, module)
        elif isinstance(object, Class):
            return self._generate_test_method_descriptions_for_class(object, module)

    def _generate_test_method_descriptions_for_function(self, function, module):
        if function.calls:
            # We're calling the function, so we have to make sure it will
            # be imported in the test
            self.ensure_import((module.locator, function.name))

            # We have at least one call registered, so use it.
            return method_descriptions_from_function(function)
        else:
            # No calls were traced, so we're go for a single test stub.
            return [TestMethodDescription(name2testname(underscore(function.name)))]

    def _generate_test_method_descriptions_for_class(self, klass, module):
        if klass.live_objects:
            # We're calling the method, so we have to make sure its class
            # will be imported in the test
            self.ensure_import((module.locator, klass.name))

        for live_object in klass.live_objects.values():
            yield method_description_from_live_object(live_object)

        # No calls were traced for those methods, so we'll go for simple test stubs.
        for method in klass.get_untraced_methods():
            if not should_ignore_method(method):
                yield self._generate_test_method_description_for_method(method)

    def _generate_test_method_description_for_method(self, method):
        if method.name == '__init__':
            name = "object_initialization"
        else:
            name = method.name
        return TestMethodDescription(name2testname(name))

class UnittestTestGenerator(TestGenerator):
    main_snippet = parse("if __name__ == '__main__':\n    unittest.main()\n")

    def test_class_header(self, name):
        self.ensure_import('unittest')
        return "class %s(unittest.TestCase):" % name

    def equal_assertion(self, expected, actual):
        return "self.assertEqual(%s, %s)" % (expected, actual)

    def raises_assertion(self, exception, code):
        return "self.assertRaises(%s, %s)" % (exception, code)

    def missing_assertion(self):
        return "assert False # TODO: implement your test here"

class NoseTestGenerator(TestGenerator):
    def test_class_header(self, name):
        return "class %s:" % name

    def equal_assertion(self, expected, actual):
        self.ensure_import(('nose.tools', 'assert_equal'))
        return "assert_equal(%s, %s)" % (expected, actual)

    def raises_assertion(self, exception, code):
        self.ensure_import(('nose.tools', 'assert_raises'))
        return "assert_raises(%s, %s)" % (exception, code)

    def missing_assertion(self):
        self.ensure_import(('nose', 'SkipTest'))
        return "raise SkipTest # TODO: implement your test here"

def add_tests_to_project(project, modnames, template, force=False):
    generator = TestGenerator.from_template(template)
    generator.add_tests_to_project(project, modnames, force)

import os
import re
import types

from astvisitor import EmptyCode, descend, parse, ASTVisitor
from store import Class, Function, TestClass, TestMethod, ModuleNotFound, \
     LiveObject, MethodCall, Method, Value, Type, Repr, Project, PointOfEntry
from util import RePatternType, camelize, underscore, sorted, \
     regexp_flags_as_string, groupby


class ValueNeeded(Exception):
    pass

# :: ObjectWrapper -> type
def unwrap_type(object):
    """Get a type from given wrapped object.
    """
    if isinstance(object, Value):
        return object.value.__class__
    elif isinstance(object, Type):
        return object.type
    else:
        raise ValueNeeded()

# :: ObjectWrapper -> string
def type_as_string(object):
    """Return a most common representation of the wrapped object type.

    >>> type_as_string(Type([]))
    'list'
    >>> type_as_string(Type({}))
    'dict'
    >>> type_as_string(Type(lambda: None))
    'types.FunctionType'
    """
    mapping = {
        list: 'list',
        dict: 'dict',
        tuple: 'tuple',
        types.FunctionType: 'types.FunctionType'
    }
    try:
        return mapping[unwrap_type(object)]
    except KeyError:
        raise ValueNeeded()

# :: ObjectWrapper -> string
def exception_as_string(exception):
    """Return a name of this wrapped exception class.

    >>> exception_as_string(Value(TypeError()))
    'TypeError'
    >>> exception_as_string(Type(TypeError()))
    'TypeError'
    """
    return unwrap_type(exception).__name__

class CallString(str):
    """A string that holds information on the function/method call it
    represents.

    `uncomplete` attribute denotes whether it is a complete call
    or just a template.

    `imports` is a list of imports that this call requires.
    """
    def __new__(cls, string, uncomplete=False, imports=[]):
        call_string = str.__new__(cls, string)
        call_string.uncomplete = uncomplete
        call_string.imports = imports
        return call_string

# :: object -> CallString
def standard_constructor_as_string(object):
    """For a given Python object return a string representing a code that will
    construct it.

    >>> standard_constructor_as_string(re.compile('abcd'))
    "re.compile('abcd')"
    >>> standard_constructor_as_string(re.compile('abcd', re.I | re.M))
    "re.compile('abcd', re.IGNORECASE | re.MULTILINE)"
    """
    if isinstance(object, RePatternType):
        flags = regexp_flags_as_string(object.flags)
        if flags:
            return CallString('re.compile(%r, %s)' % (object.pattern, flags), imports=['re'])
        else:
            return CallString('re.compile(%r)' % object.pattern, imports=['re'])
    else:
        # This may not always be right, but it's worth a try.
        return CallString(repr(object))

# :: ObjectWrapper | LiveObject -> CallString
def constructor_as_string(object):
    """For a given object (either ObjectWrapper or a LiveObject instance) return
    a string representing a code that will construct it.

    >>> constructor_as_string(Value(123))
    '123'
    >>> constructor_as_string(Value('string'))
    "'string'"
    >>> obj = LiveObject(None, Class('SomeClass'), PointOfEntry(Project('.'), 'poe'))
    >>> constructor_as_string(obj)
    'SomeClass()'
    >>> obj.add_call(MethodCall(Method('__init__'), {'arg': Value('whatever')}, None))
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
    elif isinstance(object, Value):
        return standard_constructor_as_string(object.value)
    elif isinstance(object, Type):
        return CallString("<TODO: %s>" % object.type.__name__, uncomplete=True)
    elif isinstance(object, Repr):
        return CallString("<TODO: %s>" % object.repr, uncomplete=True)
    else:
        raise TypeError("constructor_as_string expected ObjectWrapper or LiveObject object at input, not %s" % object)

# :: (string, dict) -> CallString
def call_as_string(object_name, input):
    """Generate code for calling an object with given input.

    >>> call_as_string('fun', {'a': Value(1), 'b': Value(2)})
    'fun(a=1, b=2)'
    >>> call_as_string('capitalize', {'str': Value('string')})
    "capitalize(str='string')"
    >>> result = call_as_string('map', {'f': Type(lambda x: 42), 'L': Value([1,2,3])})
    >>> result
    'map(L=[1, 2, 3], f=<TODO: function>)'
    >>> result.uncomplete
    True
    """
    arguments = []
    uncomplete = False
    imports = set()
    for arg, value in input.iteritems():
        constructor = constructor_as_string(value)
        uncomplete = uncomplete or constructor.uncomplete
        imports.update(constructor.imports)
        arguments.append("%s=%s" % (arg, constructor))
    return CallString("%s(%s)" % (object_name, ', '.join(arguments)),
                      uncomplete=uncomplete, imports=imports)

# :: string -> string
def string2id(string):
    """Remove from string all characters that cannot be used in an identifier.
    """
    return re.sub(r'[^a-zA-Z0-9_]', '', re.sub(r'\s+', '_', string.strip()))

def object2id(object):
    """Convert object to string that can be used as an identifier.
    """
    if isinstance(object, Value):
        if object.value is True:
            return 'true'
        elif object.value is False:
            return 'false'
        elif isinstance(object.value, Exception):
            return underscore(exception_as_string(object))
        elif isinstance(object.value, RePatternType):
            return "%s_pattern" % string2id(object.value.pattern)
        return string2id(str(object.value))
    elif isinstance(object, Type):
        return underscore(object.type.__name__)
    elif isinstance(object, Repr):
        return string2id(object.repr)
    else:
        raise TypeError("object2id() should be called with a ObjectWrapper argument, not %s" % object)

def input_as_string(input):
    """Generate an underscored description of given input arguments.

    >>> input_as_string({})
    ''
    >>> input_as_string({'x': Value(7), 'y': Value(13)})
    'x_equal_7_and_y_equal_13'
    """
    if len(input) == 1:
        return object2id(input.values()[0])
    return "_and_".join(["%s_equal_%s" % (arg, object2id(value))
                         for arg, value in sorted(input.iteritems())])

def call2testname(object_name, input, output):
    """Generate a test method name that describes given object call.

    >>> call2testname('do_this', {}, Value(True))
    'test_do_this_returns_true'
    >>> call2testname('compute', {}, Value('whatever you say'))
    'test_compute_returns_whatever_you_say'
    >>> call2testname('square', {'x': Value(7)}, Value(49))
    'test_square_returns_49_for_7'
    >>> call2testname('capitalize', {'str': Value('a word.')}, Value('A word.'))
    'test_capitalize_returns_A_word_for_a_word'

    Two or more arguments are mentioned by name.
        >>> call2testname('ackermann', {'m': Value(3), 'n': Value(2)}, Value(29))
        'test_ackermann_returns_29_for_m_equal_3_and_n_equal_2'

    Will sort arguments alphabetically.
        >>> call2testname('concat', {'s1': Value('Hello '), 's2': Value('world!')}, Value('Hello world!'))
        'test_concat_returns_Hello_world_for_s1_equal_Hello_and_s2_equal_world'

    Always starts and ends a word with a letter or number.
        >>> call2testname('strip', {'n': Value(1), 's': Value('  A bit of whitespace  ')}, Value(' A bit of whitespace '))
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

    >>> exccall2testname('do_this', {}, Type(Exception()))
    'test_do_this_raises_exception'
    >>> exccall2testname('square', {'x': Value('a string')}, Type(TypeError()))
    'test_square_raises_type_error_for_a_string'
    """
    if input:
        call_description = "%s_for_%s" % (object2id(exception), input_as_string(input))
    else:
        call_description = object2id(exception)
    return "test_%s_raises_%s" % (underscore(object_name), call_description)

def sorted_test_method_descriptions(descriptions):
    return sorted(descriptions, key=lambda md: md.name)

def name2testname(name):
    if name[0].isupper():
        return "Test%s" % name
    return "test_%s" % name

def in_lambda(string):
    return "lambda: %s" % string

def type_of(string):
    return "type(%s)" % string

def should_ignore_method(method):
    return method.name.startswith('_') and method.name != "__init__"

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

    def contains_code(self):
        return self._has_complete_setup() or self._get_code_assertions()

    def _get_code_assertions(self):
        return [a for a in self.assertions if a[0] in ['equal', 'raises']]

    def _has_complete_setup(self):
        return self.setup and not self.setup.startswith("#")

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
            module = project.find_module_by_full_path(modname)
            self._add_tests_for_module(module, project, force)

    def create_test_class(self, class_name, method_descriptions):
        result = "%s\n" % (self.test_class_header(class_name))
        for method_description in method_descriptions:
            if method_description.assertions:
                result += "    def %s(self):\n" % method_description.name
                if method_description.setup:
                    result += "        " + method_description.setup
                for assertion in method_description.assertions:
                    apply_template = getattr(self, "%s_assertion" % assertion[0])
                    result += "        %s\n" % apply_template(*assertion[1:])
                # We need at least one statement in a method to be syntatically correct.
                if not method_description.contains_code():
                    result += "        pass\n"
                result += "\n"
            else:
                result += "    def %s(self):\n" % method_description.name
                result += "        %s\n\n" % self.missing_assertion()
        return result

    def comment_assertion(self, comment):
        return comment

    def equal_stub_assertion(self, expected, actual):
        return "# %s" % self.equal_assertion(expected, actual)

    def raises_stub_assertion(self, exception, code):
        return "# %s" % self.raises_assertion(exception, code)

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
            return self._method_descriptions_from_function(function)
        else:
            # No calls were traced, so we're go for a single test stub.
            return [TestMethodDescription(name2testname(underscore(function.name)))]

    def _generate_test_method_descriptions_for_class(self, klass, module):
        if klass.live_objects:
            # We're calling the method, so we have to make sure its class
            # will be imported in the test.
            self.ensure_import((module.locator, klass.name))

        for live_object in klass.live_objects.values():
            yield self._method_description_from_live_object(live_object)

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

    def _method_descriptions_from_function(self, function):
        for call in function.get_unique_calls():
            assertions = [self._create_assertion(function.name, call)]

            if call.raised_exception():
                name = exccall2testname(function.name, call.input, call.exception)
            else:
                name = call2testname(function.name, call.input, call.output)

            yield TestMethodDescription(name, assertions)

    def _method_description_from_live_object(self, live_object):
        init_call = live_object.get_init_call()
        external_calls = live_object.get_external_calls()
        local_name = underscore(live_object.klass.name)
        constructor = constructor_as_string(live_object)
        stub_all = constructor.uncomplete

        def test_name():
            if len(external_calls) == 0 and init_call:
                test_name = "test_creation_with_%s" % input_as_string(init_call.input)
                if init_call.raised_exception():
                    test_name += "_raises_%s" % object2id(init_call.exception)
            else:
                if len(external_calls) == 1:
                    call = external_calls[0]
                    if call.raised_exception():
                        test_name = exccall2testname(call.callable.name, call.input, call.exception)
                    else:
                        test_name = call2testname(call.callable.name, call.input, call.output)
                # Methods with more than one external call use more brief
                # descriptions that don't include inputs and outputs.
                else:
                    methods = []
                    for method, icalls in groupby(sorted([call.callable.name for call in external_calls])):
                        calls = list(icalls)
                        if len(calls) == 1:
                            methods.append(method)
                        else:
                            methods.append("%s_%d_times" % (method, len(calls)))
                    test_name = "test_%s" % '_and_'.join(methods)
                if init_call:
                    test_name += "_after_creation_with_%s" % input_as_string(init_call.input)
            return test_name

        def assertions():
            if init_call and len(external_calls) == 0:
                # If the constructor raised an exception, object creation should be an assertion.
                if init_call.raised_exception():
                    yield self._create_assertion(live_object.klass.name, init_call, stub_all)
                else:
                    yield(('comment', "# Make sure it doesn't raise any exceptions."))
    
            for call in external_calls:
                name = "%s.%s" % (local_name, call.callable.name)
                yield(self._create_assertion(name, call, stub_all))

        def setup():
            if init_call and init_call.raised_exception():
                return ""
            else:
                setup = "%s = %s\n" % (local_name, constructor)
                # Comment out the constructor if it isn't complete.
                if stub_all:
                    setup = "# %s" % setup
                return setup

        return TestMethodDescription(test_name(), list(assertions()), setup())

    def _create_assertion(self, name, call, stub=False):
        """Create a new assertion based on a given call and a name provided
        for it.

        Generated assertion will be a stub if input of a call cannot be
        constructed or if stub argument is True.
        """
        input = call_as_string(name, call.input)

        for import_ in input.imports:
            self.ensure_import(import_)

        if call.raised_exception():
            if input.uncomplete or stub:
                assertion_type = 'raises_stub'
            else:
                assertion_type = 'raises'
            return (assertion_type,
                    exception_as_string(call.exception),
                    in_lambda(input))
        else:
            if input.uncomplete or stub:
                assertion_type = 'equal_stub'
            else:
                assertion_type = 'equal'

            if call.output.can_be_constructed:
                return (assertion_type, constructor_as_string(call.output), input)
            else:
                # If we can't test for real values, let's at least test for the right type.
                output_type = type_as_string(call.output)
                self.ensure_import('types')
                return (assertion_type, output_type, type_of(input))

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

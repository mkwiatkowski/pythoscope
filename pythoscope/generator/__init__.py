from pythoscope.astvisitor import descend, ASTVisitor
from pythoscope.astbuilder import parse_fragment, EmptyCode
from pythoscope.logger import log
from pythoscope.generator.adder import add_test_case_to_project
from pythoscope.generator.selector import testable_objects, testable_calls
from pythoscope.generator.side_effect_assertions import UnittestTemplate,\
    NoseTemplate, generate_test_case
from pythoscope.serializer import SerializedObject, ImmutableObject,\
    UnknownObject
from pythoscope.store import Class, Function, TestClass, TestMethod,\
    ModuleNotFound, GeneratorObject
from pythoscope.compat import all, sorted
from pythoscope.util import assert_argument_type, camelize, counted, \
    key_for_value, pluralize, underscore


# :: GeneratorObject -> SerializedObject | None
def generator_object_exception(gobject):
    assert_argument_type(gobject, GeneratorObject)
    for call in gobject.calls:
        if call.raised_exception():
            return call.exception

# :: GeneratorObject -> [SerializedObject]
def generator_object_yields(gobject):
    assert_argument_type(gobject, GeneratorObject)
    return [c.output for c in gobject.calls]

# :: SerializedObject -> string
def object2id(obj):
    """Convert object to string that can be used as an identifier.

    Generator objects that were never activated get a generic name...
        >>> def producer():
        ...     yield 1
        >>> gobject = GeneratorObject(producer())
        >>> object2id(gobject)
        'generator'

    ...but if we have a matching definition, the name is based on it.
        >>> definition = Function('producer', is_generator=True)
        >>> gobject.activate(definition, {}, definition)
        >>> object2id(gobject)
        'producer_instance'

    Accepts only SerializedObjects as arguments.
        >>> object2id(42)
        Traceback (most recent call last):
          ...
        TypeError: object2id() should be called with a SerializedObject argument, not 42
    """
    assert_argument_type(obj, SerializedObject)
    if isinstance(obj, GeneratorObject) and obj.is_activated():
        return "%s_instance" % obj.definition.name
    else:
        return obj.human_readable_id

def objects_list_to_id(objects):
    """Convert given list of objects into string that can be used as an
    identifier.
    """
    if not objects:
        return 'nothing'
    return '_then_'.join(map(object2id, objects))

def arguments_as_string(args, always_use_argnames=False):
    """Generate an underscored description of given arguments.

    >>> arguments_as_string({})
    ''
    >>> arguments_as_string({'x': ImmutableObject(7), 'y': ImmutableObject(13)})
    'x_equal_7_and_y_equal_13'

    Usually doesn't use argument names when there's only a single argument:
        >>> arguments_as_string({'x': ImmutableObject(1)})
        '1'

    but will use them if forced to:
        >>> arguments_as_string({'x': ImmutableObject(1)}, always_use_argnames=True)
        'x_equal_1'
    """
    if not always_use_argnames and len(args) == 1:
        return object2id(args.values()[0])
    return "_and_".join(["%s_equal_%s" % (arg, object2id(value))
                         for arg, value in sorted(args.iteritems())])

def objcall2testname(object_name, args, output):
    """Generate a test method name that describes given object call.

    >>> from test.helper import make_fresh_serialize
    >>> serialize = make_fresh_serialize()

    >>> objcall2testname('do_this', {}, serialize(True))
    'test_do_this_returns_true'
    >>> objcall2testname('compute', {}, serialize('whatever you say'))
    'test_compute_returns_whatever_you_say'
    >>> objcall2testname('square', {'x': serialize(7)}, serialize(49))
    'test_square_returns_49_for_7'
    >>> objcall2testname('capitalize', {'str': serialize('a word.')}, serialize('A word.'))
    'test_capitalize_returns_A_word_for_a_word'

    Two or more arguments are mentioned by name.
        >>> objcall2testname('ackermann', {'m': serialize(3), 'n': serialize(2)}, serialize(29))
        'test_ackermann_returns_29_for_m_equal_3_and_n_equal_2'

    Will sort arguments alphabetically.
        >>> objcall2testname('concat', {'s1': serialize('Hello '), 's2': serialize('world!')}, serialize('Hello world!'))
        'test_concat_returns_Hello_world_for_s1_equal_Hello_and_s2_equal_world'

    Always starts and ends a word with a letter or number.
        >>> objcall2testname('strip', {'n': serialize(1), 's': serialize('  A bit of whitespace  ')}, serialize(' A bit of whitespace '))
        'test_strip_returns_A_bit_of_whitespace_for_n_equal_1_and_s_equal_A_bit_of_whitespace'

    Uses argument name when argument is used as a return value.
        >>> alist = serialize([])
        >>> objcall2testname('identity', {'x': alist}, alist)
        'test_identity_returns_x_for_x_equal_list'
    """
    if args:
        # If return value is present in arguments list, use its name as an
        # identifier.
        output_name = key_for_value(args, output)
        if output_name:
            call_description = "%s_for_%s" % (output_name, arguments_as_string(args, always_use_argnames=True))
        else:
            call_description = "%s_for_%s" % (object2id(output), arguments_as_string(args))
    else:
        call_description = object2id(output)

    return "test_%s_returns_%s" % (underscore(object_name), call_description)

def exccall2testname(object_name, args, exception):
    """Generate a test method name that describes given object call raising
    an exception.

    >>> exccall2testname('do_this', {}, UnknownObject(Exception()))
    'test_do_this_raises_exception'
    >>> exccall2testname('square', {'x': ImmutableObject('a string')}, UnknownObject(TypeError()))
    'test_square_raises_type_error_for_a_string'
    """
    if args:
        call_description = "%s_for_%s" % (object2id(exception), arguments_as_string(args))
    else:
        call_description = object2id(exception)
    return "test_%s_raises_%s" % (underscore(object_name), call_description)

def gencall2testname(object_name, args, yields):
    """Generate a test method name that describes given generator object call
    yielding some values.

    >>> gencall2testname('generate', {}, [])
    'test_generate_yields_nothing'
    >>> gencall2testname('generate', {}, [ImmutableObject(1), ImmutableObject(2), ImmutableObject(3)])
    'test_generate_yields_1_then_2_then_3'
    >>> gencall2testname('backwards', {'x': ImmutableObject(321)}, [ImmutableObject('one'), ImmutableObject('two'), ImmutableObject('three')])
    'test_backwards_yields_one_then_two_then_three_for_321'
    """
    if args:
        call_description = "%s_for_%s" % (objects_list_to_id(yields), arguments_as_string(args))
    else:
        call_description = objects_list_to_id(yields)
    return "test_%s_yields_%s" % (underscore(object_name), call_description)

def call2testname(call, object_name):
    # Generators can be treated as calls, which take arguments during
    # initialization and return a list of yielded values.
    if isinstance(call, GeneratorObject):
        exception = generator_object_exception(call)
        if exception:
            return exccall2testname(object_name, call.args, exception)
        else:
            return gencall2testname(object_name, call.args, generator_object_yields(call))
    elif call.raised_exception():
        return exccall2testname(object_name, call.input, call.exception)
    else:
        return objcall2testname(object_name, call.input, call.output)

# :: [TestMethodDescription] -> [TestMethodDescription]
def sorted_test_method_descriptions(descriptions):
    return sorted(descriptions, key=lambda md: md.name)

# :: [TestMethodDescription] -> [TestMethodDescription]
def resolve_name_duplicates(descriptions):
    # We abuse the fact that descriptions has been sorted by name before being
    # passed into this function.
    last_name = ''
    num = 2
    for description in descriptions:
        if last_name != description.name:
            last_name = description.name
            num = 2
        else:
            description.name = "%s_case_%d" % (description.name, num)
            num += 1
    return descriptions

def name2testname(name):
    if name[0].isupper():
        return "Test%s" % name
    return "test_%s" % name

def should_ignore_method(method):
    return method.is_private()

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

# :: str, str -> str
def indented_setup(setup, indentation):
    """Indent each line of setup with given amount of indentation.

    >>> indented_setup("x = 1\\n", "  ")
    '  x = 1\\n'
    >>> indented_setup("x = 1\\ny = 2\\n", "    ")
    '    x = 1\\n    y = 2\\n'
    """
    return ''.join([indentation + line for line in setup.splitlines(True)])

class BareTestMethodDescription(object):
    def __init__(self, name, code=""):
        self.name = name
        self.code = code
    def contains_code(self):
        return not all([(line.strip().startswith("#") or line.strip() == '') for line in self.code.splitlines()])

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

    def template(self):
        if isinstance(self, UnittestTestGenerator):
            return UnittestTemplate()
        elif isinstance(self, NoseTestGenerator):
            return NoseTemplate()

    def ensure_import(self, import_):
        if import_ is not None and import_ not in self.imports:
            self.imports.append(import_)

    def ensure_imports(self, imports):
        for import_ in imports:
            self.ensure_import(import_)

    def add_tests_to_project(self, project, modnames, force=False):
        for modname in modnames:
            try:
                module = project.find_module_by_full_path(modname)
                if not module.has_errors():
                    self._add_tests_for_module(module, project, force)
            except ModuleNotFound:
                log.warning("Failed to inspect module %s, skipping test generation." % modname)

    def _add_tests_for_module(self, module, project, force):
        log.info("Generating tests for module %s." % module.subpath)
        for test_case in self._generate_test_cases(module):
            add_test_case_to_project(project, test_case, self.main_snippet, force)

    def _generate_test_cases(self, module):
        for object in testable_objects(module):
            test_case = self._generate_test_case(object, module)
            if test_case:
                yield test_case

    def _generate_test_case(self, object, module):
        class_name = name2testname(camelize(object.name))
        method_descriptions = resolve_name_duplicates(sorted_test_method_descriptions(self._generate_test_method_descriptions(object, module)))

        # Don't generate empty test classes.
        if method_descriptions:
            body = self._generate_test_class_code(class_name, method_descriptions)
            return self._generate_test_class(class_name, method_descriptions, module, body)

    def _generate_test_class_code(self, class_name, method_descriptions):
        result = "%s\n" % (self.test_class_header(class_name))
        for method_description in method_descriptions:
            result += "    def %s(self):\n" % method_description.name
            result += indented_setup(method_description.code, "        ")
            self.ensure_imports(method_description.code.imports)
            # We need at least one statement in a method to be syntatically correct.
            if not method_description.contains_code():
                result += "        pass\n"
            result += "\n"
        return result

    def _generate_test_class(self, class_name, method_descriptions, module, body):
        code = parse_fragment(body)
        def methoddesc2testmethod(method_description):
            name = method_description.name
            return TestMethod(name=name, code=find_method_code(code, name))
        return TestClass(name=class_name,
                         code=code,
                         test_cases=map(methoddesc2testmethod, method_descriptions),
                         imports=self.imports,
                         associated_modules=[module])

    def _generate_test_method_descriptions(self, object, module):
        if isinstance(object, Function):
            return self._generate_test_method_descriptions_for_function(object, module)
        elif isinstance(object, Class):
            return self._generate_test_method_descriptions_for_class(object, module)
        else:
            raise TypeError("Don't know how to generate test method descriptions for %s" % object)

    def _generate_test_method_descriptions_for_function(self, function, module):
        if testable_calls(function.calls):
            log.debug("Detected %s in function %s." % \
                          (pluralize("testable call", len(testable_calls(function.calls))),
                           function.name))

            # We're calling the function, so we have to make sure it will
            # be imported in the test
            self.ensure_import((module.locator, function.name))

            # We have at least one call registered, so use it.
            return self._method_descriptions_from_function(function)
        else:
            # No calls were traced, so we'll go for a single test stub.
            log.debug("Detected _no_ testable calls in function %s." % function.name)
            name = name2testname(underscore(function.name))
            return [BareTestMethodDescription(name, generate_test_case(function, self.template()))]

    def _generate_test_method_descriptions_for_class(self, klass, module):
        if klass.user_objects:
            # We're calling the method, so we have to make sure its class
            # will be imported in the test.
            self.ensure_import((module.locator, klass.name))

        for user_object in klass.user_objects:
            yield self._method_description_from_user_object(user_object)

        # No calls were traced for those methods, so we'll go for simple test stubs.
        for method in klass.get_untraced_methods():
            if not should_ignore_method(method):
                yield self._generate_test_method_description_for_method(method)

    def _generate_test_method_description_for_method(self, method):
        test_name = name2testname(method.name)
        return BareTestMethodDescription(test_name, generate_test_case(method, self.template()))

    def _method_descriptions_from_function(self, function):
        for call in testable_calls(function.get_unique_calls()):
            name = call2testname(call, function.name)
            yield BareTestMethodDescription(name, generate_test_case(call, self.template()))

    def _method_description_from_user_object(self, user_object):
        init_call = user_object.get_init_call()
        external_calls = testable_calls(user_object.get_external_calls())

        def test_name():
            if len(external_calls) == 0 and init_call:
                test_name = "test_creation"
                if init_call.input:
                    test_name += "_with_%s" % arguments_as_string(init_call.input)
                if init_call.raised_exception():
                    test_name += "_raises_%s" % object2id(init_call.exception)
            else:
                if len(external_calls) == 1:
                    call = external_calls[0]
                    test_name = call2testname(call, call.definition.name)
                # Methods with more than one external call use more brief
                # descriptions that don't include inputs and outputs.
                else:
                    methods = []
                    for method, calls_count in counted([call.definition.name for call in external_calls]):
                        if calls_count == 1:
                            methods.append(method)
                        else:
                            methods.append("%s_%d_times" % (method, calls_count))
                    test_name = "test_%s" % '_and_'.join(methods)
                if init_call and init_call.input:
                    test_name += "_after_creation_with_%s" % arguments_as_string(init_call.input)
            return test_name

        return BareTestMethodDescription(test_name(), generate_test_case(user_object, self.template()))

class UnittestTestGenerator(TestGenerator):
    main_snippet = parse_fragment("if __name__ == '__main__':\n    unittest.main()\n")

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

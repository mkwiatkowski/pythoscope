from pythoscope.astvisitor import descend, ASTVisitor
from pythoscope.astbuilder import parse_fragment, EmptyCode
from pythoscope.logger import log
from pythoscope.generator.adder import add_test_case_to_project
from pythoscope.generator.assertions import assertions_for_interaction
from pythoscope.generator.builder import UnittestTemplate, NoseTemplate,\
    generate_test_contents
from pythoscope.generator.cleaner import remove_objects_unworthy_of_naming
from pythoscope.generator.objects_namer import name_objects_on_timeline
from pythoscope.generator.case_namer import call2testname, name2testname,\
    userobject2testname
from pythoscope.generator.selector import testable_objects, testable_calls
from pythoscope.store import Class, Function, TestClass, TestMethod,\
    ModuleNotFound
from pythoscope.compat import all, sorted
from pythoscope.util import camelize, pluralize, underscore


# :: Call | UserObject | Method | Function -> CodeString
def generate_test_case(testable_interaction, template):
    """This functions binds all other functions from generator submodules
    together (assertions, cleaner, objects_namer and builder), implementing full
    test generation process, from a testable interaction object to a test
    case string.

    Call|UserObject|Method|Function -> assertions_for_interaction ->
      [Event] -> remove_objects_unworthy_of_naming ->
        [Event] -> name_objects_on_timeline ->
          [Event] -> generate_test_contents ->
            CodeString
    """
    return \
        generate_test_contents(
            name_objects_on_timeline(
                remove_objects_unworthy_of_naming(
                    assertions_for_interaction(testable_interaction))),
            template)

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

class TestMethodDescription(object):
    def __init__(self, name, code=""):
        self.name = name
        self.code = code
    def contains_code(self):
        return not all([(line.strip().startswith("#") or line.strip() == '') for line in self.code.splitlines()])

class TestGenerator(object):
    main_snippet = EmptyCode()
    template = None

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

    def test_class_header(self, name):
        raise NotImplementedError("Method test_class_header() not defined.")

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
            return [TestMethodDescription(name, generate_test_case(function, self.template))]

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
        return TestMethodDescription(test_name, generate_test_case(method, self.template))

    def _method_descriptions_from_function(self, function):
        for call in testable_calls(function.get_unique_calls()):
            name = call2testname(call, function.name)
            yield TestMethodDescription(name, generate_test_case(call, self.template))

    def _method_description_from_user_object(self, user_object):
        return TestMethodDescription(userobject2testname(user_object),
                                     generate_test_case(user_object, self.template))

class UnittestTestGenerator(TestGenerator):
    main_snippet = parse_fragment("if __name__ == '__main__':\n    unittest.main()\n")
    template = UnittestTemplate()

    def test_class_header(self, name):
        self.ensure_import('unittest')
        return "class %s(unittest.TestCase):" % name

class NoseTestGenerator(TestGenerator):
    template = NoseTemplate()

    def test_class_header(self, name):
        return "class %s:" % name

def add_tests_to_project(project, modnames, template, force=False):
    generator = TestGenerator.from_template(template)
    generator.add_tests_to_project(project, modnames, force)

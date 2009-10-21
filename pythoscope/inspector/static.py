import re
import types

from pythoscope.astvisitor import descend, ASTVisitor
from pythoscope.astbuilder import parse, ParseError
from pythoscope.store import Class, Function, Method, TestClass,TestMethod
from pythoscope.util import all_of_type, is_generator_code, \
    read_file_contents, compile_without_warnings


def is_test_class(name, bases):
    """Look at the name and bases of a class to determine whether it's a test
    class or not.

    >>> is_test_class("TestSomething", [])
    True
    >>> is_test_class("SomethingElse", [])
    False
    >>> is_test_class("ItDoesntLookLikeOne", ["unittest.TestCase"])
    True
    """
    return name.startswith("Test") or name.endswith("Test") \
           or "unittest.TestCase" in bases

def unindent(string):
    """Remove the initial part of whitespace from string.

    >>> unindent("1 + 2 + 3\\n")
    '1 + 2 + 3\\n'
    >>> unindent("  def fun():\\n    return 42\\n")
    'def fun():\\n  return 42\\n'
    """
    match = re.match(r'^([\t ]+)', string)
    if not match:
        return string
    whitespace = match.group(1)

    lines = []
    for line in string.splitlines(True):
        if line.startswith(whitespace):
            lines.append(line[len(whitespace):])
        else:
            return string
    return ''.join(lines)

def function_code_from_definition(definition):
    """Return a code object of a given function definition.

    Can raise SyntaxError if the definition is not valid.
    """
    consts = compile_without_warnings(unindent(str(definition))).co_consts
    return all_of_type(consts, types.CodeType)[0]

def is_generator_definition(definition):
    """Return True if given piece of code is a generator definition.

    >>> is_generator_definition("def f():\\n  return 1\\n")
    False
    >>> is_generator_definition("def g():\\n  yield 2\\n")
    True
    >>> is_generator_definition("  def indented_gen():\\n    yield 3\\n")
    True
    """
    try:
        return is_generator_code(function_code_from_definition(definition))
    except SyntaxError:
        # This most likely means given code used "return" with argument
        # inside generator.
        return False

def create_definition(name, args, code, definition_type):
    return definition_type(name, args=args, code=code,
                           is_generator=is_generator_definition(code))

class ModuleVisitor(ASTVisitor):
    def __init__(self):
        ASTVisitor.__init__(self)
        self.imports = []
        self.objects = []
        self.main_snippet = None
        self.last_import = None
        self.past_imports = False

    def visit_class(self, name, bases, body):
        visitor = descend(body.children, ClassVisitor)
        if is_test_class(name, bases):
            methods = [TestMethod(n, c) for (n, a, c) in visitor.methods]
            klass = TestClass(name=name, test_cases=methods, code=body)
        else:
            methods = [create_definition(n, a, c, Method) for (n, a, c) in visitor.methods]
            klass = Class(name=name, methods=methods, bases=bases)
        self.objects.append(klass)
        self.past_imports = True

    def visit_function(self, name, args, body):
        self.objects.append(create_definition(name, args, body, Function))
        self.past_imports = True

    def visit_lambda_assign(self, name, args):
        self.objects.append(Function(name, args=args))
        self.past_imports = True

    def visit_import(self, names, import_from, body):
        if import_from:
            for name in names:
                self.imports.append((import_from, name))
        else:
            self.imports.extend(names)
        if not self.past_imports:
            self.last_import = body

    def visit_main_snippet(self, body):
        self.main_snippet = body
        self.past_imports = True

class ClassVisitor(ASTVisitor):
    def __init__(self):
        ASTVisitor.__init__(self)
        self.methods = []

    def visit_class(self, name, bases, body):
        # Ignore definitions of subclasses.
        pass

    def visit_function(self, name, args, body):
        self.methods.append((name, args, body))

def inspect_module(project, path):
    return inspect_code(project, path, read_file_contents(path))

# :: (Project, string, string) -> Module
def inspect_code(project, path, code):
    try:
        tree = parse(code)
    except ParseError, e:
        return project.create_module(path, errors=[e])
    visitor = descend(tree, ModuleVisitor)

    # We assume that all test classes in this module has dependencies on
    # all imports the module contains.
    for test_class in [o for o in visitor.objects if isinstance(o, TestClass)]:
        # We gathered all imports in a single list, but import lists of those
        # classes may diverge in time, so we don't want to share their
        # structure.
        test_class.imports = visitor.imports[:]

    return project.create_module(path, code=tree, objects=visitor.objects,
        imports=visitor.imports, main_snippet=visitor.main_snippet,
        last_import=visitor.last_import)

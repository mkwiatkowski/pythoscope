import os.path
import re

from pythoscope.astvisitor import descend, parse, ParseError, ASTVisitor
from pythoscope.store import Module, Class, Function, Generator, Method, \
     TestClass, TestMethod
from pythoscope.util import read_file_contents


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

def is_generator_definition(code):
    """Return True if given piece of code is a generator definition.

    >>> is_generator_definition("def f():\\n  return 1\\n")
    False
    >>> is_generator_definition("def g():\\n  yield 2\\n")
    True
    >>> is_generator_definition("  def indented_gen():\\n    yield 3\\n")
    True
    """
    try:
        return compile(unindent(str(code)), '', 'single').co_consts[0].co_flags & 0x20 != 0
    except SyntaxError:
        # This most likely means given code used "return" with argument
        # inside generator.
        return False

class ModuleVisitor(ASTVisitor):
    def __init__(self):
        ASTVisitor.__init__(self)
        self.imports = []
        self.objects = []
        self.main_snippet = None

    def visit_class(self, name, bases, body):
        visitor = descend(body.children, ClassVisitor)
        if is_test_class(name, bases):
            methods = [TestMethod(n, c) for (n, c) in visitor.methods]
            klass = TestClass(name=name, test_cases=methods, code=body)
        else:
            methods = [Method(n, c) for (n, c) in visitor.methods]
            klass = Class(name=name, methods=methods, bases=bases)
        self.objects.append(klass)

    def visit_function(self, name, args, body):
        if is_generator_definition(body):
            self.objects.append(Generator(name, body))
        else:
            self.objects.append(Function(name, body))

    def visit_lambda_assign(self, name):
        self.objects.append(Function(name))

    def visit_import(self, names, import_from):
        if import_from:
            for name in names:
                self.imports.append((import_from, name))
        else:
            self.imports.extend(names)

    def visit_main_snippet(self, body):
        self.main_snippet = body

class ClassVisitor(ASTVisitor):
    def __init__(self):
        ASTVisitor.__init__(self)
        self.methods = []

    def visit_class(self, name, bases, body):
        # Ignore definitions of subclasses.
        pass

    def visit_function(self, name, args, body):
        self.methods.append((name, body))

def inspect_module(project, path):
    return inspect_code(project, path, read_file_contents(path))

def inspect_code(project, path, code):
    try:
        tree = parse(code)
    except ParseError, e:
        return project.create_module(path, errors=[e])
    visitor = descend(tree, ModuleVisitor)

    # We assume that all test classes in this module has dependencies on
    # imports and a main snippet the module contains.
    for test_class in [o for o in visitor.objects if isinstance(o, TestClass)]:
        # We gathered all imports in a single list, but import lists of those
        # classes may diverge in time, so we don't want to share their
        # structure.
        test_class.imports = visitor.imports[:]
        test_class.main_snippet = visitor.main_snippet

    return project.create_module(path, code=tree, objects=visitor.objects,
                                 imports=visitor.imports,
                                 main_snippet=visitor.main_snippet)

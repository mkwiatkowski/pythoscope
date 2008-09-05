import os.path
import re

from astvisitor import descend, parse, ParseError, ASTVisitor
from store import Module, Class, Function, TestModule, TestClass, TestMethod
from util import read_file_contents, python_modules_below


def is_test_module_path(path):
    """Return True if given path points to a test module.

    >>> is_test_module_path("module.py")
    False
    >>> is_test_module_path("test_module.py")
    True
    >>> is_test_module_path("pythoscope-tests%stest_module.py" % os.path.sep)
    True
    """
    return re.search(r'((^|%s)test_)|(_test.py$)' % re.escape(os.path.sep), path) is not None

class TopLevelVisitor(ASTVisitor):
    def __init__(self):
        ASTVisitor.__init__(self)
        self.objects = []

    def visit_class(self, name, bases, body):
        visitor = descend(body.children, ClassVisitor)
        self.objects.append(Class(name, visitor.methods, bases))

    def visit_function(self, name, args, body):
        self.objects.append(Function(name))

    def visit_lambda_assign(self, name):
        self.objects.append(Function(name))

class ClassVisitor(ASTVisitor):
    def __init__(self):
        ASTVisitor.__init__(self)
        self.methods = []

    def visit_class(self, name, bases, body):
        # Ignore definitions of subclasses.
        pass

    def visit_function(self, name, args, body):
        self.methods.append(name)

def inspect_project(project):
    for modpath in python_modules_below(project.path):
        inspect_module(project, modpath)

def inspect_module(project, path):
    if is_test_module_path(path):
        inspect = inspect_test_code
    else:
        inspect = inspect_code

    inspect(project, path, read_file_contents(path))

def inspect_code(project, path, code):
    try:
        tree = parse(code)
    except ParseError, e:
        return project.add_module(Module, path, errors=[e])
    visitor = descend(tree, TopLevelVisitor)

    return project.add_module(Module, path, objects=visitor.objects)

class TestClassVisitor(ASTVisitor):
    def __init__(self):
        ASTVisitor.__init__(self)
        self.methods = []

    def visit_class(self, name, bases, body):
        # Ignore definitions of subclasses.
        pass

    def visit_function(self, name, args, body):
        self.methods.append(TestMethod(name=name, code=body))

class TestModuleVisitor(ASTVisitor):
    def __init__(self):
        ASTVisitor.__init__(self)
        self.imports = []
        self.test_classes = []
        self.main_snippet = None

    def visit_class(self, name, bases, body):
        visitor = descend(body.children, TestClassVisitor)
        self.test_classes.append(TestClass(name=name,
                                           test_cases=visitor.methods,
                                           code=body))

    def visit_import(self, names, import_from):
        if import_from:
            self.imports.append((import_from, names))
        else:
            self.imports.extend(names)

    def visit_main_snippet(self, body):
        self.main_snippet = body

def inspect_test_code(project, path, code):
    try:
        tree = parse(code)
    except ParseError, e:
        return project.add_module(Module, path, errors=[e])
    visitor = descend(tree, TestModuleVisitor)

    for test_class in visitor.test_classes:
        test_class.imports = visitor.imports
        test_class.main_snippet = visitor.main_snippet

    return project.add_module(TestModule, path,
                              code=tree,
                              imports=visitor.imports,
                              main_snippet=visitor.main_snippet,
                              test_cases=visitor.test_classes)

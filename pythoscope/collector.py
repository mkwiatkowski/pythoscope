import os.path
import re

from astvisitor import parse, ParseError, ASTVisitor
from store import Module, Class, Function, TestModule
from util import read_file_contents, python_sources_below


def is_test_module_path(path):
    return re.search(r'(^test_)|(_test.py$)', path)

def descend(tree, visitor_type):
    """Walk over the AST using a visitor of a given type and return the visitor
    object once done.
    """
    visitor = visitor_type()
    visitor.visit(tree)
    return visitor

class TopLevelVisitor(ASTVisitor):
    def __init__(self):
        ASTVisitor.__init__(self)
        self.objects = []

    def visit_class(self, name, bases, children):
        visitor = descend(children, ClassVisitor)
        self.objects.append(Class(name, visitor.methods, bases))

    def visit_function(self, name, args, children):
        self.objects.append(Function(name))

    def visit_lambda_assign(self, name):
        self.objects.append(Function(name))

class ClassVisitor(ASTVisitor):
    def __init__(self):
        ASTVisitor.__init__(self)
        self.methods = []

    def visit_class(self, name, bases, children):
        # Ignore definitions of subclasses.
        pass

    def visit_function(self, name, args, children):
        self.methods.append(name)

def collect_information_from_paths(paths):
    """Collects information from list of paths. Path can point to a Python module
    file or to a directory. Directories are processed recursively.

    Returns a list of modules.
    """
    modules = []
    for path in paths:
        if os.path.isdir(path):
            modules.extend(collect_information_from_paths(python_sources_below(path)))
        else:
            modules.append(collect_information_from_module(path))
    return modules

def collect_information_from_module(path):
    if is_test_module_path(path):
        collect_from_code = collect_information_from_test_code
    else:
        collect_from_code = collect_information_from_code

    module = collect_from_code(read_file_contents(path))
    module.path = path
    return module

def collect_information_from_code(code):
    try:
        tree = parse(code)
    except ParseError, e:
        return Module(errors=[e])
    visitor = descend(tree, TopLevelVisitor)

    return Module(objects=visitor.objects)

def collect_information_from_test_code(code):
    regex = r"^(.*?)((?:class|def) .+?)(if __name__ == '__main__':.*)?$"
    match = re.match(regex, code, re.DOTALL)
    if match:
        imports, body, main_snippet = match.groups()
        if main_snippet is None:
            main_snippet = ""
    else:
        # If we can't recognize it, put everything into body.
        imports = main_snippet = ""
        body = code

    return TestModule(body=body, imports=imports,
                      main_snippet=main_snippet)

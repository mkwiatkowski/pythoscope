import compiler
import compiler.ast
import os.path

from compiler.visitor import ASTVisitor

from store import Module, Class, Function
from util import read_file_contents, python_sources_below

def descend(node, visitor_type):
    """Walk over the AST using a visitor of a given type and return the visitor
    object once done.
    """
    visitor = visitor_type()
    compiler.walk(node, visitor)
    return visitor

def derive_class_name(node):
    if isinstance(node, compiler.ast.Name):
        return node.name
    elif isinstance(node, compiler.ast.Getattr):
        return "%s.%s" % (derive_class_name(node.expr), node.attrname)
    return "<unknown>"

def derive_class_names(nodes):
    return map(derive_class_name, nodes)

class TopLevelVisitor(ASTVisitor):
    def __init__(self):
        self.objects = []

    def visitClass(self, node):
        visitor = descend(node, ClassVisitor)
        self.objects.append(Class(node.name,
                                  visitor.methods,
                                  derive_class_names(node.bases)))

    def visitFunction(self, node):
        self.objects.append(Function(node.name))

    def visitAssign(self, node):
        if len(node.nodes) == 1 and isinstance(node.nodes[0], compiler.ast.AssName) \
           and isinstance(node.expr, compiler.ast.Lambda):
            self.objects.append(Function(node.nodes[0].name))

class ClassVisitor(ASTVisitor):
    def __init__(self):
        self.methods = []

    def visitFunction(self, node):
        self.methods.append(node.name)

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
    module = collect_information_from_code(read_file_contents(path))
    module.path = path
    return module

def collect_information_from_code(code):
    try:
        tree = compiler.parse(code)
    except SyntaxError, e:
        return Module(errors=[e])
    visitor = descend(tree, TopLevelVisitor)

    return Module(objects=visitor.objects)

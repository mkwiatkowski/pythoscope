import compiler
import compiler.ast

from compiler.visitor import ASTVisitor

from util import read_file_contents

class Module(object):
    def __init__(self, objects=[], errors=[]):
        self.objects = objects
        self.errors = errors

    def _get_classes(self):
        return [o for o in self.objects if isinstance(o, Class)]
    classes = property(_get_classes)

    def _get_functions(self):
        return [o for o in self.objects if isinstance(o, Function)]
    functions = property(_get_functions)

class Class(object):
    def __init__(self, name, methods):
        self.name = name
        self.methods = methods

class Function(object):
    def __init__(self, name):
        self.name = name

def descend(node, visitor_type):
    """Walk over the AST using a visitor of a given type and return the visitor
    object once done.
    """
    visitor = visitor_type()
    compiler.walk(node, visitor)
    return visitor

class TopLevelVisitor(ASTVisitor):
    def __init__(self):
        self.objects = []

    def visitClass(self, node):
        visitor = descend(node, ClassVisitor)
        self.objects.append(Class(node.name, visitor.methods))

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

def collect_information_from_module(path):
    return collect_information_from_code(read_file_contents(path))

def collect_information_from_code(code):
    try:
        tree = compiler.parse(code)
    except SyntaxError, e:
        return Module(errors=[e])
    visitor = descend(tree, TopLevelVisitor)

    return Module(visitor.objects)

import compiler

from compiler.visitor import ASTVisitor

class Module(object):
    def __init__(self, objects):
        self.objects = objects

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

class ClassVisitor(ASTVisitor):
    def __init__(self):
        self.methods = []

    def visitFunction(self, node):
        self.methods.append(node.name)

def collect_information(code):
    tree = compiler.parse(code)
    visitor = descend(tree, TopLevelVisitor)

    return Module(visitor.objects)

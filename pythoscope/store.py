from util import underscore

def method2testmethod(name):
    if name == '__init__':
        return "object_initialization"
    return name

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

    def test_methods(self):
        return map(method2testmethod, self.methods)

class Function(object):
    def __init__(self, name):
        self.name = name

    def test_methods(self):
        return [underscore(self.name)]

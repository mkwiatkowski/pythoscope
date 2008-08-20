import pickle

from util import underscore

def method2testmethod(name):
    if name == '__init__':
        return "object_initialization"
    return name

class ModuleNotFound(Exception):
    def __init__(self, module):
        self.module = module

class Project(object):
    def __init__(self, modules=[], filepath=None):
        if filepath:
            self._read_from_file(filepath)
        else:
            self.modules = modules

    def save_to_file(self, filepath):
        fd = open(filepath, 'w')
        pickle.dump(self.modules, fd)
        fd.close()

    def _read_from_file(self, filepath):
        fd = open(filepath)
        self.modules = pickle.load(fd)
        fd.close()

    def __getitem__(self, module):
        for mod in self.modules:
            if mod.path == module:
                return mod
        raise ModuleNotFound(module)

class Module(object):
    def __init__(self, path="<code>", objects=[], errors=[]):
        self.path = path
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

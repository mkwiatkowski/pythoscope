import os
import pickle
import re

from util import underscore


class ModuleNotFound(Exception):
    def __init__(self, module):
        Exception.__init__(self, "Couldn't find module %r." % module)
        self.module = module

class Project(object):
    def from_file(cls, filepath):
        """Try reading from the project file. The file may not exist for
        projects that are analyzed the first time and that's OK.
        """
        try:
            fd = open(filepath)
            project = pickle.load(fd)
            # Update project's filepath, as the file could've been renamed.
            project.filepath = filepath
            fd.close()
        except IOError:
            project = Project(filepath)
        return project
    from_file = classmethod(from_file)

    def __init__(self, filepath=None, modules=[]):
        self.filepath = filepath
        self._modules = {}
        self.add_modules(modules)

    def save(self):
        fd = open(self.filepath, 'w')
        pickle.dump(self, fd)
        fd.close()

    def add_modules(self, modules):
        for module in modules:
            self._modules[module.path] = module
            # TODO: match test modules with application modules here.

    def __getitem__(self, module):
        for mod in self.modules:
            if module in [mod.path, mod.locator]:
                return mod
        raise ModuleNotFound(module)

    def _get_modules(self):
        return self._modules.values()
    modules = property(_get_modules)

class Localizable(object):
    "Any object with a path attribute."
    def _get_locator(self):
        return re.sub(r'(%s__init__)?\.py$' % os.path.sep, '', self.path).\
            replace(os.path.sep, ".")
    locator = property(_get_locator)

class Module(Localizable):
    def __init__(self, path=None, objects=[], errors=[]):
        # Path has to be unique, otherwise project won't be able to
        # differentiate between modules.
        if path is None:
            path = "<code %s>" % id(self)
        self.path = path
        self.objects = objects
        self.errors = errors

    def _get_testable_objects(self):
        return [o for o in self.objects if o.is_testable()]
    testable_objects = property(_get_testable_objects)

    def _get_classes(self):
        return [o for o in self.objects if isinstance(o, Class)]
    classes = property(_get_classes)

    def _get_functions(self):
        return [o for o in self.objects if isinstance(o, Function)]
    functions = property(_get_functions)

    def has_test_cases(self):
        "Return True if the Module will spawn at least one test case."
        for object in self.testable_objects:
            if object.testable_methods:
                return True
        return False

class Class(object):
    def __init__(self, name, methods, bases=[]):
        self.name = name
        self.methods = methods
        self.bases = bases

    def is_testable(self):
        ignored_superclasses = ['Exception', 'unittest.TestCase']
        for klass in ignored_superclasses:
            if klass in self.bases:
                return False
        return True

    def testable_methods(self):
        return list(self._testable_methods_generator())

    def _testable_methods_generator(self):
        for method in self.methods:
            if method == '__init__':
                yield "object_initialization"
            elif not method.startswith('_'):
                yield method

class Function(object):
    def __init__(self, name):
        self.name = name

    def testable_methods(self):
        return [underscore(self.name)]

    def is_testable(self):
        return not self.name.startswith('_')

def import_stmt(import_desc):
    if isinstance(import_desc, tuple):
        return 'from %s import %s' % import_desc
    else:
        return 'import %s' % import_desc

class TestModule(Localizable):
    def __init__(self, path=None, application_module=None, imports="",
                 test_cases="", main_snippet=""):
        # Path has to be unique, otherwise project won't be able to
        # differentiate between modules.
        if path is None:
            path = "<test %s>" % id(self)

        self.path = path
        self.application_module = application_module

        self.imports = imports
        self.test_cases = test_cases
        self.main_snippet = main_snippet

    def ensure_main_snippet(self, main_snippet, force=False):
        """Make sure the main_snippet is present. Won't overwrite the snippet
        unless force flag is set.
        """
        if not self.main_snippet or force:
            self.main_snippet = main_snippet

    def ensure_imports(self, required_imports):
        "Make sure that all required imports are present."
        for imp in required_imports:
            self._ensure_import(imp)

    def add_test_cases(self, test_cases):
        if self.test_cases:
            self.test_cases += "\n"
        self.test_cases += test_cases

    def get_content(self):
        return '%s\n\n%s\n\n%s\n' % (self.imports.strip(),
                                     self.test_cases.strip(),
                                     self.main_snippet.strip())

    def _ensure_import(self, import_desc):
        if not self._contains_import(import_desc):
            self._add_import(import_desc)

    def _contains_import(self, import_desc):
        return import_stmt(import_desc) in self.imports

    def _add_import(self, import_desc):
        if self.imports:
            self.imports += "\n"
        self.imports += import_stmt(import_desc)

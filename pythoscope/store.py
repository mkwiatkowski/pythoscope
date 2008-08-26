import os
import pickle
import re

from util import underscore, write_string_to_file


class ModuleNotFound(Exception):
    def __init__(self, module):
        Exception.__init__(self, "Couldn't find module %r." % module)
        self.module = module

def test_module_name_for_test_case(test_case):
    "Come up with a name for a test module which will contain given test case."
    return "test_foo.py" # TODO

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

    def add_test_cases(self, test_cases, test_directory, force):
        for test_case in test_cases:
            self.add_test_case(test_case, test_directory, force)

    def add_test_case(self, test_case, test_directory, force):
        if not self._contains_test_case(test_case):
            place = self._find_place_for_test_case(test_case, test_directory)
            place.add_test_case(test_case)
        elif force:
            self._replace_test_case(test_case)

    def _contains_test_case(self, test_case):
        return False # TODO

    def _find_place_for_test_case(self, test_case, test_directory):
        """Find the best place for the new test case to be added. If there is
        no such place in existing test modules, a new one will be created.
        """
        for mod in self.modules:
            if isinstance(mod, TestModule):
                return mod
        return TestModule(os.path.join(test_directory,
                                       test_module_name_for_test_case(test_case)))

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
    def __init__(self, path=None, body="", imports="", main_snippet=""):
        # Path has to be unique, otherwise project won't be able to
        # differentiate between modules.
        if path is None:
            path = "<test %s>" % id(self)

        self.path = path

        self.body = body
        self.imports = imports
        self.main_snippet = main_snippet

        self.test_cases = []

    def add_test_case(self, test_case):
        self._ensure_imports(test_case.imports)
        self._ensure_main_snippet(test_case.main_snippet)
        self.test_cases.append(test_case)
        self._save()

    def get_content(self):
        return '%s\n\n%s\n\n%s\n' % (self.imports.strip(),
                                     self._get_body(),
                                     self.main_snippet.strip())

    def _ensure_main_snippet(self, main_snippet, force=False):
        """Make sure the main_snippet is present. Won't overwrite the snippet
        unless force flag is set.
        """
        if not self.main_snippet or force:
            self.main_snippet = main_snippet

    def _ensure_imports(self, imports):
        "Make sure that all required imports are present."
        for imp in imports:
            self._ensure_import(imp)

    def _ensure_import(self, import_desc):
        if not self._contains_import(import_desc):
            self._add_import(import_desc)

    def _contains_import(self, import_desc):
        return import_stmt(import_desc) in self.imports

    def _add_import(self, import_desc):
        if self.imports:
            self.imports += "\n"
        self.imports += import_stmt(import_desc)

    def _get_body(self):
        body = self.body.strip()
        if body:
            body += '\n\n'
        return body + '\n'.join(map(lambda tc: tc.body.strip(), self.test_cases))

    def _save(self):
        # Don't save the test file unless it has at least one test case.
        if self._get_body():
            write_string_to_file(self.get_content(), self.path)

class TestCase(object):
    """Basic testing object, either generated by Pythoscope or hand-writen by
    the user.

    Each test case contains a set of requirements its surrounding must meet,
    like the list of imports it needs, contents of the "if __name__ == '__main__'"
    snippet or specific setup and teardown instructions.
    """
    def __init__(self, body, imports, main_snippet):
        self.body = body
        self.imports = imports
        self.main_snippet = main_snippet

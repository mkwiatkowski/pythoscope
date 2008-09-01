import os
import pickle
import re

from astvisitor import EmptyCode, Newline, create_import, regenerate
from util import max_by_not_zero, underscore, write_string_to_file


class ModuleNeedsAnalysis(Exception):
    def __init__(self, module, path):
        Exception.__init__(self, "Destination test module %r wasn't analyzed." % module)
        self.module = module
        self.path = path

class ModuleNotFound(Exception):
    def __init__(self, module):
        Exception.__init__(self, "Couldn't find module %r." % module)
        self.module = module

def test_module_name_for_test_case(test_case):
    "Come up with a name for a test module which will contain given test case."
    if test_case.associated_modules:
        return module_path_to_test_path(test_case.associated_modules[0].path)
    return "test_foo.py" # TODO

def module_path_to_test_path(module):
    """Convert a module locator to a proper test filename.

    >>> module_path_to_test_path("module.py")
    'test_module.py'
    >>> module_path_to_test_path("pythoscope/store.py")
    'test_pythoscope_store.py'
    >>> module_path_to_test_path("pythoscope/__init__.py")
    'test_pythoscope.py'
    """
    return "test_" + re.sub(r'%s__init__.py$' % os.path.sep, '.py', module).\
        replace(os.path.sep, "_")

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
            self.add_module(module)

    def add_module(self, module):
        self._modules[module.path] = module

    def add_test_cases(self, test_cases, test_directory, force):
        for test_case in test_cases:
            self.add_test_case(test_case, test_directory, force)

    def add_test_case(self, test_case, test_directory, force):
        if not self._contains_test_case(test_case):
            place = self._find_place_for_test_case(test_case, test_directory)
            place.add_test_case(test_case)
        elif force:
            self._replace_test_case(test_case)

    def test_cases_iter(self):
        "Iterate over all test cases present in a project."
        for tmodule in self._get_test_modules():
            for test_case in tmodule.test_cases:
                yield test_case

    def _contains_test_case(self, test_case):
        for tcase in self.test_cases_iter():
            if tcase.name == test_case.name:
                return True
        return False

    def _get_test_modules(self):
        return [mod for mod in self.modules if isinstance(mod, TestModule)]

    def _find_place_for_test_case(self, test_case, test_directory):
        """Find the best place for the new test case to be added. If there is
        no such place in existing test modules, a new one will be created.
        """
        if isinstance(test_case, TestClass):
            return self._find_test_module(test_case) or \
                   self._create_test_module_for(test_case, test_directory)
        elif isinstance(test_case, TestMethod):
            return self._find_test_class(test_case) or \
                   self._create_test_class_for(test_case)

    def _create_test_module_for(self, test_case, test_directory):
        """Create a new TestModule for a given test case. If the test module
        already existed, will raise an ModuleNeedsAnalysis exception.
        """
        test_name = test_module_name_for_test_case(test_case)
        test_path = os.path.join(test_directory, test_name)
        if os.path.exists(test_path):
            raise ModuleNeedsAnalysis(test_name, test_path)
        test_module = TestModule(test_path)
        self.add_module(test_module)
        return test_module

    def _find_test_module(self, test_case):
        """Find test module that will be good for the given test case.

        Currently only module names are used as a criteria.
        """
        for module in test_case.associated_modules:
            test_module = self._find_associate_test_module_by_name(module) or \
                          self._find_associate_test_module_by_test_cases(module)
            if test_module:
                return test_module

    def _find_associate_test_module_by_name(self, module):
        """Try to find a test module with name corresponding to the name of
        the application module.
        """
        for test_module in self._get_test_modules():
            if test_module.path.endswith(module_path_to_test_path(module.path)):
                return test_module

    def _find_associate_test_module_by_test_cases(self, module):
        """Try to find a test module with most test cases for the given
        application module.
        """
        def test_cases_number(test_module):
            return len(test_module.get_test_cases_for_module(module))
        test_module = max_by_not_zero(test_cases_number, self._get_test_modules())
        if test_module:
            return test_module

    def _find_test_class(self, test_method):
        """Find a test class that will be good for the given test method.
        """
        pass # TODO

    def _create_test_class_for(self, test_method):
        """Create a new test class for given test method.
        """
        pass # TODO

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

    def get_testable_methods(self):
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

    def get_testable_methods(self):
        return [underscore(self.name)]

    def is_testable(self):
        return not self.name.startswith('_')

class TestModule(Localizable):
    def __init__(self, path=None, code=None, imports=None, main_snippet=None,
                 test_cases=None):
        # Path has to be unique, otherwise project won't be able to
        # differentiate between modules.
        if path is None:
            path = "<test %s>" % id(self)
        if code is None:
            code = EmptyCode()
        if imports is None:
            imports = []
        if test_cases is None:
            test_cases = []

        self.path = path
        self.code = code
        self.imports = imports
        self.main_snippet = main_snippet
        self.test_cases = test_cases

    def add_test_case(self, test_case):
        if not isinstance(test_case, TestClass):
            raise TypeError("Only TestClasses can be added to TestModules.")
        self._ensure_imports(test_case.imports)
        self._ensure_main_snippet(test_case.main_snippet)
        self._add_test_case(test_case)
        self._save()

    def get_content(self):
        return regenerate(self.code)

    def get_test_cases_for_module(self, module):
        """Return all test cases that are associated with given module.
        """
        return [tc for tc in self.test_cases if module in tc.associated_modules]

    def _get_test_classes(self):
        return [o for o in self.test_cases if isinstance(o, TestClass)]
    test_classes = property(_get_test_classes)

    def _ensure_main_snippet(self, main_snippet, force=False):
        """Make sure the main_snippet is present. Won't overwrite the snippet
        unless force flag is set.
        """
        if not main_snippet:
            return

        if not self.main_snippet:
            self.main_snippet = main_snippet
            self.code.append_child(main_snippet)
        elif force:
            self.main_snippet.replace(main_snippet)
            self.main_snippet = main_snippet

    def _ensure_imports(self, imports):
        "Make sure that all required imports are present."
        for imp in imports:
            self._ensure_import(imp)

    def _ensure_import(self, import_desc):
        # Add an extra newline separating imports from the code.
        if not self.imports:
            self.code.insert_child(0, Newline())
        if not self._contains_import(import_desc):
            self._add_import(import_desc)

    def _contains_import(self, import_desc):
        return import_desc in self.imports

    def _add_import(self, import_desc):
        self.imports.append(import_desc)
        self.code.insert_child(0, create_import(import_desc))

    def _add_test_case(self, test_case):
        self.test_cases.append(test_case)
        # If the main_snippet exists we have to put the new test case
        # before it. If it doesn't we put the test case at the end.
        if self.main_snippet:
            self._insert_before_main_snippet(test_case.code)
        else:
            self.code.append_child(test_case.code)

    def _insert_before_main_snippet(self, code):
        for i, child in enumerate(self.code.children):
            if child == self.main_snippet:
                self.code.insert_child(i, code)
                break

    def _save(self):
        # Don't save the test file unless it has at least one test case.
        if self.test_cases:
            write_string_to_file(self.get_content(), self.path)

class _TestCase(object):
    def __init__(self, name, code=None):
        if code is None:
            code = EmptyCode()
        self.name = name
        self.code = code

class TestClass(_TestCase):
    """Basic testing object, either generated by Pythoscope or hand-writen by
    the user.

    Each test class contains a set of requirements its surrounding must meet,
    like the list of imports it needs, contents of the "if __name__ == '__main__'"
    snippet or specific setup and teardown instructions.

    associated_modules is a list of Modules which this test class exercises.
    """
    def __init__(self, name, code=None, methods=None, imports=None,
                 main_snippet=None, test_module=None, associated_modules=None):
        if methods is None:
            methods = []
        if imports is None:
            imports = []
        if associated_modules is None:
            associated_modules = []

        _TestCase.__init__(self, name, code)
        self.test_module = test_module
        self.methods = methods
        self.imports = imports
        self.main_snippet = main_snippet
        self.associated_modules = associated_modules

    def add_test_case(self, test_case):
        if not isinstance(test_case, TestMethod):
            raise TypeError("Only TestMethods can be addd to TestClasses.")
        if test_case.klass:
            raise TypeError("This TestMethod already belong to another test class.")
        test_case.klass = self
        self.methods.append(test_case)
        self.code.append_child(test_case.code)

class TestMethod(_TestCase):
    def __init__(self, name, klass=None, code=None):
        _TestCase.__init__(self, name, code)
        self.klass = klass

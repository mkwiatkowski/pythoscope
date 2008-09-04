import os
import pickle
import re
import time

from astvisitor import EmptyCode, Newline, create_import, find_last_leaf, \
     get_starting_whitespace, is_node_of_type, regenerate
from util import max_by_not_zero, underscore, write_string_to_file


class ModuleNeedsAnalysis(Exception):
    def __init__(self, path, out_of_sync=False):
        Exception.__init__(self, "Destination test module %r needs analysis." % path)
        self.path = path
        self.out_of_sync = out_of_sync

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

def get_pythoscope_path(project_path):
    return os.path.join(project_path, ".pythoscope")

def get_pickle_path(project_path):
    return os.path.join(get_pythoscope_path(project_path), "project.pickle")

class Project(object):
    """Object representing the whole project under Pythoscope wings.

    No modifications are final until you call save().
    """

    def from_directory(cls, project_path):
        """Read the project information from the .pythoscope/ directory of
        the given project.

        The pickle file may not exist for project that is analyzed the
        first time and that's OK.
        """
        try:
            fd = open(get_pickle_path(project_path))
            project = pickle.load(fd)
            fd.close()
            # Mark all test modules as unchanged.
            for test_module in project._get_test_modules():
                test_module.changed = False
        except IOError:
            project = Project(project_path)
        return project
    from_directory = classmethod(from_directory)

    def __init__(self, path=None, modules=[]):
        self.path = path
        self._modules = {}
        self.add_modules(modules)

    def _get_pickle_path(self):
        return get_pickle_path(self.path)

    def save(self):
        fd = open(self._get_pickle_path(), 'w')
        pickle.dump(self, fd)
        fd.close()

        for test_module in self._get_test_modules():
            test_module.save()

    def add_modules(self, modules):
        for module in modules:
            self.add_module(module)

    def add_module(self, module):
        self._modules[module.path] = module

    def add_test_cases(self, test_cases, test_directory, force):
        for test_case in test_cases:
            self.add_test_case(test_case, test_directory, force)

    def add_test_case(self, test_case, test_directory, force):
        existing_test_case = self._find_test_case_by_name(test_case.name)
        if not existing_test_case:
            place = self._find_place_for_test_case(test_case, test_directory)
            place.add_test_case(test_case)
        elif isinstance(test_case, TestClass) and isinstance(existing_test_case, TestClass):
            self._merge_test_classes(existing_test_case, test_case, force)
        elif force:
            existing_test_case.replace_itself_with(test_case)

    def test_cases_iter(self):
        "Iterate over all test cases present in a project."
        for tmodule in self._get_test_modules():
            for test_case in tmodule.test_cases:
                yield test_case

    def _merge_test_classes(self, test_class, other_test_class, force):
        """Merge other_test_case into test_case.
        """
        for method in other_test_class.test_cases:
            existing_test_method = test_class.find_method_by_name(method.name)
            if not existing_test_method:
                test_class.add_test_case(method)
            elif force:
                test_class.replace_test_case(existing_test_method, method)

    def _find_test_case_by_name(self, name):
        for tcase in self.test_cases_iter():
            if tcase.name == name:
                return tcase

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
        already existed, will raise a ModuleNeedsAnalysis exception.
        """
        test_name = test_module_name_for_test_case(test_case)
        test_path = os.path.join(test_directory, test_name)
        if os.path.exists(test_path):
            raise ModuleNeedsAnalysis(test_path)
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
    """An object which has a corresponding file.

    Each Localizable has a 'path' attribute and an information when it was
    created, to be in sync with its file system counterpart.
    """
    def __init__(self, path, created=None):
        # Path has to be unique, otherwise Project won't be able to
        # differentiate between modules.
        if path is None:
            path  = "<%s %s>" % (str(self.__class__), id(self))
        if created is None:
            created = time.time()
        self.path = path
        self.created = created

    def _get_locator(self):
        return re.sub(r'(%s__init__)?\.py$' % os.path.sep, '', self.path).\
            replace(os.path.sep, ".")
    locator = property(_get_locator)

    def is_out_of_sync(self):
        """Is the object out of sync with its file.
        """
        try:
            return os.path.getmtime(self.path) > self.created
        except OSError:
            # File may not exist, in which case we're safe.
            return False

    def write(self, new_content):
        """Overwrite the file with new contents and update its created time.
        """
        write_string_to_file(new_content, self.path)
        self.created = time.time()

class Module(Localizable):
    def __init__(self, path=None, objects=[], errors=[]):
        Localizable.__init__(self, path)
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

class TestCase(object):
    """A single test object, possibly contained within a test suite (denoted
    as parent attribute).
    """
    def __init__(self, name, code=None, parent=None):
        if code is None:
            code = EmptyCode()
        self.name = name
        self.code = code
        self.parent = parent

    def replace_itself_with(self, new_test_case):
        self.parent.replace_test_case(self, new_test_case)

class TestSuite(TestCase):
    """A test objects container.

    Keeps both test cases and other test suites in test_cases attribute.
    """
    allowed_test_case_classes = []

    def __init__(self, name, code=None, parent=None, test_cases=[]):
        TestCase.__init__(self, name, code, parent)

        self.changed = True
        self.test_cases = []

    def add_test_cases(self, test_cases, append_code=True):
        for test_case in test_cases:
            self.add_test_case(test_case, append_code)

    def add_test_case(self, test_case, append_code=True):
        self._check_test_case_type(test_case)

        test_case.parent = self
        self.test_cases.append(test_case)

        if append_code:
            self._append_test_case_code(test_case.code)
            self.mark_as_changed()

    def replace_test_case(self, old_test_case, new_test_case):
        self._check_test_case_type(new_test_case)
        if old_test_case not in self.test_cases:
            raise ValueError("Given test case is not part of this test suite.")

        self.test_cases.remove(old_test_case)

        # The easiest way to get the new code inside the AST is to call
        # replace() on the old test case code.
        # It is destructive, but since we're discarding the old test case
        # anyway, it doesn't matter.
        old_test_case.code.replace(new_test_case.code)

        self.add_test_case(new_test_case, False)
        self.mark_as_changed()

    def mark_as_changed(self):
        self.changed = True
        if self.parent:
            self.parent.mark_as_changed()

    def _check_test_case_type(self, test_case):
        if not isinstance(test_case, tuple(self.allowed_test_case_classes)):
            raise TypeError("Given test case isn't allowed to be added to this test suite.")

class TestMethod(TestCase):
    pass

class TestClass(TestSuite):
    """Testing class, either generated by Pythoscope or hand-writen by the user.

    Each test class contains a set of requirements its surrounding must meet,
    like the list of imports it needs, contents of the "if __name__ == '__main__'"
    snippet or specific setup and teardown instructions.

    associated_modules is a list of Modules which this test class exercises.
    """
    allowed_test_case_classes = [TestMethod]

    def __init__(self, name, code=None, parent=None, test_cases=[],
                 imports=None, main_snippet=None, associated_modules=None):
        TestSuite.__init__(self, name, code, parent, test_cases)

        if imports is None:
            imports = []
        if associated_modules is None:
            associated_modules = []

        self.imports = imports
        self.main_snippet = main_snippet
        self.associated_modules = associated_modules

        # Code of test cases passed to the constructor is already contained
        # within the class code.
        self.add_test_cases(test_cases, False)

    def _append_test_case_code(self, code):
        """Append to the right node, so that indentation level of the
        new method is good.
        """
        if self.code.children and is_node_of_type(self.code.children[-1], 'suite'):
            suite = self.code.children[-1]
            # Prefix the definition with the right amount of whitespace.
            node = find_last_leaf(suite.children[-2])
            ident = get_starting_whitespace(suite)
            # There's no need to have extra newlines.
            if node.prefix.endswith("\n") and ident.startswith("\n"):
                node.prefix += ident.lstrip("\n")
            else:
                node.prefix += ident
            # Insert before the class contents dedent.
            suite.insert_child(-1, code)
        else:
            self.code.append_child(code)

    def find_method_by_name(self, name):
        for method in self.test_cases:
            if method.name == name:
                return method

class TestModule(Localizable, TestSuite):
    allowed_test_case_classes = [TestClass]

    def __init__(self, path=None, code=None, test_cases=[], imports=None,
                 main_snippet=None):
        Localizable.__init__(self, path)
        TestSuite.__init__(self, None, code, None, test_cases)

        if imports is None:
            imports = []

        self.imports = imports
        self.main_snippet = main_snippet

        # Code of test cases passed to the constructor is already contained
        # within the module code.
        self.add_test_cases(test_cases, False)

    def add_test_case(self, test_case, append_code=True):
        TestSuite.add_test_case(self, test_case, append_code)

        self._ensure_imports(test_case.imports)
        self._ensure_main_snippet(test_case.main_snippet)

    # def replace_test_case:
    #   Using the default definition. We don't remove imports or main_snippet,
    #   because we may unintentionally break something.

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
        self.mark_as_changed()

    def _ensure_imports(self, imports):
        "Make sure that all required imports are present."
        for imp in imports:
            self._ensure_import(imp)
        self.mark_as_changed()

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

    def _append_test_case_code(self, code):
        # If the main_snippet exists we have to put the new test case
        # before it. If it doesn't we put the test case at the end.
        if self.main_snippet:
            self._insert_before_main_snippet(code)
        else:
            self.code.append_child(code)

    def _insert_before_main_snippet(self, code):
        for i, child in enumerate(self.code.children):
            if child == self.main_snippet:
                self.code.insert_child(i, code)
                break

    def save(self):
        # Don't save the test file unless it has been changed.
        if self.changed:
            if self.is_out_of_sync():
                raise ModuleNeedsAnalysis(self.path, out_of_sync=True)
            self.write(self.get_content())

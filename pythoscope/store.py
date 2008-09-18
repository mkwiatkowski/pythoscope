import __builtin__
import os
import pickle
import re
import time
import types

from astvisitor import EmptyCode, Newline, create_import, find_last_leaf, \
     get_starting_whitespace, is_node_of_type, regenerate, \
     remove_trailing_whitespace
from util import all_of_type, max_by_not_zero, set, \
     write_string_to_file, ensure_directory, DirectoryException, \
     get_last_modification_time, read_file_contents, python_modules_below, \
     extract_subpath, directories_under, findfirst


# So we can pickle the function type.
__builtin__.function = types.FunctionType

class ModuleNeedsAnalysis(Exception):
    def __init__(self, path, out_of_sync=False):
        Exception.__init__(self, "Destination test module %r needs analysis." % path)
        self.path = path
        self.out_of_sync = out_of_sync

class ModuleNotFound(Exception):
    def __init__(self, module):
        Exception.__init__(self, "Couldn't find module %r." % module)
        self.module = module

class ModuleSaveError(Exception):
    def __init__(self, module, reason):
        Exception.__init__(self, "Couldn't save module %r: %s." % (module, reason))
        self.module = module
        self.reason = reason

def test_module_name_for_test_case(test_case):
    "Come up with a name for a test module which will contain given test case."
    if test_case.associated_modules:
        return module_path_to_test_path(test_case.associated_modules[0].subpath)
    return "test_foo.py" # TODO

def module_path_to_name(module_path):
    return re.sub(r'.py$', '',
                  re.sub(r'%s__init__.py$' % os.path.sep, '.py',
                         module_path)).replace(os.path.sep, "_")

def module_path_to_test_path(module):
    """Convert a module locator to a proper test filename.

    >>> module_path_to_test_path("module.py")
    'test_module.py'
    >>> module_path_to_test_path("pythoscope/store.py")
    'test_pythoscope_store.py'
    >>> module_path_to_test_path("pythoscope/__init__.py")
    'test_pythoscope.py'
    """
    return "test_%s.py" % module_path_to_name(module)

def possible_test_module_paths(module, new_tests_directory):
    """Return possible locations of a test module corresponding to given
    application module.
    """
    test_directories = ["", "test", "tests"]
    if new_tests_directory not in test_directories:
        test_directories.append(new_tests_directory)
    def generate():
        for name in possible_test_module_names(module):
            for test_directory in test_directories:
                yield os.path.join(test_directory, name)
    return list(generate())

def possible_test_module_names(module):
    module_name = module_path_to_name(module.subpath)

    for name in ["test_%s", "%s_test", "%sTest", "tests_%s", "%s_tests", "%sTests"]:
        yield (name % module_name) + ".py"
    for name in ["test%s", "Test%s", "%sTest", "tests%s", "Tests%s", "%sTests"]:
        yield (name % module_name.capitalize()) + ".py"

def get_pythoscope_path(project_path):
    return os.path.join(project_path, ".pythoscope")

def get_pickle_path(project_path):
    return os.path.join(get_pythoscope_path(project_path), "project.pickle")

def get_points_of_entry_path(project_path):
    return os.path.join(get_pythoscope_path(project_path), "points-of-entry")

def get_test_objects(objects):
    def is_test_object(object):
        return isinstance(object, TestCase)
    return filter(is_test_object, objects)

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
        project_path = os.path.realpath(project_path)
        try:
            fd = open(get_pickle_path(project_path))
            project = pickle.load(fd)
            fd.close()
            # Update project's path, as the directory could've been moved.
            project.path = project_path
        except IOError:
            project = Project(project_path)
        return project
    from_directory = classmethod(from_directory)

    def __init__(self, path):
        self.path = path
        self.new_tests_directory = "tests"
        self.points_of_entry = {}
        self._modules = {}

        self._find_new_tests_directory()

    def _get_pickle_path(self):
        return get_pickle_path(self.path)

    def _get_points_of_entry_path(self):
        return get_points_of_entry_path(self.path)

    def _find_new_tests_directory(self):
        for path in directories_under(self.path):
            if re.search(r'[_-]?tests?([_-]|$)', path):
                self.new_tests_directory = path

    def save(self):
        # To avoid inconsistencies try to save all project's modules first. If
        # any of those saves fail, the pickle file won't get updated.
        for module in self.get_modules():
            module.save()

        fd = open(self._get_pickle_path(), 'w')
        pickle.dump(self, fd)
        fd.close()

    def find_module_by_full_path(self, path):
        subpath = self._extract_subpath(path)
        return self[subpath]

    def ensure_point_of_entry(self, path):
        name = self._extract_point_of_entry_subpath(path)
        if name not in self.points_of_entry:
            poe = PointOfEntry(project=self, name=name)
            self.points_of_entry[name] = poe
            return poe

    def remove_point_of_entry(self, name):
        poe = self.points_of_entry.pop(name)
        poe.clear_previous_run()

    def create_module(self, path, **kwds):
        """Create a module for this project located under given path.

        If there already was a module with given subpath, it will get replaced
        with a new instance using the _replace_references_to_module method.

        Returns the new Module object.
        """
        module = Module(subpath=self._extract_subpath(path), project=self, **kwds)

        if module.subpath in self._modules.keys():
            self._replace_references_to_module(module)

        self._modules[module.subpath] = module

        return module

    def remove_module(self, subpath):
        """Remove a module from this Project along with all references to it
        from other modules.
        """
        module = self[subpath]
        for test_case in self.iter_test_cases():
            try:
                test_case.associated_modules.remove(module)
            except ValueError:
                pass
        del self._modules[subpath]

    def _replace_references_to_module(self, module):
        """Remove a module with the same subpath as given module from this
        Project and replace all references to it with the new instance.
        """
        old_module = self[module.subpath]
        for test_case in self.iter_test_cases():
            try:
                test_case.associated_modules.remove(old_module)
                test_case.associated_modules.append(module)
            except ValueError:
                pass        

    def _extract_point_of_entry_subpath(self, path):
        """Takes the file path and returns subpath relative to the
        points of entry path.

        Assumes the given path is under points of entry path.
        """
        return extract_subpath(path, self._get_points_of_entry_path())

    def _extract_subpath(self, path):
        """Takes the file path and returns subpath relative to the
        project.

        Assumes the given path is under Project.path.
        """
        return extract_subpath(path, self.path)

    def add_test_cases(self, test_cases, force=False):
        for test_case in test_cases:
            self.add_test_case(test_case, force)

    def add_test_case(self, test_case, force=False):
        existing_test_case = self._find_test_case_by_name(test_case.name)
        if not existing_test_case:
            place = self._find_place_for_test_case(test_case)
            place.add_test_case(test_case)
        elif isinstance(test_case, TestClass) and isinstance(existing_test_case, TestClass):
            self._merge_test_classes(existing_test_case, test_case, force)
        elif force:
            existing_test_case.replace_itself_with(test_case)

    def iter_test_cases(self):
        for module in self.iter_modules():
            for test_case in module.test_cases:
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
        test_class.ensure_imports(other_test_class.imports)

    def _find_test_case_by_name(self, name):
        for tcase in self.iter_test_cases():
            if tcase.name == name:
                return tcase

    def _find_place_for_test_case(self, test_case):
        """Find the best place for the new test case to be added. If there is
        no such place in existing test modules, a new one will be created.
        """
        if isinstance(test_case, TestClass):
            return self._find_test_module(test_case) or \
                   self._create_test_module_for(test_case)
        elif isinstance(test_case, TestMethod):
            return self._find_test_class(test_case) or \
                   self._create_test_class_for(test_case)

    def _create_test_module_for(self, test_case):
        """Create a new test module for a given test case. If the test module
        already existed, will raise a ModuleNeedsAnalysis exception.
        """
        test_name = test_module_name_for_test_case(test_case)
        test_path = self._path_for_test(test_name)
        if os.path.exists(test_path):
            raise ModuleNeedsAnalysis(test_path)
        return self.create_module(test_path)

    def _path_for_test(self, test_module_name):
        """Return a full path to test module with given name.
        """
        return os.path.join(self.path, self.new_tests_directory, test_module_name)

    def _find_test_module(self, test_case):
        """Find test module that will be good for the given test case.
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
        possible_paths = possible_test_module_paths(module, self.new_tests_directory)
        for module in self.get_modules():
            if module.subpath in possible_paths:
                return module

    def _find_associate_test_module_by_test_cases(self, module):
        """Try to find a test module with most test cases for the given
        application module.
        """
        def test_cases_number(mod):
            return len(mod.get_test_cases_for_module(module))
        test_module = max_by_not_zero(test_cases_number, self.get_modules())
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
        for mod in self.iter_modules():
            if module in [mod.subpath, mod.locator]:
                return mod
        raise ModuleNotFound(module)

    def get_modules(self):
        return self._modules.values()

    def iter_modules(self):
        return self._modules.values()

    def iter_classes(self):
        for module in self.iter_modules():
            for klass in module.classes:
                yield klass

    def iter_functions(self):
        for module in self.iter_modules():
            for function in module.functions:
                yield function

    def find_class(self, name, modulepath):
        modulename = self._extract_subpath(modulepath)
        try:
            for klass in self[modulename].classes:
                if klass.name == name:
                    return klass
        except ModuleNotFound:
            pass

    def find_function(self, name, modulepath):
        modulename = self._extract_subpath(modulepath)
        try:
            for function in self[modulename].functions:
                if function.name == name:
                    return function
        except ModuleNotFound:
            pass

class ObjectWrapper(object):
    pass

class Value(ObjectWrapper):
    """Wrapper of an object, which can be pickled, so we can save its real
    value.
    """
    can_be_constructed = True

    def __init__(self, object):
        self.value = object

    def __eq__(self, other):
        return isinstance(other, Value) and self.value == other.value

    def __hash__(self):
        return hash(self.value)

    def __repr__(self):
        return "Value(%r)" % self.value

class Type(ObjectWrapper):
    """Placeholder for an object that cannot be pickled, thus have to be
    remembered as type only.
    """
    can_be_constructed = False

    def __init__(self, object):
        self.type = type(object)

    def __eq__(self, other):
        return isinstance(other, Type) and self.type == other.type

    def __hash__(self):
        return hash(self.type)

    def __repr__(self):
        return "Type(%r)" % self.type

class Repr(ObjectWrapper):
    """Placeholder for an object which cannot be pickled and which type
    cannot be pickled as well, so it is remembered as its string representation
    only.
    """
    can_be_constructed = False

    def __init__(self, object):
        self.repr = repr(object)

    def __eq__(self, other):
        return isinstance(other, Repr) and self.repr == other.repr

    def __hash__(self):
        return hash(self.repr)

    def __repr__(self):
        return "Repr(%s)" % self.repr

def is_pickable(object):
    if isinstance(object, types.FunctionType):
        return False
    # TODO: handle more cases
    return True

def wrap_object(object):
    if is_pickable(object):
        return Value(object)
    elif is_pickable(type(object)):
        return Type(object)
    else:
        return Repr(object)

def wrap_call_arguments(input):
    new_input = {}
    for key, value in input.iteritems():
        new_input[key] = wrap_object(value)
    return new_input

class Call(object):
    """Stores information about a single function or method call.

    Includes reference to the caller, all call arguments, references to
    other calls made inside this one and finally an output value.

    There's more to function/method call than arguments and outputs.
    They're the only attributes for now, but information on side effects
    will be added later.

    __eq__ and __hash__ definitions provided for Function.get_unique_calls()
    and LiveObject.get_external_calls().
    """
    def __init__(self, callable, input, output=None, exception=None):
        if [value for value in input.values() if not isinstance(value, ObjectWrapper)]:
            raise ValueError("All input values should be instances of ObjectWrapper class.")
        if output and exception:
            raise ValueError("Call should have a single point of return.")

        self.callable = callable
        self.input = input
        self.output = output
        self.exception = exception

        self.caller = None
        self.subcalls = []

    def add_subcall(self, call):
        if call.caller is not None:
            raise TypeError("This Call already has a caller.")
        call.caller = self
        self.subcalls.append(call)

    def raised_exception(self):
        return self.exception is not None

    def set_output(self, output):
        self.output = wrap_object(output)

    def set_exception(self, exception):
        self.exception = wrap_object(exception)

    def clear_exception(self):
        self.exception = None

    def __eq__(self, other):
        return self.callable == other.callable and \
               self.input == other.input and \
               self.output == other.output and \
               self.exception == other.exception

    def __hash__(self):
        return hash((self.callable.name,
                     tuple(self.input.iteritems()),
                     self.output,
                     self.exception))

    def __repr__(self):
        return "%s(callable=%r, input=%r, output=%r, exception=%r)" % \
               (self.__class__.__name__, self.callable, self.input,
                self.output, self.exception)

class FunctionCall(Call):
    def __init__(self, point_of_entry, function, input, output=None, exception=None):
        Call.__init__(self, function, input, output, exception)
        self.point_of_entry = point_of_entry

class MethodCall(Call):
    pass

class Definition(object):
    def __init__(self, name, code=None):
        if code is None:
            code = EmptyCode()
        self.name = name
        self.code = code

class Callable(object):
    def __init__(self, calls=None):
        if calls is None:
            calls = []
        self.calls = calls

    def add_call(self, call):
        self.calls.append(call)

class Function(Definition, Callable):
    def __init__(self, name, code=None, calls=None):
        Definition.__init__(self, name, code)
        Callable.__init__(self, calls)

    def is_testable(self):
        return not self.name.startswith('_')

    def get_unique_calls(self):
        return set(self.calls)

    def remove_calls_from(self, point_of_entry):
        self.calls = [call for call in self.calls if call.point_of_entry is not point_of_entry]

    def __repr__(self):
        return "Function(name=%r, calls=%r)" % (self.name, self.calls)

# Methods are not Callable, because they cannot be called by itself - they
# need a bound object. We represent this object by LiveObject class, which
# gathers all MethodCalls for given instance.
class Method(Definition):
    pass

class LiveObject(Callable):
    """Representation of an object which creation and usage was traced
    during dynamic inspection.

    Note that the LiveObject.id is only unique to a given point of entry.
    In other words, it is possible to have two points of entry holding
    separate live objects with the same id. Use LiveObject.unique_id for
    identification purposes.
    """
    def __init__(self, id, klass, point_of_entry):
        self.id = id
        self.klass = klass
        self.point_of_entry = point_of_entry

        self.unique_id = (point_of_entry.name, id)
        self.calls = []

    def add_call(self, call):
        self.calls.append(call)

    def get_init_call(self):
        """Return a call to __init__ or None if it wasn't called.
        """
        return findfirst(lambda call: call.callable.name == '__init__', self.calls)

    def get_external_calls(self):
        """Return all calls to this object made from the outside.

        Note: __init__ is considered an internal call.
        """
        def is_not_init_call(call):
            return call.callable.name != '__init__'
        def is_external_call(call):
            return (not call.caller) or (call.caller not in self.calls)
        return filter(is_not_init_call, filter(is_external_call, self.calls))

    def __repr__(self):
        return "LiveObject(id=%d, klass=%r, calls=%r)" % (self.id, self.klass.name, self.calls)

class Class(object):
    def __init__(self, name, methods=[], bases=[]):
        self.name = name
        self.methods = methods
        self.bases = bases
        self.live_objects = {}

    def is_testable(self):
        ignored_superclasses = ['Exception', 'unittest.TestCase']
        for klass in ignored_superclasses:
            if klass in self.bases:
                return False
        return True

    def add_live_object(self, live_object):
        self.live_objects[live_object.unique_id] = live_object

    def remove_live_objects_from(self, point_of_entry):
        # We're removing elements, so iterate over a shallow copy.
        for id, live_object in self.live_objects.copy().iteritems():
            if live_object.point_of_entry is point_of_entry:
                del self.live_objects[id]

    def get_traced_method_names(self):
        traced_method_names = set()
        for live_object in self.live_objects.values():
            for call in live_object.calls:
                traced_method_names.add(call.callable.name)
        return traced_method_names

    def get_untraced_methods(self):
        traced_method_names = self.get_traced_method_names()
        def is_untraced(method):
            return method.name not in traced_method_names
        return filter(is_untraced, self.methods)

    def find_method_by_name(self, name):
        for method in self.methods:
            if method.name == name:
                return method

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

    def __init__(self, name, code=None, parent=None, test_cases=[], imports=None):
        TestCase.__init__(self, name, code, parent)

        if imports is None:
            imports = []

        self.changed = False
        self.test_cases = []
        self.imports = imports

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

    def ensure_imports(self, imports):
        "Make sure that all required imports are present."
        for imp in imports:
            self._ensure_import(imp)
        if self.parent:
            self.parent.ensure_imports(imports)

    def _ensure_import(self, import_desc):
        if not self._contains_import(import_desc):
            self.imports.append(import_desc)

    def _contains_import(self, import_desc):
        return import_desc in self.imports

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
        TestSuite.__init__(self, name, code, parent, test_cases, imports)

        if associated_modules is None:
            associated_modules = []

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
            remove_trailing_whitespace(code)
            suite = self.code.children[-1]
            # Prefix the definition with the right amount of whitespace.
            node = find_last_leaf(suite.children[-2])
            ident = get_starting_whitespace(suite)
            # There's no need to have extra newlines.
            if node.prefix.endswith("\n"):
                node.prefix += ident.lstrip("\n")
            else:
                node.prefix += ident
            # Insert before the class contents dedent.
            suite.insert_child(-1, code)
        else:
            self.code.append_child(code)
        self.mark_as_changed()

    def find_method_by_name(self, name):
        for method in self.test_cases:
            if method.name == name:
                return method

    def is_testable(self):
        return False

class Localizable(object):
    """An object which has a corresponding file belonging to some Project.

    Each Localizable has a 'path' attribute and an information when it was
    created, to be in sync with its file system counterpart. Path is always
    relative to the project this localizable belongs to.
    """
    def __init__(self, project, subpath, created=None):
        self.project = project
        self.subpath = subpath
        if created is None:
            created = time.time()
        self.created = created

    def _get_locator(self):
        return re.sub(r'(%s__init__)?\.py$' % os.path.sep, '', self.subpath).\
            replace(os.path.sep, ".")
    locator = property(_get_locator)

    def is_out_of_sync(self):
        """Is the object out of sync with its file.
        """
        return get_last_modification_time(self.get_path()) > self.created

    def is_up_to_date(self):
        return not self.is_out_of_sync()

    def get_path(self):
        """Return the full path to the file.
        """
        return os.path.join(self.project.path, self.subpath)

    def write(self, new_content):
        """Overwrite the file with new contents and update its created time.

        Creates the containing directories if needed.
        """
        ensure_directory(os.path.dirname(self.get_path()))
        write_string_to_file(new_content, self.get_path())
        self.created = time.time()

    def exists(self):
        return os.path.isfile(self.get_path())

class Module(Localizable, TestSuite):
    allowed_test_case_classes = [TestClass]

    def __init__(self, project, subpath, code=None, objects=None, imports=None,
                 main_snippet=None, errors=[]):
        if objects is None:
            objects = []
        test_cases = get_test_objects(objects)

        Localizable.__init__(self, project, subpath)
        TestSuite.__init__(self, self.locator, code, None, test_cases, imports)

        self.objects = objects
        self.main_snippet = main_snippet
        self.errors = errors

        # Code of test cases passed to the constructor is already contained
        # within the module code.
        self.add_test_cases(test_cases, False)

    def _get_testable_objects(self):
        return [o for o in self.objects if o.is_testable()]
    testable_objects = property(_get_testable_objects)

    def _get_classes(self):
        return all_of_type(self.objects, Class)
    classes = property(_get_classes)

    def _get_functions(self):
        return all_of_type(self.objects, Function)
    functions = property(_get_functions)

    def _get_test_classes(self):
        return all_of_type(self.objects, TestClass)
    test_classes = property(_get_test_classes)

    def add_test_case(self, test_case, append_code=True):
        TestSuite.add_test_case(self, test_case, append_code)

        self.ensure_imports(test_case.imports)
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

    def _ensure_main_snippet(self, main_snippet, force=False):
        """Make sure the main_snippet is present. Won't overwrite the snippet
        unless force flag is set.
        """
        if not main_snippet:
            return

        if not self.main_snippet:
            self.main_snippet = main_snippet
            self.code.append_child(main_snippet)
            self.mark_as_changed()
        elif force:
            self.main_snippet.replace(main_snippet)
            self.main_snippet = main_snippet
            self.mark_as_changed()

    def _ensure_import(self, import_desc):
        # Add an extra newline separating imports from the code.
        if not self.imports:
            self.code.insert_child(0, Newline())
            self.mark_as_changed()
        if not self._contains_import(import_desc):
            self._add_import(import_desc)

    def _add_import(self, import_desc):
        self.imports.append(import_desc)
        self.code.insert_child(0, create_import(import_desc))
        self.mark_as_changed()

    def _append_test_case_code(self, code):
        # If the main_snippet exists we have to put the new test case
        # before it. If it doesn't we put the test case at the end.
        if self.main_snippet:
            self._insert_before_main_snippet(code)
        else:
            self.code.append_child(code)
        self.mark_as_changed()

    def _insert_before_main_snippet(self, code):
        for i, child in enumerate(self.code.children):
            if child == self.main_snippet:
                self.code.insert_child(i, code)
                break

    def save(self):
        # Don't save the test file unless it has been changed.
        if self.changed:
            if self.is_out_of_sync():
                raise ModuleNeedsAnalysis(self.subpath, out_of_sync=True)
            try:
                self.write(self.get_content())
            except DirectoryException, err:
                raise ModuleSaveError(self.subpath, err.message)
            self.changed = False

class PointOfEntry(Localizable):
    """Piece of code provided by the user that allows dynamic analysis.

    In add_method_call/add_function_call if we can't find a class or function
    in Project, we don't care about it. This way we don't record any information
    about thid-party and dynamically created code.
    """
    def __init__(self, project, name):
        poes_subpath = project._extract_subpath(project._get_points_of_entry_path())
        Localizable.__init__(self, project, os.path.join(poes_subpath, name))

        self.name = name
        # After an inspection run, this will be a reference to the top level call.
        self.call_graph = None

        self._preserved_objects = []

    def get_path(self):
        return os.path.join(self.project._get_points_of_entry_path(), self.name)

    def get_content(self):
        return read_file_contents(self.get_path())

    def clear_previous_run(self):
        for klass in self.project.iter_classes():
            klass.remove_live_objects_from(self)
        for function in self.project.iter_functions():
            function.remove_calls_from(self)
        self.call_graph = None

    def create_method_call(self, name, classname, modulepath, object, input):
        klass = self.project.find_class(classname, modulepath)
        if not klass:
            return

        method = klass.find_method_by_name(name)
        if not method:
            return

        call = MethodCall(method, wrap_call_arguments(input))

        try:
            live_object = klass.live_objects[(self.name, id(object))]
        except KeyError:
            live_object = LiveObject(id(object), klass, self)
            klass.add_live_object(live_object)
            self._preserve(object)

        live_object.add_call(call)
        return call

    def create_function_call(self, name, modulepath, input):
        function = self.project.find_function(name, modulepath)

        if function:
            call = FunctionCall(self, function, wrap_call_arguments(input))
            function.add_call(call)
            return call

    def finalize_inspection(self):
        # We can release preserved objects now.
        self._preserved_objects = []

    def _preserve(self, object):
        """Preserve an object from garbage collection, so its id won't get
        occupied by any other object.
        """
        self._preserved_objects.append(object)

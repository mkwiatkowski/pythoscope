import cPickle
import itertools
import os
import re
import time
import types

from pythoscope.astvisitor import find_last_leaf, get_starting_whitespace, \
    is_node_of_type, remove_trailing_whitespace
from pythoscope.astbuilder import EmptyCode, Newline, create_import, \
    insert_after, insert_before, regenerate
from pythoscope.logger import log
from pythoscope.serializer import BuiltinException, ImmutableObject, \
    MapObject, UnknownObject, SequenceObject, SerializedObject, is_immutable, \
    is_sequence, is_mapping, is_builtin_exception
from pythoscope.compat import set
from pythoscope.util import all_of_type, module_path_to_name, \
     write_content_to_file, ensure_directory, DirectoryException, \
     get_last_modification_time, read_file_contents, is_generator_code, \
     extract_subpath, directories_under, findfirst, generator_has_ended, \
     map_values, class_name, module_name, starts_with_path, string2filename, \
     get_generator_from_frame


CREATIONAL_METHODS = ['__init__', '__new__']

########################################################################
## CodeTreesManager classes.
##
class CodeTreeNotFound(Exception):
    def __init__(self, module_subpath):
        Exception.__init__(self, "Couldn't find code tree for module %r." % module_subpath)
        self.module_subpath = module_subpath

class CodeTreesManager(object):
    def __init__(self, code_trees_path):
        raise NotImplementedError

    # :: (CodeTree, str) -> None
    def remember_code_tree(self, code_tree, module_subpath):
        raise NotImplementedError

    # :: str -> CodeTree
    def recall_code_tree(self, module_subpath):
        """Return code tree corresponding to a module located under given subpath.

        May raise CodeTreeNotFound exception.
        """
        raise NotImplementedError

    # :: str -> None
    def forget_code_tree(self, module_subpath):
        """Get rid of the CodeTree for a module located under given subpath.
        Do nothing if the module doesn't exist.
        """
        raise NotImplementedError

    def clear_cache(self):
        pass

class FilesystemCodeTreesManager(CodeTreesManager):
    """Manager of CodeTree instances that keeps at most one CodeTree instance
    in a memory, storing the rest in files.
    """
    def __init__(self, code_trees_path):
        self.code_trees_path = code_trees_path
        self._cached_code_tree = None

    def remember_code_tree(self, code_tree, module_subpath):
        log.debug("Saving code tree for module %r to a file and caching..." % \
                      module_subpath)
        code_tree.save(self._code_tree_path(module_subpath))
        self._cache(code_tree, module_subpath)

    def recall_code_tree(self, module_subpath):
        if self._is_cached(module_subpath):
            return self._cached_code_tree[1]
        try:
            log.debug("Loading code tree for module %r from a file and caching..." % \
                          module_subpath)
            code_tree = CodeTree.load(self._code_tree_path(module_subpath))
            self._cache(code_tree, module_subpath)
            return code_tree
        except IOError:
            raise CodeTreeNotFound(module_subpath)

    def forget_code_tree(self, module_subpath):
        try:
            os.remove(self._code_tree_path(module_subpath))
        except OSError:
            pass
        self._remove_from_cache(module_subpath)

    def clear_cache(self):
        if self._cached_code_tree:
            old_module_subpath, old_code_tree = self._cached_code_tree
            log.debug("Code tree for module %r gets out of cache, "\
                          "saving to a file..." %  old_module_subpath)
            old_code_tree.save(self._code_tree_path(old_module_subpath))
        self._cached_code_tree = None

    def _cache(self, code_tree, module_subpath):
        self.clear_cache()
        self._cached_code_tree = (module_subpath, code_tree)

    def _is_cached(self, module_subpath):
        return self._cached_code_tree and self._cached_code_tree[0] == module_subpath

    def _remove_from_cache(self, module_subpath):
        if self._is_cached(module_subpath):
            self._cached_code_tree = None

    def _code_tree_path(self, module_subpath):
        code_tree_filename = string2filename(module_subpath) + '.pickle'
        return os.path.join(self.code_trees_path, code_tree_filename)

########################################################################
## Project class and helpers.
##
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

PYTHOSCOPE_SUBPATH = ".pythoscope"
PICKLE_SUBPATH = os.path.join(PYTHOSCOPE_SUBPATH, "project.pickle")
POINTS_OF_ENTRY_SUBPATH = os.path.join(PYTHOSCOPE_SUBPATH, "points-of-entry")

def get_pythoscope_path(project_path):
    return os.path.join(project_path, PYTHOSCOPE_SUBPATH)
def get_pickle_path(project_path):
    return os.path.join(project_path, PICKLE_SUBPATH)
def get_points_of_entry_path(project_path):
    return os.path.join(project_path, POINTS_OF_ENTRY_SUBPATH)

def get_code_trees_path(project_path):
    return os.path.join(get_pythoscope_path(project_path), "code-trees")

def get_test_objects(objects):
    def is_test_object(object):
        return isinstance(object, TestCase)
    return filter(is_test_object, objects)

def load_pickle_from(path):
    fd = open(path, 'rb')
    obj = cPickle.load(fd)
    fd.close()
    return obj

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
            project = load_pickle_from(get_pickle_path(project_path))
            # Update project's path, as the directory could've been moved.
            project.path = project_path
        except IOError:
            project = Project(project_path)
        return project
    from_directory = classmethod(from_directory)

    def __init__(self, path, code_trees_manager_class=FilesystemCodeTreesManager):
        """Initialize a Project instance using the given path as the project's
        top directory.

        During normal operation code_trees_manager_class is the class that
        the Project delegates to all CodeTree management tasks, but during
        testing this can be replaced with something else, possibly a class
        that doesn't touch the file system.
        """
        self.path = path
        self.new_tests_directory = "tests"
        self.points_of_entry = {}
        self._modules = {}
        self.code_trees_manager = code_trees_manager_class(get_code_trees_path(path))

        self._find_new_tests_directory()

    def _get_pickle_path(self):
        return get_pickle_path(self.path)

    def get_points_of_entry_path(self):
        return get_points_of_entry_path(self.path)

    def path_for_point_of_entry(self, name):
        return os.path.join(self.path, self.subpath_for_point_of_entry(name))

    def subpath_for_point_of_entry(self, name):
        return os.path.join(POINTS_OF_ENTRY_SUBPATH, name)

    def _find_new_tests_directory(self):
        for path in directories_under(self.path):
            if re.search(r'[_-]?tests?([_-]|$)', path):
                self.new_tests_directory = path

    def save(self):
        # To avoid inconsistencies try to save all project's modules first. If
        # any of those saves fail, the pickle file won't get updated.
        for module in self.get_modules():
            log.debug("Calling save() on module %r" % module.subpath)
            module.save()

        # We don't want to have a single AST in a Project instance.
        self.code_trees_manager.clear_cache()

        # Pickling the project after saving all of its modules, so any changes
        # made by Module instances during save() will be preserved as well.
        pickled_project = cPickle.dumps(self, cPickle.HIGHEST_PROTOCOL)

        log.debug("Writing project pickle to disk...")
        write_content_to_file(pickled_project, self._get_pickle_path(), binary=True)

    def find_module_by_full_path(self, path):
        subpath = self._extract_subpath(path)
        return self[subpath]

    def ensure_point_of_entry(self, path):
        name = self._extract_point_of_entry_subpath(path)
        if name not in self.points_of_entry:
            poe = PointOfEntry(project=self, name=name)
            self.points_of_entry[name] = poe
        return self.points_of_entry[name]

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
            # Don't need to forget the old CallTree, as the creation of
            # the Module instance above overwrites it anyway.

        self._modules[module.subpath] = module

        return module

    def create_test_module_from_name(self, test_name):
        """Create a module with given name in project tests directory.

        If the test module already exists, ModuleNeedsAnalysis exception will
        be raised.
        """
        test_path = self._path_for_test(test_name)
        if os.path.exists(test_path):
            raise ModuleNeedsAnalysis(test_path)
        return self.create_module(test_path)

    def remove_module(self, subpath):
        """Remove a module from this Project along with all references to it
        from other modules and its CodeTree.
        """
        module = self[subpath]
        for test_case in self.iter_test_cases():
            try:
                test_case.associated_modules.remove(module)
            except ValueError:
                pass
        del self._modules[subpath]
        self.code_trees_manager.forget_code_tree(module.subpath)

    # :: (CodeTree, Module) -> None
    def remember_code_tree(self, code_tree, module):
        self.code_trees_manager.remember_code_tree(code_tree, module.subpath)

    # :: Module -> CodeTree
    def recall_code_tree(self, module):
        return self.code_trees_manager.recall_code_tree(module.subpath)

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
        return extract_subpath(path, self.get_points_of_entry_path())

    def _extract_subpath(self, path):
        """Takes the file path and returns subpath relative to the
        project.

        Assumes the given path is under Project.path.
        """
        return extract_subpath(path, self.path)

    def contains_path(self, path):
        """Returns True if given path is under this project's path and False
        otherwise.
        """
        return starts_with_path(path, self.path)

    def iter_test_cases(self):
        for module in self.iter_modules():
            for test_case in module.test_cases:
                yield test_case

    def _path_for_test(self, test_module_name):
        """Return a full path to test module with given name.
        """
        return os.path.join(self.path, self.new_tests_directory, test_module_name)

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

    def iter_generator_objects(self):
        for module in self.iter_modules():
            for generator in module.generators:
                for gobject in generator.calls:
                    yield gobject

    def find_object(self, type, name, modulename):
        try:
            for obj in all_of_type(self[modulename].objects, type):
                if obj.name == name:
                    return obj
        except ModuleNotFound:
            pass

class Call(object):
    """Stores information about a single function or method call.

    Includes reference to the caller, all call arguments, references to
    other calls made inside this one and finally an output value.

    There's more to function/method call than arguments and outputs.
    They're the only attributes for now, but information on side effects
    will be added later.

    __eq__ and __hash__ definitions provided for Function.get_unique_calls()
    and UserObject.get_external_calls().
    """
    def __init__(self, definition, args, output=None, exception=None):
        if [value for value in args.values() if not isinstance(value, SerializedObject)]:
            raise ValueError("Values of all arguments should be instances of SerializedObject class.")
        if output and exception:
            raise ValueError("Call should have a single point of return.")
        if not isinstance(definition, Definition):
            raise ValueError("Call definition object should be an instance of Definition.")

        self.definition = definition
        self.input = args
        self.output = output
        self.exception = exception

        self.caller = None
        self.subcalls = []

    def add_subcall(self, call):
        # Don't add the same GeneratorObject more than once.
        if isinstance(call, GeneratorObject) and call.caller is self:
            return
        if call.caller is not None:
            raise TypeError("This %s of %s already has a caller." % \
                                (class_name(call), call.definition.name))
        call.caller = self
        self.subcalls.append(call)

    def raised_exception(self):
        return self.exception is not None

    def set_output(self, output):
        self.output = output

    def set_exception(self, exception):
        self.exception = exception

    def clear_exception(self):
        self.exception = None

    def is_testable(self):
        return True

    def __eq__(self, other):
        return self.definition == other.definition and \
               self.input == other.input and \
               self.output == other.output and \
               self.exception == other.exception

    def __hash__(self):
        return hash((self.definition.name,
                     tuple(self.input.iteritems()),
                     self.output,
                     self.exception))

    def __repr__(self):
        return "%s(definition=%s, input=%r, output=%r, exception=%r)" % \
            (class_name(self), self.definition.name, self.input, self.output,
             self.exception)

class FunctionCall(Call):
    pass

class MethodCall(Call):
    pass

class ObjectInModule(object):
    """Named object that can be localized in a module via the AST.

    Note that the code attribute will be removed from the object once it
    becomes a part of a Module.
    """
    def __init__(self, name, code):
        self.name = name
        if code is None:
            code = EmptyCode()
        self.code = code

class Definition(ObjectInModule):
    """Definition of a callable object (function or a method basically),
    describing its static properties.
    """
    def __init__(self, name, args=None, code=None, is_generator=False):
        ObjectInModule.__init__(self, name, code)
        if args is None:
            args = []
        self.args = args
        self.is_generator = is_generator

    def is_vararg(self, name):
        """Return True if given string names a vararg argument for this
        definition.
        """
        return ("*%s" % name) in self.args

    def is_kwarg(self, name):
        """Return True if given string names a kwarg argument for this
        definition.
        """
        return ("**%s" % name) in self.args

class Callable(object):
    """Dynamic aspect of a callable object. Tracks all calls made to given
    callable.
    """
    def __init__(self, calls=None):
        if calls is None:
            calls = []
        self.calls = calls

    def add_call(self, call):
        # Don't add the same GeneratorObject more than once.
        if isinstance(call, GeneratorObject) and call in self.calls:
            return
        self.calls.append(call)

class Function(Definition, Callable):
    def __init__(self, name, args=None, code=None, calls=None, is_generator=False, module=None):
        Definition.__init__(self, name, args=args, code=code, is_generator=is_generator)
        Callable.__init__(self, calls)
        self.module = module

    def is_testable(self):
        return not self.name.startswith('_')

    def get_unique_calls(self):
        return set(self.calls)

    def __repr__(self):
        return "Function(name=%s, args=%r, calls=%r)" % (self.name, self.args, self.calls)

# Methods are not Callable, because they cannot be called by itself - they
# need a bound object. We represent this object by UserObject class, which
# gathers all MethodCalls for given instance.
class Method(Definition):
    def __init__(self, name, args=None, code=None, is_generator=False, klass=None):
        Definition.__init__(self, name, args=args, code=code, is_generator=is_generator)
        self.klass = klass

    def get_call_args(self):
        """Return names of arguments explicitly passed during call to this
        method.

        In other words, it removes "self" from the list of arguments, as "self"
        is passed implicitly.
        """
        if self.args and self.args[0].startswith('*'):
            return self.args
        return self.args[1:]

    def is_creational(self):
        return self.name in CREATIONAL_METHODS

    def is_private(self):
        """Private methods (by convention) start with a single or double
        underscore.

        Note: Special methods are *not* considered private.
        """
        return self.name.startswith('_') and not self.is_special()

    def is_special(self):
        """Special methods, as defined in
        <http://docs.python.org/reference/datamodel.html#specialnames>
        have names starting and ending with a double underscore.
        """
        return self.name.startswith('__') and self.name.endswith('__')

    def __repr__(self):
        return "Method(name=%s, args=%r)" % (self.name, self.args)

class GeneratorObject(Call):
    """Representation of a generator object - a callable with an input and many
    outputs (here called "yields").

    Although a generator object execution is not a single call, but consists of
    a series of suspensions and resumes, we make it conform to the Call interface
    for simplicity.
    """
    def __init__(self, generator, args, yields=None, exception=None):
        if yields is None:
            yields = []
        Call.__init__(self, generator, args, yields, exception)

    def set_output(self, output):
        self.output.append(output)

    def is_testable(self):
        return self.raised_exception() or self.output

    def __hash__(self):
        return hash((self.definition.name,
                     tuple(self.input.iteritems()),
                     tuple(self.output),
                     self.exception))

    def __repr__(self):
        return "GeneratorObject(generator=%r, yields=%r)" % \
               (self.definition.name, self.output)

class UserObject(Callable, SerializedObject):
    """Serialized instance of a user-defined type.

    UserObjects are also callables that aggregate MethodCall instances,
    capturing the whole life of an object, from initialization to destruction.
    """
    def __init__(self, obj, klass):
        Callable.__init__(self)
        SerializedObject.__init__(self, obj)
        self.klass = klass
        self.type_name = self.klass.name

    # Defined lazily to ease testing - classes may be assigned to modules after
    # creation of UserObject, or never at all.
    module_name = property(lambda self: self.klass.module.locator, lambda s,v: None)

    def get_init_call(self):
        """Return a call to __init__ or None if it wasn't called.
        """
        return findfirst(lambda call: call.definition.name == '__init__', self.calls)

    def get_external_calls(self):
        """Return all calls to this object made from the outside.

        Note: __init__ is considered an internal call.
        """
        def is_not_init_call(call):
            return call.definition.name != '__init__'
        def is_external_call(call):
            return (not call.caller) or (call.caller not in self.calls)
        return filter(is_not_init_call, filter(is_external_call, self.calls))

    def __repr__(self):
        return "UserObject(klass=%r, calls=%r)" % (self.klass.name, self.calls)

class Class(ObjectInModule):
    def __init__(self, name, methods=[], bases=[], code=None, module=None):
        ObjectInModule.__init__(self, name, code)
        self.methods = []
        self.bases = bases
        self.module = module
        self.user_objects = []

        self.add_methods(methods)

    def _set_class_for_method(self, method):
        if method.klass is not None:
            raise TypeError("Trying to add %r to class %r, while the "
                            "method is already inside %r." % \
                                (method, self.name, method.klass.name))
        method.klass = self

    def add_methods(self, methods):
        for method in methods:
            self._set_class_for_method(method)
            self.methods.append(method)

    def is_testable(self):
        ignored_superclasses = ['Exception', 'unittest.TestCase']
        for klass in ignored_superclasses:
            if klass in self.bases:
                return False
        return True

    def add_user_object(self, user_object):
        self.user_objects.append(user_object)

    def get_traced_method_names(self):
        traced_method_names = set()
        for user_object in self.user_objects:
            for call in user_object.calls:
                traced_method_names.add(call.definition.name)
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

    def get_creational_method(self):
        """Return either __new__ or __init__ method of this class, with __new__
        taking precedence.
        """
        method = self.find_method_by_name('__new__')
        if method:
            return method
        return self.find_method_by_name('__init__')

    def __repr__(self):
        return "Class(name=%s)" % self.name

class TestCase(object):
    """A single test object, possibly contained within a test suite (denoted
    as parent attribute).
    """
    def __init__(self, parent=None):
        self.parent = parent

    def replace_itself_with(self, new_test_case):
        self.parent.replace_test_case(self, new_test_case)

class TestSuite(TestCase):
    """A test objects container.

    Keeps both test cases and other test suites in test_cases attribute.
    """
    allowed_test_case_classes = []

    def __init__(self, parent=None, imports=None):
        TestCase.__init__(self, parent)

        if imports is None:
            imports = []
        self.imports = imports

        self.changed = False
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

    def _remove_test_case(self, test_case):
        """Try to remove given test case from this test suite.

        Raise ValueError if the given test case is not a part of thise test
        suite.

        Note: this method doesn't modify the AST of the test suite.
        """
        try:
            self.test_cases.remove(test_case)
        except ValueError:
            raise ValueError("Given test case is not a part of this test suite.")

    def replace_test_case(self, old_test_case, new_test_case):
        """Replace one test case object with another.

        As a side effect, AST of the new test case will replace part of the AST
        in the old test case parent.

        `Code` attribute of the new test case object will be removed.
        """
        # The easiest way to get the new code inside the AST is to call
        # replace() on the old test case code.
        # It is destructive, but since we're discarding the old test case
        # anyway, it doesn't matter.
        code_of(old_test_case).replace(new_test_case.code)

        self._remove_test_case(old_test_case)
        self.add_test_case(new_test_case, append_code=False)
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

class TestMethod(ObjectInModule, TestCase):
    def __init__(self, name, code=None, parent=None):
        ObjectInModule.__init__(self, name, code)
        TestCase.__init__(self, parent)

class TestClass(ObjectInModule, TestSuite):
    """Testing class, either generated by Pythoscope or hand-writen by the user.

    Each test class contains a set of requirements its surrounding must meet,
    like the list of imports it needs or specific setup and teardown
    instructions.

    associated_modules is a list of Modules which this test class exercises.
    """
    allowed_test_case_classes = [TestMethod]

    def __init__(self, name, code=None, parent=None, test_cases=[],
                 imports=None, associated_modules=None):
        ObjectInModule.__init__(self, name, code)
        TestSuite.__init__(self, parent, imports)

        if associated_modules is None:
            associated_modules = []

        self.associated_modules = associated_modules

        # Code of test cases passed to the constructor is already contained
        # within the class code, so we don't need to append it.
        self.add_test_cases(test_cases, append_code=False)

    def _get_methods(self):
        return self.test_cases
    methods = property(_get_methods)

    def add_test_case(self, test_case, append_code=True):
        TestSuite.add_test_case(self, test_case, append_code)

        if self.parent is not None:
            CodeTree.of(self).add_object_with_code(test_case)
        else:
            # This TestClass is not attached to a Module yet. We will leave
            # the just-added test case as it is and let Module instance handle
            # the rest when the time comes (see `Module#add_object`).
            pass

    def _append_test_case_code(self, code):
        """Append to the right node, so that indentation level of the
        new method is good.
        """
        if code_of(self).children and is_node_of_type(code_of(self).children[-1], 'suite'):
            remove_trailing_whitespace(code)
            suite = code_of(self).children[-1]
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
            code_of(self).append_child(code)
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
        return module_path_to_name(self.subpath, newsep=".")
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
        write_content_to_file(new_content, self.get_path())
        self.created = time.time()

    def exists(self):
        return os.path.isfile(self.get_path())

class Module(Localizable, TestSuite):
    allowed_test_case_classes = [TestClass]

    def __init__(self, project, subpath, code=None, objects=None, imports=None,
                 main_snippet=None, last_import=None, errors=[]):
        if objects is None:
            objects = []

        Localizable.__init__(self, project, subpath)
        TestSuite.__init__(self, imports=imports)

        if code is None:
            code = EmptyCode()

        # Persistence of CodeTree instances is managed by the Project instance.
        code_tree = CodeTree(code)
        project.remember_code_tree(code_tree, self)

        self.objects = []
        self.errors = errors

        self._store_reference('main_snippet', main_snippet)
        self._store_reference('last_import', last_import)

        self.add_objects(objects)

    def _set_module_for_object(self, obj):
        if isinstance(obj, (Class, Function)):
            if obj.module is not None:
                raise TypeError("Trying to add %r to module %r, while the "
                                "object is already inside %r." % \
                                    (obj, self.locator, obj.module.locator))
            obj.module = self

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

    def _store_reference(self, name, code):
        CodeTree.of(self).add_object(name, code)

    def add_objects(self, objects):
        """Add objects to this module.

        Note: AST of those objects will *not* be appended to the module's AST.
        """
        for obj in objects:
            # Adding a test case requires some extra effort than adding
            # a regular object, but they all land in `self.objects` list anyway.
            if isinstance(obj, TestCase):
                # By using the `add_objects()` interface user states that
                # the code of objects passed is already contained within
                # the module code, so we don't need to append it.
                self.add_test_case(obj, append_code=False)
            else:
                self.add_object(obj)

    def add_object(self, obj):
        self._set_module_for_object(obj)
        self.objects.append(obj)
        CodeTree.of(self).add_object_with_code(obj)

        # When attaching a class to a module we not only have to store its own
        # code reference, but also code references of its methods.
        if isinstance(obj, (Class, TestClass)):
            for method in obj.methods:
                CodeTree.of(self).add_object_with_code(method)

    def remove_object(self, obj):
        self.objects.remove(obj)
        CodeTree.of(self).remove_object(obj)

    def add_test_case(self, test_case, append_code=True):
        TestSuite.add_test_case(self, test_case, append_code)
        self.add_object(test_case)
        self.ensure_imports(test_case.imports)

    def _remove_test_case(self, test_case):
        TestSuite._remove_test_case(self, test_case)
        self.remove_object(test_case)

    # def replace_test_case:
    #   Using the default definition. We don't remove imports because we may
    #   unintentionally break something.

    def get_content(self):
        return regenerate(code_of(self))

    def get_test_cases_for_module(self, module):
        """Return all test cases that are associated with given module.
        """
        return [tc for tc in self.test_cases if module in tc.associated_modules]

    def ensure_main_snippet(self, main_snippet, force=False):
        """Make sure the main_snippet is present. Won't overwrite the snippet
        unless force flag is set.
        """
        if not main_snippet:
            return
        current_main_snippet = code_of(self, 'main_snippet')

        if not current_main_snippet:
            code_of(self).append_child(main_snippet)
            self._store_reference('main_snippet', main_snippet)
            self.mark_as_changed()
        elif force:
            current_main_snippet.replace(main_snippet)
            self._store_reference('main_snippet', main_snippet)
            self.mark_as_changed()

    def _ensure_import(self, import_desc):
        # Add an extra newline separating imports from the code.
        if not self.imports:
            code_of(self).insert_child(0, Newline())
            self.mark_as_changed()
        if not self._contains_import(import_desc):
            self._add_import(import_desc)

    def _add_import(self, import_desc):
        self.imports.append(import_desc)
        self._insert_after_other_imports(create_import(import_desc))
        self.mark_as_changed()

    def _insert_after_other_imports(self, code):
        last_import = code_of(self, 'last_import')
        if last_import:
            insert_after(last_import, code)
        else:
            code_of(self).insert_child(0, code)
        # Just inserted import becomes the last one.
        self._store_reference('last_import', code)

    def _append_test_case_code(self, code):
        # If the main_snippet exists we have to put the new test case
        # before it. If it doesn't we put the test case at the end.
        main_snippet = code_of(self, 'main_snippet')
        if main_snippet:
            insert_before(main_snippet, code)
        else:
            code_of(self).append_child(code)
        self.mark_as_changed()

    def save(self):
        # Don't save the test file unless it has been changed.
        if self.changed:
            if self.is_out_of_sync():
                raise ModuleNeedsAnalysis(self.subpath, out_of_sync=True)
            try:
                self.write(self.get_content())
            except DirectoryException, err:
                raise ModuleSaveError(self.subpath, err.args[0])
            self.changed = False

def object_id(obj):
    # The reason why we index generator by its code id is because at the time
    # of GeneratorObject creation we don't have access to the generator itself,
    # only to its code. See `Execution.create_call` for details.
    if isinstance(obj, types.GeneratorType):
        return id(obj.gi_frame.f_code)
    else:
        return id(obj)

class Execution(object):
    """A single run of a user application.

    To start an execution context, simply create a new Execution() object.
        >>> e = Execution(Project("."))
        >>> e.ended is None
        True

    When you're done tracing, call the finalize() method. Objects protected
    from the garbage collector will be released and the execution context
    will be closed:
        >>> e.finalize()
        >>> e.ended is not None
        True

    To erase any information collected during this run, call the destroy()
    method:
        >>> e.destroy()

    In create_method_call/create_function_call if we can't find a class or
    function in Project, we don't care about it. This way we don't record any
    information about thid-party and dynamically created code.
    """
    def __init__(self, project):
        self.project = project

        self.started = time.time()
        self.ended = None

        # References to objects and calls created during the run.
        self.captured_objects = {}
        self.captured_calls = []

        # After an inspection run, this will be a reference to the top level
        # call. Call graph can be traveresed by descending to `subcalls`
        # attribute of a call.
        self.call_graph = None

        # References to objects we don't want to be garbage collected just yet.
        self._preserved_objects = []

    def finalize(self):
        """Mark execution as finished.
        """
        self._preserved_objects = []
        self.ended = time.time()
        self._fix_generator_objects()

    def destroy(self):
        """Erase any serialized objects and references created during this run.
        """
        self.destroy_references()
        self.captured_objects = {}
        self.captured_calls = []
        self.call_graph = None

    def destroy_references(self):
        for obj in itertools.chain(self.captured_calls, self.captured_objects.values()):
            # Method calls will also be erased, implicitly during removal of
            # their UserObjects.
            if isinstance(obj, UserObject):
                obj.klass.user_objects.remove(obj)
            # FunctionCalls and GeneratorObjects have to be removed from their
            # definition classes.
            elif isinstance(obj, (FunctionCall, GeneratorObject)):
                obj.definition.calls.remove(obj)
            # Other serializables, like ImmutableObject are not referenced from
            # anywhere outside of calls in self.captured_calls.

    # :: object -> SerializedObject
    def serialize(self, obj):
        """Return description of the given object in the form of a subclass of
        SerializedObject.
        """
        def create_serialized_object():
            return self.create_serialized_object(obj)
        return self._retrieve_or_capture(obj, create_serialized_object)

    # :: {str: object, ...} -> {str: SerializedObject, ...}
    def serialize_call_arguments(self, args):
        return map_values(self.serialize, args)

    # :: object -> SerializedObject
    def create_serialized_object(self, obj):
        klass = self.project.find_object(Class, class_name(obj), module_name(obj))
        if klass:
            serialized = UserObject(obj, klass)
            klass.add_user_object(serialized)
            return serialized
        elif is_immutable(obj):
            return ImmutableObject(obj)
        elif is_sequence(obj):
            return SequenceObject(obj, self.serialize)
        elif is_mapping(obj):
            return MapObject(obj, self.serialize)
        elif is_builtin_exception(obj):
            return BuiltinException(obj, self.serialize)
        else:
            return UnknownObject(obj)

    # :: (Definition, dict, frame) -> GeneratorObject
    def create_generator_object(self, definition, sargs, frame):
        gobject = GeneratorObject(definition, sargs)
        # Generator objects return None to the tracer when stopped. That
        # extra None we have to filter out manually (see
        # _fix_generator_objects method). We distinguish between active
        # and stopped generators using the generator_has_ended() function.
        # It needs the generator object itself, so we save it for later
        # inspection inside the GeneratorObject.
        gobject._generator = get_generator_from_frame(frame)
        return gobject

    # :: (type, Definition, Callable, args, code, frame) -> Call
    def create_call(self, call_type, definition, callable, args, code, frame):
        sargs = self.serialize_call_arguments(args)
        if is_generator_code(code):
            # Each generator invocation is related to some generator object,
            # so we have to create one if it wasn't captured yet.
            def create_generator_object():
                return self.create_generator_object(definition, sargs, frame)
            call = self._retrieve_or_capture(code, create_generator_object)
        else:
            call = call_type(definition, sargs)
            self.captured_calls.append(call)
        callable.add_call(call)
        return call

    # :: (str, object, dict, code, frame) -> MethodCall | None
    def create_method_call(self, name, obj, args, code, frame):
        serialized_object = self.serialize(obj)

        # We ignore the call if we can't find the class of this object.
        if isinstance(serialized_object, UserObject):
            method = serialized_object.klass.find_method_by_name(name)
            if method:
                return self.create_call(MethodCall, method, serialized_object, args, code, frame)
            else:
                # TODO: We're lacking a definition of a method in a known class,
                # so at least issue a warning.
                pass

    # :: (str, dict, code, frame) -> FunctionCall | None
    def create_function_call(self, name, args, code, frame):
        if self.project.contains_path(code.co_filename):
            modulename = self.project._extract_subpath(code.co_filename)
            function = self.project.find_object(Function, name, modulename)
            if function:
                return self.create_call(FunctionCall, function, function,
                                        args, code, frame)

    def _retrieve_or_capture(self, obj, capture_callback):
        """Return existing description of the given object or create and return
        new one if the description wasn't captured yet.

        Preserves identity of objects, by storing them in `captured_objects`
        list.
        """
        try:
            return self.captured_objects[object_id(obj)]
        except KeyError:
            captured = capture_callback()
            self._preserve(obj)
            self.captured_objects[object_id(obj)] = captured
            return captured

    def _preserve(self, obj):
        """Preserve an object from garbage collection, so its id won't get
        occupied by any other object.
        """
        self._preserved_objects.append(obj)

    def iter_captured_generator_objects(self):
        return all_of_type(self.captured_objects.values(), GeneratorObject)

    def _fix_generator_objects(self):
        """Remove last yielded values of generator objects, as those are
        just bogus Nones placed on generator stop.
        """
        for gobject in self.iter_captured_generator_objects():
            if generator_has_ended(gobject._generator) \
                   and gobject.output \
                   and gobject.output[-1] == ImmutableObject(None):
                gobject.output.pop()
            # Once we know if the generator is active or not, we can discard it.
            del gobject._generator

class PointOfEntry(Localizable):
    """Piece of code provided by the user that allows dynamic analysis.

    Each point of entry keeps a reference to its last run in the `execution`
    attribute.
    """
    def __init__(self, project, name):
        Localizable.__init__(self, project, project.subpath_for_point_of_entry(name))

        self.project = project
        self.name = name
        self.execution = Execution(project)

    def _get_created(self):
        "Points of entry are not up-to-date until they're run."
        return self.execution.ended or 0
    def _set_created(self, value):
        pass
    created = property(_get_created, _set_created)

    def get_path(self):
        return self.project.path_for_point_of_entry(self.name)

    def get_content(self):
        return read_file_contents(self.get_path())

    def clear_previous_run(self):
        self.execution.destroy()
        self.execution = Execution(self.project)

########################################################################
## CodeTree and helper functions.
##
class CodeTree(object):
    """Container of a module's AST (from lib2to3.pytree).

    Each Module object has one corresponding CodeTree instance, which holds
    its whole AST in the `code` attribute. Moreover, references to subtrees
    inside this AST correspond to definitions inside a Module, and are stored
    inside a `code_references` attribute.

    Modules are identified by their subpath, which (within the scope of
    a project) is known to be unique. CodeTree instance doesn't need to know
    this subpath. It is used only by the Project class, for identification
    of modules and ultimately - storage and retrieval of CodeTree instances
    (see Project#remember_code_tree and Project#recall_code_tree methods).

    CodeTree instances are not saved to disk unless the save() method is
    called on them. They also will *not* be accesible  via `CodeTree.of()`
    interface unless you remember them in a Project instance first (see
    Project#remember_code_tree).
    """
    def of(cls, obj):
        """Return a CodeTree instance that handles code of the given object.
        """
        module = module_of(obj)
        return module.project.recall_code_tree(module)
    of = classmethod(of)

    def __init__(self, code):
        self.code = code
        self.code_references = {}

    def add_object(self, obj, code):
        self.code_references[module_level_id(obj)] = code

    def add_object_with_code(self, obj):
        """Take an object holding an AST in its `code` attribute and store it
        as a part of this CodeTree.

        As a side effect, `code` attribute is removed. The object will no
        longer hold any references to the AST, so they can be pickled
        separately.
        """
        self.add_object(obj, obj.code)
        del obj.code

    def remove_object(self, obj):
        del self.code_references[module_level_id(obj)]

    def get_code_of(self, obj):
        if isinstance(obj, Module):
            return self.code
        return self.code_references[module_level_id(obj)]

    def save(self, path):
        """Pickle and save this CodeTree under given path.
        """
        pickled_code_tree = cPickle.dumps(self, cPickle.HIGHEST_PROTOCOL)
        write_content_to_file(pickled_code_tree, path, binary=True)

    def load(cls, path):
        return load_pickle_from(path)
    load = classmethod(load)

def module_of(obj):
    """Return the Module given object is contained within.
    """
    if isinstance(obj, Module):
        return obj
    elif isinstance(obj, (Function, Class)):
        return obj.module
    elif isinstance(obj, Method):
        return module_of(obj.klass)
    elif isinstance(obj, TestCase):
        return module_of(obj.parent)
    else:
        raise TypeError("Don't know how to find the module of %r" % obj)

# :: ObjectInModule | str -> hashable
def module_level_id(obj):
    """Take an object and return something that unambiguously identifies
    it in the scope of its module.
    """
    if isinstance(obj, Class):
        return ('Class', obj.name)
    elif isinstance(obj, Function):
        return ('Function', obj.name)
    elif isinstance(obj, Method):
        return ('Method', (obj.klass.name, obj.name))
    elif isinstance(obj, TestClass):
        return ('TestClass', obj.name)
    elif isinstance(obj, TestMethod):
        return ('TestMethod', (obj.parent.name, obj.name))
    elif isinstance(obj, str):
        return obj
    else:
        raise TypeError("Don't know how to generate a module-level id for %r" % obj)

def code_of(obj, reference=None):
    """Return an AST for the given object.

    It is "code_of(obj)" instead of "obj.code" mostly for explicitness. Objects
    have code attribute when they are created, but lose it once they are added
    to a Module (see docstring for ObjectInModule). Existence of code_of
    decouples a storage method (including caching) from an interface.
    """
    if reference is not None:
        assert isinstance(obj, Module)
    else:
        reference = obj
    return CodeTree.of(obj).get_code_of(reference)

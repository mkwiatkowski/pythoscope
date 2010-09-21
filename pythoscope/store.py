import cPickle
import os
import re

from pythoscope.astbuilder import regenerate
from pythoscope.code_trees_manager import FilesystemCodeTreesManager
from pythoscope.compat import set
from pythoscope.event import Event
from pythoscope.localizable import Localizable
from pythoscope.logger import log
from pythoscope.serializer import SerializedObject
from pythoscope.util import all_of_type, assert_argument_type, class_name,\
    directories_under, extract_subpath, findfirst, load_pickle_from,\
    starts_with_path, write_content_to_file, DirectoryException

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
        self.snippet_executions = []
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

    def contains_point_of_entry(self, name):
        return name in self.points_of_entry

    def get_point_of_entry(self, name):
        return self.points_of_entry[name]

    def add_point_of_entry(self, poe):
        self.points_of_entry[poe.name] = poe

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

    def create_test_module_from_name(self, test_name, **kwds):
        """Create a module with given name in project tests directory.

        If the test module already exists, ModuleNeedsAnalysis exception will
        be raised.
        """
        test_path = self._path_for_test(test_name)
        if os.path.exists(test_path):
            raise ModuleNeedsAnalysis(test_path)
        return self.create_module(test_path, **kwds)

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

    def remember_execution_from_snippet(self, execution):
        self.snippet_executions.append(execution)

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

    def find_object(self, type, name, modulename):
        try:
            return self[modulename].find_object(type, name)
        except ModuleNotFound:
            pass

########################################################################
## CodeTree class and helpers.
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

########################################################################
## Classes of objects which are part of a Module.
##
class ObjectInModule(object):
    """Named object that can be localized in a module via the AST.

    Note that the code attribute will be removed from the object once it
    becomes a part of a Module.
    """
    def __init__(self, name, code):
        self.name = name
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

CREATIONAL_METHODS = ['__init__', '__new__']

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

class TestCase(object):
    """A single test object, possibly contained within a test suite (denoted
    as parent attribute).
    """
    def __init__(self, parent=None):
        self.parent = parent

class TestMethod(ObjectInModule, TestCase):
    def __init__(self, name, code=None, parent=None):
        ObjectInModule.__init__(self, name, code)
        TestCase.__init__(self, parent)

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

    def add_test_cases_without_append(self, test_cases):
        for test_case in test_cases:
            self.add_test_case_without_append(test_case)

    def add_test_case_without_append(self, test_case):
        self._check_test_case_type(test_case)
        test_case.parent = self
        self.test_cases.append(test_case)

    def remove_test_case(self, test_case):
        """Try to remove given test case from this test suite.

        Raise ValueError if the given test case is not a part of thise test
        suite.

        Note: this method doesn't modify the AST of the test suite.
        """
        try:
            self.test_cases.remove(test_case)
        except ValueError:
            raise ValueError("Given test case is not a part of this test suite.")

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
        if not self.contains_import(import_desc):
            self.imports.append(import_desc)

    def contains_import(self, import_desc):
        return import_desc in self.imports

    def _check_test_case_type(self, test_case):
        if not isinstance(test_case, tuple(self.allowed_test_case_classes)):
            raise TypeError("Given test case isn't allowed to be added to this test suite.")

class Call(Event):
    """Stores information about a single function or method call.

    Includes reference to the caller, all call arguments, references to
    other calls made inside this one, references to side effects that occured
    during this call and finally an output value.

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

        super(Call, self).__init__()

        self.definition = definition
        self.input = args
        self.output = output
        self.exception = exception

        self.caller = None
        self.subcalls = []
        self.side_effects = []

    def add_subcall(self, call):
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

    def add_side_effect(self, side_effect):
        self.side_effects.append(side_effect)

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        return self.definition == other.definition and \
               self.input == other.input and \
               self.output == other.output and \
               self.exception == other.exception and \
               self.side_effects == other.side_effects

    def __hash__(self):
        return hash((self.definition.name,
                     tuple(self.input.iteritems()),
                     self.output,
                     self.exception,
                     tuple(self.side_effects)))

    def __repr__(self):
        return "%s(definition=%s, input=%r, output=%r, exception=%r, side_effects=%r)" % \
            (class_name(self), self.definition.name, self.input, self.output,
             self.exception, self.side_effects)

class CFunction(Definition):
    pass

class CallToC(Call):
    def __init__(self, name, side_effect=None):
        super(CallToC, self).__init__(CFunction(name), {})
        self.side_effect = side_effect

class FunctionCall(Call):
    pass

class MethodCall(Call):
    pass

class Callable(object):
    """Dynamic aspect of a callable object. Tracks all calls made to given
    callable.

    Each Callable subclass tracks a different type of Calls.
    """
    calls_type = None

    def __init__(self, calls=None):
        if calls is None:
            calls = []
        self.calls = calls

    def add_call(self, call):
        assert_argument_type(call, self.calls_type)
        self.calls.append(call)

class Function(Definition, Callable):
    def __init__(self, name, args=None, code=None, calls=None, is_generator=False, module=None):
        Definition.__init__(self, name, args=args, code=code, is_generator=is_generator)
        Callable.__init__(self, calls)
        self.module = module
        if is_generator:
            self.calls_type = GeneratorObject
        else:
            self.calls_type = FunctionCall

    def get_unique_calls(self):
        return set(self.calls)

    def __repr__(self):
        return "Function(name=%s, args=%r, calls=%r)" % (self.name, self.args, self.calls)

class GeneratorObjectInvocation(Call):
    """Representation of a single generator invocation.

    Each time a generator is resumed a new GeneratorObjectInvocation is created.
    """

class GeneratorObject(Callable, SerializedObject):
    """Representation of a generator object - a callable with an input and many
    outputs (here called "yields").
    """
    calls_type = GeneratorObjectInvocation

    def __init__(self, obj, generator=None, args=None, callable=None):
        Callable.__init__(self)
        SerializedObject.__init__(self, obj)
        if generator is not None and args is not None and callable is not None:
            self.activate(generator, args, callable)

    def activate(self, generator, args, callable):
        assert_argument_type(generator, (Function, Method))
        assert_argument_type(callable, (Function, UserObject))
        if self.is_activated():
            raise ValueError("This generator has already been activated.")
        if not generator.is_generator:
            raise TypeError("Tried to activate GeneratorObject with %r as a generator definition." % generator)
        self.definition = generator
        self.args = args
        # Finally register this GeneratorObject with its callable context
        # (which will be a Function or an UserObject). This has to be
        # done only once for each GeneratorObject.
        callable.add_call(self)

    def is_activated(self):
        return hasattr(self, 'args')

    def __repr__(self):
        if self.is_activated():
            return "GeneratorObject(generator=%r, args=%r)" % \
                (self.definition.name, self.args)
        else:
            return "GeneratorObject()"

class UserObject(Callable, SerializedObject):
    """Serialized instance of a user-defined type.

    UserObjects are also callables that aggregate MethodCall instances,
    capturing the whole life of an object, from initialization to destruction.
    """
    calls_type = (MethodCall, GeneratorObject)

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
        return filter(is_not_init_call, filter(self.is_external_call, self.calls))

    def get_init_and_external_calls(self):
        return filter(self.is_external_call, self.calls)

    def __repr__(self):
        return "UserObject(klass=%r, calls=%r)" % (self.klass.name, self.calls)

    def is_external_call(self, call):
        if isinstance(call, GeneratorObject):
            return True
        return (not call.caller) or (call.caller not in self.calls)

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
        self.add_test_cases_without_append(test_cases)

    def _get_methods(self):
        return self.test_cases
    methods = property(_get_methods)

    def add_test_case_without_append(self, test_case):
        TestSuite.add_test_case_without_append(self, test_case)

        if self.parent is not None:
            CodeTree.of(self).add_object_with_code(test_case)
        else:
            # This TestClass is not attached to a Module yet. We will leave
            # the just-added test case as it is and let Module instance handle
            # the rest when the time comes (see `Module#add_object`).
            pass

    def find_method_by_name(self, name):
        for method in self.test_cases:
            if method.name == name:
                return method

########################################################################
## The Module class.
##
class Module(Localizable, TestSuite):
    allowed_test_case_classes = [TestClass]

    def __init__(self, project, subpath, code=None, objects=None, imports=None,
                 main_snippet=None, last_import=None, errors=None):
        Localizable.__init__(self, project, subpath)
        TestSuite.__init__(self, imports=imports)

        if code:
            # Persistence of CodeTree instances is managed by the Project instance.
            code_tree = CodeTree(code)
            project.remember_code_tree(code_tree, self)
            self.store_reference('main_snippet', main_snippet)
            self.store_reference('last_import', last_import)
        elif objects:
            raise ValueError("Tried to create module with objects, but without code.")

        if objects is None:
            objects = []
        if errors is None:
            errors = []

        self.errors = errors

        self.objects = []
        self.add_objects(objects)

    def _set_module_for_object(self, obj):
        if isinstance(obj, (Class, Function)):
            if obj.module is not None:
                raise TypeError("Trying to add %r to module %r, while the "
                                "object is already inside %r." % \
                                    (obj, self.locator, obj.module.locator))
            obj.module = self

    def _get_classes(self):
        return all_of_type(self.objects, Class)
    classes = property(_get_classes)

    def _get_functions(self):
        return all_of_type(self.objects, Function)
    functions = property(_get_functions)

    def _get_test_classes(self):
        return all_of_type(self.objects, TestClass)
    test_classes = property(_get_test_classes)

    def has_errors(self):
        return self.errors != []

    def store_reference(self, name, code):
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
                self.add_test_case_without_append(obj)
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

    def add_test_case_without_append(self, test_case):
        TestSuite.add_test_case_without_append(self, test_case)
        self.add_object(test_case)
        self.ensure_imports(test_case.imports)

    def remove_test_case(self, test_case):
        TestSuite.remove_test_case(self, test_case)
        self.remove_object(test_case)

    def get_content(self):
        return regenerate(code_of(self))

    def get_test_cases_for_module(self, module):
        """Return all test cases that are associated with given module.
        """
        return [tc for tc in self.test_cases if module in tc.associated_modules]

    def find_object(self, type, name):
        for obj in all_of_type(self.objects, type):
            if obj.name == name:
                return obj

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


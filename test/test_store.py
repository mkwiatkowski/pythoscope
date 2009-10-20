from pythoscope.astbuilder import parse
from pythoscope.store import Class, Function, FunctionCall, Method, Module, \
    CodeTree, CodeTreeNotFound, PointOfEntry, Project, TestClass, TestMethod, \
    UserObject, code_of, module_of
from pythoscope.serializer import ImmutableObject, UnknownObject, \
    SequenceObject, MapObject

from assertions import *
from helper import CustomSeparator, EmptyProject

# Let nose know that those aren't test cases.
TestClass.__test__ = False


class TestModule:
    def setUp(self):
        self.project = EmptyProject()
        self.module = self.project.create_module("module.py", code=parse("# only comments"))
        self.test_class = TestClass(name="TestSomething", code=parse("# some test code"))

    def test_can_add_test_cases_to_empty_modules(self):
        self.module.add_test_case(self.test_class)
        # Make sure it doesn't raise any exceptions.

    def test_adding_a_test_case_adds_it_to_list_of_objects(self):
        self.module.add_test_case(self.test_class)

        assert_equal([self.test_class], self.module.objects)

    def test_replacing_a_test_case_removes_it_from_the_list_of_objects_and_list_of_test_cases(self):
        new_test_class = TestClass(name="TestSomethingElse")
        self.module.add_test_case(self.test_class)

        self.module.replace_test_case(self.test_class, new_test_class)

        assert_equal([new_test_class], self.module.objects)
        assert_equal([new_test_class], self.module.test_cases)

    def test_test_cases_can_be_added_using_add_objects_method(self):
        test_class_1 = TestClass(name="TestSomethingElse")
        test_class_2 = TestClass(name="TestSomethingCompletelyDifferent")
        self.module.add_objects([test_class_1, test_class_2])

        assert_equal([test_class_1, test_class_2], self.module.objects)
        assert_equal([test_class_1, test_class_2], self.module.test_cases)

class TestStoreWithCustomSeparator(CustomSeparator):
    def test_uses_system_specific_path_separator(self):
        module = Module(subpath="some#path.py", project=EmptyProject())
        assert_equal("some.path", module.locator)

def inject_user_object(poe, obj, klass):
    def create_user_object():
        return UserObject(obj, klass)
    user_object = poe.execution._retrieve_or_capture(obj, create_user_object)
    klass.add_user_object(user_object)
    return user_object

def inject_function_call(poe, function, args={}):
    call = FunctionCall(function, args)
    poe.execution.captured_calls.append(call)
    for arg in args.values():
        poe.execution.captured_objects[id(arg)] = arg
    function.add_call(call)
    return call

class TestPointOfEntry:
    def _create_project_with_two_points_of_entry(self, obj):
        project = EmptyProject()
        project.create_module("module.py", objects=[obj])
        self.first = PointOfEntry(project, 'first')
        self.second = PointOfEntry(project, 'second')

    def test_clear_previous_run_removes_user_objects_from_classes(self):
        klass = Class('SomeClass')
        self._create_project_with_two_points_of_entry(klass)

        obj1 = inject_user_object(self.first, 1, klass)
        obj2 = inject_user_object(self.first, 2, klass)
        obj3 = inject_user_object(self.second, 1, klass)

        self.first.clear_previous_run()

        # Only the UserObject from the second POE remains.
        assert_equal_sets([obj3], klass.user_objects)

    def test_clear_previous_run_removes_function_calls_from_functions(self):
        function = Function('some_function')
        self._create_project_with_two_points_of_entry(function)

        call1 = inject_function_call(self.first, function)
        call2 = inject_function_call(self.first, function)
        call3 = inject_function_call(self.second, function)

        self.first.clear_previous_run()

        # Only the FunctionCall from the second POE remains.
        assert_equal_sets([call3], function.calls)

    def test_clear_previous_run_ignores_not_referenced_objects(self):
        function = Function('some_function')
        self._create_project_with_two_points_of_entry(function)

        args = {'i': ImmutableObject(123), 'u': UnknownObject(None),
                's': SequenceObject([], None), 'm': MapObject({}, None)}
        inject_function_call(self.first, function, args)

        self.first.clear_previous_run()
        # Make sure it doesn't raise any exceptions.

class TestModuleOf:
    def setUp(self):
        project = EmptyProject()
        self.module = Module(project=project, subpath='module.py')
        self.klass = Class('Klass', module=self.module)
        self.tclass = TestClass('TClass', parent=self.module)

    def test_module_of_for_module(self):
        assert_equal(self.module, module_of(self.module))

    def test_module_of_for_function(self):
        fun = Function('fun', module=self.module)
        assert_equal(self.module, module_of(fun))

    def test_module_of_for_class(self):
        assert_equal(self.module, module_of(self.klass))

    def test_module_of_for_method(self):
        meth = Method('meth', klass=self.klass)
        assert_equal(self.module, module_of(meth))

    def test_module_of_for_test_classes(self):
        assert_equal(self.module, module_of(self.tclass))

    def test_module_of_for_test_methods(self):
        tmeth = TestMethod('tmeth', parent=self.tclass)
        assert_equal(self.module, module_of(tmeth))

class TestCodeOf:
    def setUp(self):
        project = EmptyProject()
        self.code = object() # A unique fake object.
        self.module = Module(project=project, subpath='module.py')
        self.code_tree = CodeTree(self.code)
        project.remember_code_tree(self.code_tree, self.module)

    def test_code_of_module(self):
        assert_equal(self.code, code_of(self.module))

    def test_code_of_function(self):
        function = Function('fun', module=self.module)
        function_code = object()
        self.code_tree.add_object(function, function_code)

        assert_equal(function_code, code_of(function))

    def test_code_of_class(self):
        klass = Class('Class', module=self.module)
        class_code = object()
        self.code_tree.add_object(klass, class_code)

        assert_equal(class_code, code_of(klass))

    def test_code_of_method(self):
        klass = Class('Class', module=self.module)
        method = Method('method', klass=klass)
        method_code = object()
        self.code_tree.add_object(method, method_code)

        assert_equal(method_code, code_of(method))

    def test_code_of_test_class(self):
        test_class = TestClass('TestClass', parent=self.module)
        test_class_code = object()
        self.code_tree.add_object(test_class, test_class_code)

        assert_equal(test_class_code, code_of(test_class))

    def test_code_of_test_method(self):
        test_class = TestClass('TestClass', parent=self.module)
        test_method = TestMethod('test_method', parent=test_class)
        test_method_code = object()
        self.code_tree.add_object(test_method, test_method_code)

        assert_equal(test_method_code, code_of(test_method))

class TestCodeTree:
    def test_instance_is_accesible_from_the_moment_it_is_created(self):
        project = EmptyProject()
        mod = Module(project=project, subpath='module.py')
        ct = CodeTree(None)
        project.remember_code_tree(ct, mod)

        assert_equal(ct, CodeTree.of(mod))

    def test_removal_of_a_module_removes_its_code_tree(self):
        project = EmptyProject()
        mod = project.create_module('module.py')
        ct = CodeTree(None)
        project.remember_code_tree(ct, mod)

        project.remove_module(mod.subpath)

        assert_raises(CodeTreeNotFound, lambda: CodeTree.of(mod))

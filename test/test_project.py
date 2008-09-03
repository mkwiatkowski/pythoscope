from nose.tools import assert_equal

from pythoscope.store import Project, Module, TestModule, TestClass, TestMethod

from helper import assert_length, assert_equal_sets

# Let nose know that those aren't test classes.
TestModule.__test__ = False
TestClass.__test__ = False
TestMethod.__test__ = False

class TestProject:
    def setUp(self):
        self._old_test_module_save = TestModule._save
        TestModule._save = lambda self: None

        self.existing_test_class = TestClass("TestSomething")
        self.test_module = TestModule()
        self.test_module.add_test_case(self.existing_test_class)
        self.project = Project(modules=[self.test_module])

    def tearDown(self):
        TestModule._save = self._old_test_module_save

    def test_attaches_test_class_to_test_module_with_most_test_cases_for_associated_module(self):
        module = Module()
        irrelevant_test_module = TestModule()
        self.existing_test_class.associated_modules = [module]
        self.project.add_modules([module, irrelevant_test_module])

        new_test_class = TestClass("new", associated_modules=[module])
        self.project.add_test_case(new_test_class, None, False)

        assert new_test_class in self.test_module.test_cases

    def test_doesnt_overwrite_existing_test_classes_by_default(self):
        test_class = TestClass("TestSomething")
        self.project.add_test_case(test_class, "", False)

        assert_length(list(self.project.test_cases_iter()), 1)

    def test_adds_new_test_classes_to_existing_test_module(self):
        test_class = TestClass("TestSomethingNew")
        self.project.add_test_case(test_class, "", False)

        assert_equal_sets([self.existing_test_class, test_class],
                          list(self.project.test_cases_iter()))

    def test_adds_new_test_methods_to_existing_test_classes(self):
        test_method = TestMethod("test_new_method")
        test_class = TestClass("TestSomething", methods=[test_method])
        self.project.add_test_case(test_class, "", False)

        assert_length(list(self.project.test_cases_iter()), 1)
        assert list(self.project.test_cases_iter())[0] is test_method.klass
        assert test_method.klass is not test_class

    def test_after_adding_new_test_case_to_class_its_module_is_saved(self):
        saved = []
        TestModule._save = lambda self: saved.append(True)

        self.existing_test_class.add_test_case(TestMethod("test_something_new"))

        assert saved

    def test_doesnt_overwrite_existing_test_methods_by_default(self):
        test_method = TestMethod("test_method")
        test_class = TestClass("TestSomething", methods=[test_method])
        self.project.add_test_case(test_class, "", False)

        assert_equal([test_method],
                     list(self.project.test_cases_iter())[0].methods)

        # Let's try adding the same method again.
        new_test_method = TestMethod("test_method")
        new_test_class = TestClass("TestSomething", methods=[new_test_method])
        self.project.add_test_case(new_test_class, "", False)

        assert_equal([test_method],
                     list(self.project.test_cases_iter())[0].methods)

    def test_overwrites_existing_test_methods_with_force_option(self):
        test_method = TestMethod("test_method")
        test_class = TestClass("TestSomething", methods=[test_method])
        self.project.add_test_case(test_class, "", False)

        assert_equal([test_method],
                     list(self.project.test_cases_iter())[0].methods)

        # Let's try adding the same method again with a force option
        # set to True.
        new_test_method = TestMethod("test_method")
        new_test_class = TestClass("TestSomething", methods=[new_test_method])
        self.project.add_test_case(new_test_class, "", True)

        # The class is still the same.
        assert_equal([self.existing_test_class],
                     list(self.project.test_cases_iter()))
        # But the method got replaced.
        assert_equal([new_test_method],
                     list(self.project.test_cases_iter())[0].methods)

from nose.tools import assert_equal

from pythoscope.store import Project, Module, TestModule, TestClass, TestMethod

from helper import assert_length

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

        assert_equal([self.existing_test_class, test_class],
                     list(self.project.test_cases_iter()))

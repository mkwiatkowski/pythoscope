from pythoscope.store import Project, Module, TestModule, TestCase

class TestModuleInMemory(TestModule):
    def _save(self):
        pass

class TestProject:
    def test_attaches_test_case_to_test_module_with_most_test_cases_for_associated_module(self):
        module                 = Module()
        associated_test_module = TestModuleInMemory()
        irrelevant_test_module = TestModuleInMemory()
        project                = Project(modules=[module,
                                                  associated_test_module,
                                                  irrelevant_test_module])
        existing_test_case     = TestCase("", "", "", associated_modules=[module])
        associated_test_module.add_test_case(existing_test_case)

        new_test_case = TestCase("", "", "", associated_modules=[module])
        project.add_test_case(new_test_case, None, False)

        assert new_test_case in associated_test_module.test_cases

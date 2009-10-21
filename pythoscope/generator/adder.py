"""Module responsible for adding generated test cases to a project.

Client of this module should use it through add_test_case_to_project() function.
"""

import os.path

from pythoscope.logger import log
from pythoscope.util import max_by_not_zero, module_path_to_name


def add_test_case_to_project(project, test_class, main_snippet=None, force=False):
    existing_test_class = find_test_class_by_name(project, test_class.name)
    if not existing_test_class:
        place = find_place_for_test_class(project, test_class)
        log.info("Adding generated %s to %s." % (test_class.name, place.subpath))
        place.add_test_case(test_class)
        place.ensure_main_snippet(main_snippet)
    else:
        merge_test_classes(existing_test_class, test_class, force)
        existing_test_class.parent.ensure_main_snippet(main_snippet)

def find_test_class_by_name(project, name):
    for tcase in project.iter_test_cases():
        if tcase.name == name:
            return tcase

def merge_test_classes(test_class, other_test_class, force):
    """Merge other_test_case into test_case.
    """
    for method in other_test_class.test_cases:
        existing_test_method = test_class.find_method_by_name(method.name)
        if not existing_test_method:
            log.info("Adding generated %s to %s in %s." % \
                         (method.name, test_class.name, test_class.parent.subpath))
            test_class.add_test_case(method)
        elif force:
            log.info("Replacing %s.%s from %s with generated version." % \
                         (test_class.name, existing_test_method.name, test_class.parent.subpath))
            test_class.replace_test_case(existing_test_method, method)
        else:
            log.info("Test case %s.%s already exists in %s, skipping." % \
                         (test_class.name, existing_test_method.name, test_class.parent.subpath))
    test_class.ensure_imports(other_test_class.imports)

def find_place_for_test_class(project, test_class):
    """Find the best place for the new test case to be added. If there is
    no such place in existing test modules, a new one will be created.
    """
    return find_test_module(project, test_class) or \
        create_test_module(project, test_class)

def find_test_module(project, test_class):
    """Find test module that will be good for the given test case.
    """
    for module in test_class.associated_modules:
        test_module = find_associate_test_module_by_name(project, module) or \
                      find_associate_test_module_by_test_class(project, module)
        if test_module:
            return test_module

def find_associate_test_module_by_name(project, module):
    """Try to find a test module with name corresponding to the name of
    the application module.
    """
    possible_paths = possible_test_module_paths(module, project.new_tests_directory)
    for module in project.get_modules():
        if module.subpath in possible_paths:
            return module

def find_associate_test_module_by_test_class(project, module):
    """Try to find a test module with most test cases for the given
    application module.
    """
    def test_class_number(mod):
        return len(mod.get_test_cases_for_module(module))
    test_module = max_by_not_zero(test_class_number, project.get_modules())
    if test_module:
        return test_module

def test_module_name_for_test_case(test_case):
    """Come up with a name for a test module which will contain given test case.
    """
    # Assuming the test case has at least one associated module, which indeed
    # is a case in current implementation of generator.
    return module_path_to_test_path(test_case.associated_modules[0].subpath)

def create_test_module(project, test_case):
    """Create a new test module for a given test case.
    """
    test_name = test_module_name_for_test_case(test_case)
    return project.create_test_module_from_name(test_name)

def module_path_to_test_path(module):
    """Convert a module locator to a proper test filename.
    """
    return "test_%s.py" % module_path_to_name(module)

def possible_test_module_names(module):
    module_name = module_path_to_name(module.subpath)

    for name in ["test_%s", "%s_test", "%sTest", "tests_%s", "%s_tests", "%sTests"]:
        yield (name % module_name) + ".py"
    for name in ["test%s", "Test%s", "%sTest", "tests%s", "Tests%s", "%sTests"]:
        yield (name % module_name.capitalize()) + ".py"

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

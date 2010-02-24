"""Module responsible for adding generated test cases to a project.

Client of this module should use it through add_test_case_to_project() function.
"""

import os.path

from pythoscope.logger import log
from pythoscope.util import max_by_not_zero, module_path_to_name
from pythoscope.store import Module, TestClass, code_of
from pythoscope.code_trees_manager import CodeTreeNotFound
from pythoscope.astvisitor import find_last_leaf, get_starting_whitespace, \
    is_node_of_type, remove_trailing_whitespace
from pythoscope.astbuilder import EmptyCode, Newline, create_import, \
    insert_after, insert_before


def add_test_case_to_project(project, test_class, main_snippet=None, force=False):
    existing_test_class = find_test_class_by_name(project, test_class.name)
    try:
        if not existing_test_class:
            module = find_module_for_test_class(project, test_class)
            log.info("Adding generated %s to %s." % (test_class.name, module.subpath))
            ensure_imports(module, test_class.imports)
            add_test_case(module, test_class)
            ensure_main_snippet(module, main_snippet, force)
        else:
            ensure_imports(existing_test_class, test_class.imports)
            merge_test_classes(existing_test_class, test_class, force)
            ensure_main_snippet(existing_test_class.parent, main_snippet, force)
    except CodeTreeNotFound, ex:
        log.warning("Not adding %s to %s, because of a failed inspection." %\
            (test_class.name, ex.module_subpath))

def add_test_case_without_append(test_suite, test_case):
    test_suite.add_test_case_without_append(test_case)

def add_test_case(test_suite, test_case):
    if isinstance(test_suite, Module):
        # If the main_snippet exists we have to put the new test case
        # before it. If it doesn't we put the test case at the end.
        main_snippet = code_of(test_suite, 'main_snippet')
        if main_snippet:
            insert_before(main_snippet, test_case.code)
        else:
            code_of(test_suite).append_child(test_case.code)
    elif isinstance(test_suite, TestClass):
        # Append to the right node, so that indentation level of the
        # new method is good.
        if code_of(test_suite).children and is_node_of_type(code_of(test_suite).children[-1], 'suite'):
            remove_trailing_whitespace(test_case.code)
            suite = code_of(test_suite).children[-1]
            # Prefix the definition with the right amount of whitespace.
            node = find_last_leaf(suite.children[-2])
            ident = get_starting_whitespace(suite)
            # There's no need to have extra newlines.
            if node.prefix.endswith("\n"):
                node.prefix += ident.lstrip("\n")
            else:
                node.prefix += ident
            # Insert before the class contents dedent.
            suite.insert_child(-1, test_case.code)
        else:
            code_of(test_suite).append_child(test_case.code)
    else:
        raise TypeError("Tried to add a test case to %r." % test_suite)
    add_test_case_without_append(test_suite, test_case)
    test_suite.mark_as_changed()

def ensure_main_snippet(module, main_snippet, force=False):
    """Make sure the main_snippet is present. Won't overwrite the snippet
    unless force flag is set.
    """
    if not main_snippet:
        return
    current_main_snippet = code_of(module, 'main_snippet')

    if not current_main_snippet:
        code_of(module).append_child(main_snippet)
        module.store_reference('main_snippet', main_snippet)
        module.mark_as_changed()
    elif force:
        current_main_snippet.replace(main_snippet)
        module.store_reference('main_snippet', main_snippet)
        module.mark_as_changed()

def ensure_imports(test_suite, imports):
    if isinstance(test_suite, TestClass):
        module = test_suite.parent
    elif isinstance(test_suite, Module):
        module = test_suite
    else:
        raise TypeError("Tried to ensure imports on %r." % test_suite)
    for imp in imports:
        if not module.contains_import(imp):
            insert_after_other_imports(module, create_import(imp))
            module.mark_as_changed()
    test_suite.ensure_imports(imports)

def insert_after_other_imports(module, code):
    last_import = code_of(module, 'last_import')
    if last_import:
        insert_after(last_import, code)
    else:
        # Add an extra newline separating imports from the code.
        code_of(module).insert_child(0, Newline())
        code_of(module).insert_child(0, code)
    # Just inserted import becomes the last one.
    module.store_reference('last_import', code)

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
            add_test_case(test_class, method)
        elif force:
            log.info("Replacing %s.%s from %s with generated version." % \
                         (test_class.name, existing_test_method.name, test_class.parent.subpath))
            replace_test_case(test_class, existing_test_method, method)
        else:
            log.info("Test case %s.%s already exists in %s, skipping." % \
                         (test_class.name, existing_test_method.name, test_class.parent.subpath))

def replace_test_case(test_suite, old_test_case, new_test_case):
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

    test_suite.remove_test_case(old_test_case)
    add_test_case_without_append(test_suite, new_test_case)
    test_suite.mark_as_changed()

def find_module_for_test_class(project, test_class):
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
    return project.create_test_module_from_name(test_name, code=EmptyCode())

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

import os
import re

from astvisitor import EmptyCode, descend, parse, ASTVisitor
from store import TestModule, TestClass, TestMethod, ModuleNotFound
from util import camelize


def name2testname(name):
    if name[0].isupper():
        return "Test%s" % name
    return "test_%s" % name

class GenerationError(Exception):
    pass

class UnknownTemplate(Exception):
    def __init__(self, template):
        Exception.__init__(self, "Couldn't find template %r." % template)
        self.template = template

def localize_method_code(code, method_name):
    """Return part of the code tree that corresponds to the given method
    definition.
    """
    class LocalizeMethodVisitor(ASTVisitor):
        def __init__(self):
            ASTVisitor.__init__(self)
            self.method_body = None
        def visit_function(self, name, args, body):
            if name == method_name:
                self.method_body = body

    return descend(code.children, LocalizeMethodVisitor).method_body

class TestGenerator(object):
    imports = []
    main_snippet = EmptyCode()

    def from_template(cls, template):
        if template == 'unittest':
            return UnittestTestGenerator()
        elif template == 'nose':
            return NoseTestGenerator()
        else:
            raise UnknownTemplate(template)
    from_template = classmethod(from_template)

    def add_tests_to_project(self, project, modnames, destdir, force=False):
        if os.path.exists(destdir):
            if not os.path.isdir(destdir):
                raise GenerationError("Destination is not a directory.")
        else:
            os.makedirs(destdir)

        for modname in modnames:
            module = project[modname]
            self._add_tests_for_module(module, project, destdir, force)

    def _add_tests_for_module(self, module, project, destdir, force):
        test_cases = self._generate_test_cases(module)
        if test_cases:
            project.add_test_cases(test_cases, destdir, force)

    def _generate_test_cases(self, module):
        return filter(None,
                      [self._generate_test_case(obj, module) \
                       for obj in module.testable_objects])

    def _generate_test_case(self, object, module):
        class_name = name2testname(camelize(object.name))
        methods_names = map(name2testname, object.get_testable_methods())

        # Don't generate empty test classes.
        if methods_names:
            test_body = self.create_test_class(class_name, methods_names)
            test_code = parse(test_body)
            def methodname2testmethod(method_name):
                return TestMethod(name=method_name,
                                  code=localize_method_code(test_code,
                                                            method_name))
            return TestClass(name=class_name,
                             code=test_code,
                             methods=map(methodname2testmethod, methods_names),
                             imports=self.imports,
                             main_snippet=self.main_snippet,
                             associated_modules=[module])

class UnittestTestGenerator(TestGenerator):
    imports = ['unittest']
    main_snippet = parse("if __name__ == '__main__':\n    unittest.main()\n")

    def create_test_class(self, class_name, methods_names):
        result = "class %s(unittest.TestCase):\n" % class_name
        for method_name in methods_names:
            result += "    def %s(self):\n" % method_name
            result += "        assert False # TODO: implement your test here\n\n"
        return result

class NoseTestGenerator(TestGenerator):
    imports=[('nose', 'SkipTest')]

    def create_test_class(self, class_name, methods_names):
        result = "class %s:\n" % class_name
        for method_name in methods_names:
            result += "    def %s(self):\n" % method_name
            result += "        raise SkipTest # TODO: implement your test here\n\n"
        return result

def add_tests_to_project(project, modnames, destdir, template, force=False):
    generator = TestGenerator.from_template(template)
    generator.add_tests_to_project(project, modnames, destdir, force)

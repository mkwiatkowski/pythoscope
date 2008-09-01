import os
import re

from Cheetah import Template

from astvisitor import parse
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

class TestGenerator(object):
    def from_template(cls, template):
        if template == 'unittest':
            return cls(template='unittest',
                       imports=['unittest'],
                       main_snippet=parse("if __name__ == '__main__':\n    unittest.main()\n"))
        elif template == 'nose':
            return cls(template='nose',
                       imports=[('nose', 'SkipTest')])
        else:
            raise UnknownTemplate(template)
    from_template = classmethod(from_template)

    def __init__(self, template, imports, main_snippet=""):
        self.template_path = os.path.join(os.path.dirname(__file__),
                                          "templates/%s.tpl" % template)
        self.imports = imports
        self.main_snippet = main_snippet

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
        test_name = name2testname(camelize(object.name))
        mapping = {'object': object, 'test_name': test_name}
        test_body = str(Template.Template(file=self.template_path,
                                          searchList=[mapping]))
        if test_body:
            methods = []
            for name in object.get_testable_methods():
                methods.append(TestMethod(name=name2testname(name),
                                          # TODO: generate method code for real
                                          code=None))
            return TestClass(name=test_name,
                             code=parse(test_body),
                             methods=methods,
                             imports=self.imports,
                             main_snippet=self.main_snippet,
                             associated_modules=[module])

def add_tests_to_project(project, modnames, destdir, template, force=False):
    generator = TestGenerator.from_template(template)
    generator.add_tests_to_project(project, modnames, destdir, force)

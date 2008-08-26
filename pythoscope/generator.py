import os
import re

from Cheetah import Template

from store import TestModule, TestCase, ModuleNotFound
from util import camelize

class GenerationError(Exception):
    pass

class UnknownTemplate(Exception):
    pass

def module2testpath(module):
    """Convert a module locator to a proper test filename.

    >>> module2testpath("module.py")
    'test_module.py'
    >>> module2testpath("pythoscope/store.py")
    'test_pythoscope_store.py'
    >>> module2testpath("pythoscope/__init__.py")
    'test_pythoscope.py'
    """
    return "test_" + re.sub(r'%s__init__.py$' % os.path.sep, '.py', module).\
        replace(os.path.sep, "_")

class TestGenerator(object):
    def from_template(cls, template):
        if template == 'unittest':
            return cls(template='unittest',
                       imports=['unittest'],
                       main_snippet="if __name__ == '__main__':\n    unittest.main()\n")
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
        project.add_test_cases(test_cases, destdir, force)

    def _generate_test_cases(self, module):
        mapping = {'module': module, 'camelize': camelize}
        test_body = str(Template.Template(file=self.template_path,
                                          searchList=[mapping]))
        return [TestCase(test_body, self.imports, self.main_snippet)]

def add_tests_to_project(project, modnames, destdir, template, force=False):
    generator = TestGenerator.from_template(template)
    generator.add_tests_to_project(project, modnames, destdir, force)

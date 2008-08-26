import os
import re

from Cheetah import Template

from store import TestModule, TestCase, ModuleNotFound
from util import camelize

class GenerationError(Exception):
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
    def __init__(self, template, imports, main_snippet=""):
        self.template_path = os.path.join(os.path.dirname(__file__),
                                          "templates/%s.tpl" % template)
        self.imports = imports
        self.main_snippet = main_snippet

    def add_tests_for_module(self, module, project, destdir, force):
        test_cases = self._generate_test_cases(module)
        project.add_test_cases(test_cases, destdir, force)

    def _generate_test_cases(self, module):
        mapping = {'module': module, 'camelize': camelize}
        test_body = str(Template.Template(file=self.template_path,
                                          searchList=[mapping]))
        return [TestCase(test_body, self.imports, self.main_snippet)]

template2generator = {
    'unittest': TestGenerator(template='unittest',
                              imports=['unittest'],
                              main_snippet="if __name__ == '__main__':\n    unittest.main()\n"),
    'nose':     TestGenerator(template='nose',
                              imports=[('nose', 'SkipTest')])
}

def generate_test_modules(project, modnames, destdir, template, force=False):
    if os.path.exists(destdir):
        if not os.path.isdir(destdir):
            raise GenerationError("Destination is not a directory.")
    else:
        os.makedirs(destdir)

    test_generator = template2generator[template]

    for modname in modnames:
        module = project[modname]
        test_generator.add_tests_for_module(module, project, destdir, force)

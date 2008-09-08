from pythoscope.inspector import static
from pythoscope.util import python_modules_below


def inspect_project(project):
    for modpath in python_modules_below(project.path):
        static.inspect_module(project, modpath)

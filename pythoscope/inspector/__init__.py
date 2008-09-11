from pythoscope.inspector import static, dynamic
from pythoscope.util import python_modules_below


def inspect_project(project):
    for modpath in python_modules_below(project.path):
        static.inspect_module(project, modpath)

    for poe in project.points_of_entry.values():
        dynamic.inspect_point_of_entry(poe)

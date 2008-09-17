from pythoscope.inspector import static, dynamic
from pythoscope.store import ModuleNotFound
from pythoscope.util import python_modules_below


def inspect_project(project):
    # If nothing new was discovered statically, it's also no use to run
    # dynamic inspection.
    if inspect_project_statically(project) > 0:
        inspect_project_dynamically(project)
    else:
        print "Info: No changes discovered in the source code, skipping dynamic inspection."

def inspect_project_statically(project):
    count = 0
    for modpath in python_modules_below(project.path):
        try:
            module = project.find_module_by_full_path(modpath)
            if module.is_up_to_date():
                print "Info: %s hasn't changed since last inspection, skipping." % module.subpath
                continue
        except ModuleNotFound:
            pass
        static.inspect_module(project, modpath)
        count += 1
    return count

def inspect_project_dynamically(project):
    for poe in project.points_of_entry.values():
        try:
            dynamic.inspect_point_of_entry(poe)
        except SyntaxError, err:
            print "Warning: Point of entry contains a syntax error:", err
        except (Exception, KeyboardInterrupt, SystemExit), err:
            print "Warning: Point of entry exited with error:", repr(err)

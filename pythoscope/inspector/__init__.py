from pythoscope.inspector import static, dynamic
from pythoscope.store import ModuleNotFound
from pythoscope.util import python_modules_below


def inspect_project(project):
    remove_deleted_modules(project)
    remove_deleted_points_of_entry(project)

    updates = add_and_update_modules(project) + add_points_of_entry(project)

    # If nothing new was discovered statically and there are no new points of
    # entry, don't run dynamic inspection.
    if updates:
        inspect_project_dynamically(project)
    else:
        print "Info: No changes discovered in the source code, skipping dynamic inspection."

def remove_deleted_modules(project):
    subpaths = [mod.subpath for mod in project.iter_modules() if not mod.exists()]
    for subpath in subpaths:
        project.remove_module(subpath)

def add_and_update_modules(project):
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

def remove_deleted_points_of_entry(project):
    names = [poe.name for poe in project.points_of_entry.values() if not poe.exists()]
    for name in names:
        project.remove_point_of_entry(name)

def add_points_of_entry(project):
    count = 0
    for path in python_modules_below(project._get_points_of_entry_path()):
        if project.ensure_point_of_entry(path):
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

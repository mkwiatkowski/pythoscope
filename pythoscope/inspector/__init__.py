from pythoscope.inspector import static, dynamic
from pythoscope.logger import log
from pythoscope.store import ModuleNotFound
from pythoscope.util import generator_has_ended, last_traceback, \
    python_modules_below


def inspect_project(project):
    remove_deleted_modules(project)
    remove_deleted_points_of_entry(project)

    updates = inspect_project_statically(project)

    # If nothing new was discovered statically and there are no new points of
    # entry, don't run dynamic inspection.
    if updates:
        inspect_project_dynamically(project)
    else:
        log.info("No changes discovered in the source code, skipping dynamic inspection.")

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
                log.info("%s hasn't changed since last inspection, skipping." % module.subpath)
                continue
        except ModuleNotFound:
            pass
        log.info("Inspecting module %s." % project._extract_subpath(modpath))
        static.inspect_module(project, modpath)
        count += 1
    return count

def remove_deleted_points_of_entry(project):
    names = [poe.name for poe in project.points_of_entry.values() if not poe.exists()]
    for name in names:
        project.remove_point_of_entry(name)

def add_and_update_points_of_entry(project):
    count = 0
    for path in python_modules_below(project.get_points_of_entry_path()):
        poe = project.ensure_point_of_entry(path)
        if poe.is_out_of_sync():
            count += 1
    return count

def inspect_project_statically(project):
    return add_and_update_modules(project) + \
        add_and_update_points_of_entry(project)

def inspect_project_dynamically(project):
    if project.points_of_entry and hasattr(generator_has_ended, 'unreliable'):
        log.warning("Pure Python implementation of util.generator_has_ended is "
                    "not reliable on Python 2.4 and lower. Please compile the "
                    "_util module or use Python 2.5 or higher.")

    for poe in project.points_of_entry.values():
        try:
            log.info("Inspecting point of entry %s." % poe.name)
            dynamic.inspect_point_of_entry(poe)
        except SyntaxError, err:
            log.warning("Point of entry contains a syntax error: %s" % err)
        except (Exception, KeyboardInterrupt, SystemExit), err:
            log.warning("Point of entry exited with error: %s" % repr(err))
            log.debug("Full traceback:\n" + last_traceback())

import getopt
import os
import sys

from inspector import inspect_project
from generator import add_tests_to_project, UnknownTemplate
from store import Project, ModuleNotFound, ModuleNeedsAnalysis, \
     ModuleSaveError, get_pythoscope_path, get_points_of_entry_path


USAGE = """Pythoscope usage:

    %s [options] [module names...]

By default, this command generates test suites for the listed modules.
It will automatically check for any source code changes and rerun all
points of entry if necessary.

As a module name, you can use both direct path or a locator in dot-style
notation. For example, both of the following are acceptable:

  package/sub/module.py
  package.sub.module

All test files will be written to a single directory.

Options:
  -f, --force    Go ahead and overwrite any existing test files. Default
                 is to skip generation of tests for files that would
                 otherwise get overwriten.
  -h, --help     Show this help message and exit.
  -i. --init     This option will initialize given project directory for
                 further Pythoscope usage. This is required for each new
                 project.
                 Initialization creates .pythoscope/ directory in the
                 project directory, which will store all information
                 related to test generation.
                 It will also perform a static (thus perfectly safe)
                 inspection of the project source code.
                 You may provide an argument after this option, which
                 should be a path pointing to a directory of a project
                 you want to initialize. If you don't provide one,
                 current directory will be used.
  -t TEMPLATE_NAME, --template=TEMPLATE_NAME
                 Name of a template to use (see below for a list of
                 available templates). Default is "unittest".

Available templates:
  * unittest     All tests are placed into classes which derive from
                 unittest.TestCase. Each test module ends with an
                 import-safe call to unittest.main().
  * nose         Nose-style tests, which don't import unittest and use
                 SkipTest as a default test body.
"""

class PythoscopeDirectoryMissing(Exception):
    pass

def find_project_directory(path):
    """Try to find a pythoscope project directory for a given path,
    i.e. the closest directory that contains .pythoscope/ subdirectory.

    Will go up the directory tree and return the first matching path.
    """
    path = os.path.realpath(path)

    if not os.path.isdir(path):
        return find_project_directory(os.path.dirname(path))

    pythoscope_path = get_pythoscope_path(path)
    parent_path = os.path.join(path, os.path.pardir)

    # We reached the root.
    if os.path.samefile(path, parent_path):
        raise PythoscopeDirectoryMissing()
    elif os.path.isdir(pythoscope_path):
        return path
    else:
        return find_project_directory(os.path.join(path, os.path.pardir))

def init_project(path):
    pythoscope_path = get_pythoscope_path(path)

    try:
        os.makedirs(pythoscope_path)
        os.makedirs(get_points_of_entry_path(path))
    except OSError, err:
        print "Error: Couldn't initialize Pythoscope directory: %s." % err.strerror

def generate_tests(modules, force, template):
    try:
        project = Project.from_directory(find_project_directory(modules[0]))
        inspect_project(project)
        add_tests_to_project(project, modules, template, force)
        project.save()
    except PythoscopeDirectoryMissing:
        print "Error: Can't find .pythoscope/ directory for this project. " \
              "Initialize the project with the '--init' option first."
    except ModuleNeedsAnalysis, err:
        if err.out_of_sync:
            print "Error: Tried to generate tests for test module located at %r, " \
                  "but it has been modified during this run. Please try running pythoscope again." % err.path
        else:
            print "Error: Tried to generate tests for test module located at %r, " \
                  "but it was created during this run. Please try running pythoscope again." % err.path
    except ModuleNotFound, err:
        if os.path.exists(err.module):
            print "Error: Couldn't find information on module %r. This shouldn't happen, please file a bug report." % err.module
        else:
            print "Error: File doesn't exist: %s." % err.module
    except ModuleSaveError, err:
        print "Error: Couldn't save module %r: %s." % (err.module, err.reason)
    except UnknownTemplate, err:
        print "Error: Couldn't find template named %r. Available templates are 'nose' and 'unittest'." % err.template

def main():
    appname = os.path.basename(sys.argv[0])

    try:
        options, args = getopt.getopt(sys.argv[1:], "fhit:",
                                      ["force", "help", "init", "template="])
    except getopt.GetoptError, err:
        print "Error:", err, "\n"
        print USAGE % appname
        sys.exit(1)

    force = False
    init = False
    template = "unittest"

    for opt, value in options:
        if opt in ("-f", "--force"):
            force = True
        elif opt in ("-h", "--help"):
            print USAGE % appname
            sys.exit()
        elif opt in ("-i", "--init"):
            init = True
        elif opt in ("-t", "--template"):
            template = value

    try:
        if init:
            if args:
                project_path = args[0]
            else:
                project_path = "."
            init_project(project_path)
        else:
            if not args:
                print "Error: You didn't specify any module to generate tests for.\n"
                print USAGE % appname
            else:
                generate_tests(args, force, template)
    except:
        print "Ups, it seems internal Pythoscope error occured. Please file a bug report at https://bugs.launchpad.net/pythoscope"
        print
        raise

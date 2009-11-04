import getopt
import os
import sys

import logger

from inspector import inspect_project, inspect_project_statically
from generator import add_tests_to_project, UnknownTemplate
from logger import log
from store import Project, ModuleNotFound, ModuleNeedsAnalysis, \
     ModuleSaveError, get_pythoscope_path, get_points_of_entry_path, \
     get_code_trees_path
from compat import samefile


__version__ = '0.4.2'

BUGTRACKER_URL = "https://bugs.launchpad.net/pythoscope"
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
  -q, --quiet    Don't print anything unless it's an error.
  -v, --verbose  Be very verbose (basically enable debug output).
  -V, --version  Print Pythoscope version and exit.

Available templates:
  * unittest     All tests are placed into classes which derive from
                 unittest.TestCase. Each test module ends with an
                 import-safe call to unittest.main().
  * nose         Nose-style tests, which don't import unittest and use
                 SkipTest as a default test body.
"""

def fail(message):
    """Log the error message and exit.
    """
    log.error(message)
    sys.exit(1)

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
    if samefile(path, parent_path):
        raise PythoscopeDirectoryMissing()
    elif os.path.isdir(pythoscope_path):
        return path
    else:
        return find_project_directory(os.path.join(path, os.path.pardir))

def init_project(path, skip_inspection=False):
    pythoscope_path = get_pythoscope_path(path)

    try:
        log.debug("Initializing .pythoscope directory: %s" % (os.path.abspath(pythoscope_path)))
        os.makedirs(pythoscope_path)
        os.makedirs(get_points_of_entry_path(path))
        os.makedirs(get_code_trees_path(path))
    except OSError, err:
        fail("Couldn't initialize Pythoscope directory: %s." % err.strerror)

    project = Project.from_directory(path)
    if not skip_inspection:
        log.debug("Performing initial static inspection of the project source code.")
        inspect_project_statically(project)
    project.save()

def generate_tests(modules, force, template):
    try:
        project = Project.from_directory(find_project_directory(modules[0]))
        inspect_project(project)
        add_tests_to_project(project, modules, template, force)
        project.save()
    except PythoscopeDirectoryMissing:
        fail("Can't find .pythoscope/ directory for this project. "
             "Initialize the project with the '--init' option first.")
    except ModuleNeedsAnalysis, err:
        if err.out_of_sync:
            fail("Tried to generate tests for test module located at %r, "
                 "but it has been modified during this run. Please try "
                 "running pythoscope again." % err.path)
        else:
            fail("Tried to generate tests for test module located at %r, "
                 "but it was created during this run. Please try running "
                 "pythoscope again." % err.path)
    except ModuleNotFound, err:
        if os.path.exists(err.module):
            fail("Couldn't find information on module %r. This shouldn't "
                 "happen, please file a bug report at %s." % (err.module, BUGTRACKER_URL))
        else:
            fail("File doesn't exist: %s." % err.module)
    except ModuleSaveError, err:
        fail("Couldn't save module %r: %s." % (err.module, err.reason))
    except UnknownTemplate, err:
        fail("Couldn't find template named %r. Available templates are "
             "'nose' and 'unittest'." % err.template)

def main():
    appname = os.path.basename(sys.argv[0])

    try:
        options, args = getopt.getopt(sys.argv[1:], "fhit:qvV",
                        ["force", "help", "init", "template=", "quiet", "verbose", "version"])
    except getopt.GetoptError, err:
        log.error("%s\n" % err)
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
        elif opt in ("-q", "--quiet"):
            log.level = logger.ERROR
        elif opt in ("-v", "--verbose"):
            log.level = logger.DEBUG
        elif opt in ("-V", "--version"):
            print "%s %s" % (appname, __version__)
            sys.exit()

    try:
        if init:
            if args:
                project_path = args[0]
            else:
                project_path = "."
            init_project(project_path)
        else:
            if not args:
                log.error("You didn't specify any modules for test generation.\n")
                print USAGE % appname
            else:
                generate_tests(args, force, template)
    except KeyboardInterrupt:
        log.info("Interrupted by the user.")
    except Exception: # SystemExit gets through
        log.error("Oops, it seems that an internal Pythoscope error occurred. Please file a bug report at %s\n" % BUGTRACKER_URL)
        raise

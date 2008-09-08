import getopt
import os
import sys

from inspector import inspect_project
from generator import add_tests_to_project, UnknownTemplate
from store import Project, ModuleNotFound, ModuleNeedsAnalysis, \
     ModuleSaveError, get_pythoscope_path


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

INIT_USAGE = """Pythoscope initialization usage:

    %s init [options] [directory]

This command will initialize given project directory for
further Pythoscope usage. This is required before using other
Pythoscope commands.

Initialization creates .pythoscope/ directory in the project
directory, which will store all information related to test
generation. No analysis is done at this point.

If you don't provide a directory argument, current directory
will be used.

Options:
  -h, --help                 Show this help message and exit.
"""

def init(appname, args):
    try:
        options, args = getopt.getopt(args, "h", ["help"])
    except getopt.GetoptError, err:
        print "Error:", err, "\n"
        print INIT_USAGE % appname
        sys.exit(1)

    for opt, value in options:
        if opt in ("-h", "--help"):
            print INIT_USAGE % appname
            sys.exit()

    if args:
        project_path = args[0]
    else:
        project_path = "."
    pythoscope_path = get_pythoscope_path(project_path)

    try:
        os.makedirs(pythoscope_path)
    except OSError, err:
        print "Couldn't initialize Pythoscope directory: %s." % err.strerror

INSPECT_USAGE = """Pythoscope inspector usage:

    %s inspect [options]

This command will collect information about the current project.

Options:
  -h, --help                 Show this help message and exit.
"""

def inspect(appname, args):
    try:
        options, args = getopt.getopt(args, "h", ["help"])
    except getopt.GetoptError, err:
        print "Error:", err, "\n"
        print INSPECT_USAGE % appname
        sys.exit(1)

    for opt, value in options:
        if opt in ("-h", "--help"):
            print INSPECT_USAGE % appname
            sys.exit()

    try:
        project = Project.from_directory(find_project_directory("."))
        inspect_project(project)
        project.save()
    except PythoscopeDirectoryMissing, err:
        print "Error: Can't find .pythoscope/ directory for this project. " \
              "Use the 'init' command first."

GENERATE_USAGE = """Pythoscope generator usage:

    %s generate [options] [module names...]

This command will generate test suites for the listed modules.
As a module name, you can use both direct path or locator in dot-style
notation. For example, both of the following are acceptable:

  package/sub/module.py
  package.sub.module

All test files will be written to a single directory.

Options:
  -f, --force                Go ahead and overwrite any existing
                             test files. Default is to skip generation
                             of tests for files that would otherwise
                             get overwriten.
  -h, --help                 Show this help message and exit.
  -t TEMPLATE_NAME, --template=TEMPLATE_NAME
                             Name of a template to use (see below for
                             a list of available templates). Default
                             is "unittest".

Available templates:
  * unittest     All tests are placed into classes which derive
                 from unittest.TestCase. Each test module ends with
                 an import-safe call to unittest.main().
  * nose         Nose-style tests, which don't import unittest and use
                 SkipTest as a default test body.
"""

def generate(appname, args):
    try:
        options, args = getopt.getopt(args, "fht:", ["force", "help", "template="])
    except getopt.GetoptError, err:
        print "Error:", err, "\n"
        print GENERATE_USAGE % appname
        sys.exit(1)

    force = False
    template = "unittest"

    for opt, value in options:
        if opt in ("-f", "--force"):
            force = True
        elif opt in ("-h", "--help"):
            print GENERATE_USAGE % appname
            sys.exit()
        elif opt in ("-t", "--template"):
            template = value

    try:
        project = Project.from_directory(find_project_directory(args[0]))
        add_tests_to_project(project, args, template, force)
        project.save()
    except IndexError:
        print "Error: You must provide at least one argument to generate."
    except PythoscopeDirectoryMissing:
        print "Error: Can't find .pythoscope/ directory for this project. " \
              "Use the 'init' command first."
    except ModuleNeedsAnalysis, err:
        if err.out_of_sync:
            print "Error: Tried to generate tests for test module located at %r, " \
                  "but it has been modified since last analysis. Run 'inspect' on it again." % err.path
        else:
            print "Error: Tried to generate tests for test module located at %r, " \
                  "but it hasn't been analyzed yet. Run 'inspect' on it first." % err.path
    except ModuleNotFound, err:
        print "Error: Couldn't find information on module %r, try running 'inspect' on it first." % err.module
    except ModuleSaveError, err:
        print "Error: Couldn't save module %r: %s." % (err.module, err.reason)
    except UnknownTemplate, err:
        print "Error: Couldn't find template named %r. Available templates are 'nose' and 'unittest'." % err.template

MAIN_USAGE = """Pythoscope usage:

    %s init [options] [directory]
    %s inspect [options] [files and directories...]
    %s generate [options] [module names...]

Pythoscope has two main modes of operation. It can either
collect information about a Python project or generate test
cases based on previously gathered info. Use the --help
option in combination with a mode name to get help on this
particular command.

However, before any of those two modes can be used, you
have to use the 'init' command to initialize the .pythoscope
directory.
"""

def main():
    appname = os.path.basename(sys.argv[0])

    try:
        mode, args = sys.argv[1], sys.argv[2:]

        if mode == 'init':
            init(appname, args)
        elif mode == 'inspect':
            inspect(appname, args)
        elif mode == 'generate':
            generate(appname, args)
        else:
            print "Error: unknown command %r\n" % mode
            print MAIN_USAGE % (appname, appname, appname)
            sys.exit(1)
    except IndexError:
        print MAIN_USAGE % (appname, appname, appname)
        sys.exit(1)

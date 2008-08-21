import getopt
import os
import sys

from collector import collect_information_from_paths
from generator import generate_test_modules
from store import Project

PROJECT_FILE = ".pythoscope"

COLLECT_USAGE = """Pythoscope collector usage:

    %s collect [options] [files and directories...]

This command will collect information about all listed Python
modules. Listed paths can point to a Python module file or to
a directory. Directories are processed recursively. All
information is saved to .pythoscope file in the current
working directory.

Options:
  -h, --help                 Show this help message and exit.
"""

def collect(appname, args):
    try:
        options, args = getopt.getopt(args, "h", ["help"])
    except getopt.GetoptError, err:
        print "Error:", err, "\n"
        print COLLECT_USAGE % appname
        sys.exit(1)

    for opt, value in options:
        if opt in ("-h", "--help"):
            print COLLECT_USAGE % appname
            sys.exit()

    project = Project(modules=collect_information_from_paths(args))
    project.save_to_file(PROJECT_FILE)

GENERATE_USAGE = """Pythoscope generator usage:

    %s generate [options] [module names...]

This command will generate test suites for the listed modules.
As a module name, you can use both direct path or locator in dot-style
notation. For example, both of the following are acceptable:

  package/sub/module.py
  package.sub.module

All test files will be written to a single directory.

Options:
  -d PATH, --destdir=PATH    Destination directory for generated test
                             files. Default is "pythoscope-tests/".
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
        options, args = getopt.getopt(args, "d:fht:",
                                      ["destdir=", "force", "help", "template="])
    except getopt.GetoptError, err:
        print "Error:", err, "\n"
        print GENERATE_USAGE % appname
        sys.exit(1)

    destdir = "pythoscope-tests"
    force = False
    template = "unittest"

    for opt, value in options:
        if opt in ("-d", "--destdir"):
            destdir = value
        elif opt in ("-f", "--force"):
            force = True
        elif opt in ("-h", "--help"):
            print GENERATE_USAGE % appname
            sys.exit()
        elif opt in ("-t", "--template"):
            template = value

    project = Project(filepath=PROJECT_FILE)
    generate_test_modules(project, args, destdir, template, force)

MAIN_USAGE = """Pythoscope usage:

    %s generate [options] [module names...]
    %s collect [options] [files and directories...]

Pythoscope has two modes of operation. It can either collect
information about a Python project or generate test cases
based on previously gahered info. Use the --help option in
combination with a mode name to get help on this particular
mode.
"""

def main():
    appname = os.path.basename(sys.argv[0])

    try:
        mode, args = sys.argv[1], sys.argv[2:]

        if mode == 'collect':
            collect(appname, args)
        elif mode == 'generate':
            generate(appname, args)
        else:
            print "Error: unknown mode %r\n" % mode
            print MAIN_USAGE % (appname, appname)
            sys.exit(1)
    except IndexError:
        print MAIN_USAGE % (appname, appname)
        sys.exit(1)

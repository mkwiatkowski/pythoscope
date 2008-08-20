import sys

from collector import collect_information_from_paths
from generator import generate_test_modules
from store import Project

def main():
    appname, mode, args = sys.argv[0], sys.argv[1], sys.argv[2:]

    projectfile = ".pythoscope"
    destdir = "pythoscope-tests"

    if mode == 'collect':
        project = Project(modules=collect_information_from_paths(args))
        project.save_to_file(projectfile)
    elif mode == 'generate':
        project = Project(filepath=projectfile)
        generate_test_modules(project, args, destdir)

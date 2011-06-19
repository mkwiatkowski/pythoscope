import commands
import glob
import os
import shutil
import sys
import tarfile
import tempfile


PREFIX = os.path.abspath(os.path.join(os.path.dirname(__file__), 'projects'))

class GatheringError(Exception):
    pass

class GatheringResults(object):
    def __init__(self, loc, functions, classes, methods, passed, skipped, errors, failures, coverage):
        self.loc = loc
        self.functions = functions
        self.classes = classes
        self.methods = methods
        self.passed = passed
        self.skipped = skipped
        self.errors = errors
        self.failures = failures
        self.coverage = coverage
    total = property(lambda s: s.passed + s.skipped + s.errors + s.failures)

def notify(message):
    print '*'*8, message

def check_environment():
    notify("Checking environment...")
    # TODO: check for python, nosetests, coverage
    notify("Environment OK.")

def prepare_project(project):
    notify("Preparing project...")
    archive = os.path.join(PREFIX, project) + ".tar.gz"
    project_dir = tempfile.mkdtemp(prefix="pythoscope-")
    os.chdir(project_dir)
    t = tarfile.open(archive)
    t.extractall(project_dir)
    t.close()
    notify("Project ready in %s." % project_dir)
    return project_dir


################################################################################
#  CODE METRICS CODE start
################################################################################

# Make pythoscope importable directly.
import os, sys
pythoscope_path = os.path.join(os.path.dirname(__file__), os.pardir)
sys.path.insert(0, os.path.abspath(pythoscope_path))
from pythoscope.astvisitor import descend, ASTVisitor
from pythoscope.astbuilder import parse, ParseError

def get_code_metrics_from_file(code):
    def not_blank_nor_comment(line):
        return not (line.lstrip() == '' or line.lstrip().startswith('#'))
    class ModuleVisitor(ASTVisitor):
        def __init__(self):
            ASTVisitor.__init__(self)
            self.functions = 0
            self.classes = 0
            self.methods = 0
        def visit_class(self, name, bases, body):
            visitor = descend(body.children, ClassVisitor)
            self.methods += visitor.methods
            self.classes += 1
        def visit_function(self, name, args, body):
            self.functions += 1
    class ClassVisitor(ASTVisitor):
        def __init__(self):
            ASTVisitor.__init__(self)
            self.methods = 0
        def visit_function(self, name, args, body):
            self.methods += 1
    try:
        tree = parse(code)
    except ParseError, e:
        notify("Caught parse error: %s." % e)
        raise GatheringError("Failed at code metrics.")
    visitor = descend(tree, ModuleVisitor)

    loc = len(filter(not_blank_nor_comment, code.splitlines()))
    return loc, visitor.functions, visitor.classes, visitor.methods

# A copy from pythoscope.inspector.file_system.
def rlistdir(path):
    """Resursive directory listing. Yield all files below given path,
    ignoring those which names begin with a dot.
    """
    if os.path.basename(path).startswith('.'):
        return

    if os.path.isdir(path):
        for entry in os.listdir(path):
            for subpath in rlistdir(os.path.join(path, entry)):
                yield subpath
    else:
        yield path

# A copy from pythoscope.inspector.file_system.
def python_modules_below(path):
    VCS_PATHS = set([".bzr", "CVS", "_darcs", ".git", ".hg", ".svn"])
    def is_python_module(path):
        return path.endswith(".py")
    def not_vcs_file(path):
        return not set(path.split(os.path.sep)).intersection(VCS_PATHS)
    return filter(not_vcs_file, filter(is_python_module, rlistdir(path)))

# A copy from pythoscope.util.
def file_mode(base, binary):
    if binary:
        return base + 'b'
    return base

# A copy from pythoscope.util.
def read_file_contents(filename, binary=False):
    fd = file(filename, file_mode('r', binary))
    contents = fd.read()
    fd.close()
    return contents

# loc, functions, classes, methods
def get_code_metrics(project_path):
    metrics = []
    for mod in python_modules_below(project_path):
        code = read_file_contents(mod)
        metrics.append(get_code_metrics_from_file(code))
    return map(sum, zip(*metrics))

################################################################################
#  CODE METRICS CODE end
################################################################################


def do_pythoscope_init(project_path):
    notify("Doing pythoscope --init...")
    status = os.system("pythoscope --init %s" % project_path)
    notify("Done.")
    if status != 0:
        raise GatheringError("Failed at static inspection.")

def put_point_of_entry(poe, project_dir):
    notify("Copying point of entry %s..." % poe)
    shutil.copy(os.path.join(PREFIX, poe),
        os.path.join(project_dir, ".pythoscope", "points-of-entry"))
    notify("Done.")

def run_snippet(snippet, project_dir):
    notify("Copying and running snippet %s..." % snippet)
    shutil.copy(os.path.join(PREFIX, snippet), project_dir)
    status, output = commands.getstatusoutput("(cd %s ; python2.6 %s)" % (project_dir, snippet))
    print output
    notify("Done.")

def generate_tests_for_file(project_dir, appfile):
    notify("Generating tests for %s..." % appfile)
    status, output = commands.getstatusoutput("pythoscope --verbose -t nose %s" % os.path.join(project_dir, appfile))
    print output
    if contains_dynamic_inspection_error(output):
        raise GatheringError("Failed at dynamic inspection.")
    if status != 0:
        raise GatheringError("Failed during test generation: exited with code=%d." % status)
    notify("Done.")

def contains_dynamic_inspection_error(output):
    return "Point of entry exited with error" in output

def run_nosetests(project_dir, test_path):
    notify("Running nosetests on the generated test module...")
    command = "PYTHONPATH=%s nosetests -w %s %s" % (project_dir, project_dir, test_path)
    print "    $", command
    status, output = commands.getstatusoutput(command)
    print output
    if status not in [0, 256]:
        raise GatheringError("Failed during test run: nosetests exited with code=%d." % status)
    counts = get_test_counts(output)
    notify("Done.")
    return counts

def get_test_counts(output):
    lines = output.splitlines()
    if 'DeprecationWarning' in lines[0]:
        line = lines[2]
    else:
        line = lines[0]
    return line.count('.'), line.count('S'), line.count('E'), line.count('F')

def run_nosetests_with_coverage(project_dir, test_path, cover_package):
    notify("Running nosetests with coverage on the generated test module...")
    command = "PYTHONPATH=%s nosetests --with-coverage --cover-package=%s -w %s %s" % (project_dir, cover_package, project_dir, test_path)
    print "    $", command
    status, output = commands.getstatusoutput(command)
    print output
    if status not in [0, 256]:
        raise GatheringError("Failed during test run: nosetests+coverage exited with code=%d." % status)
    coverage = extract_coverage_percent(output)
    notify("Done.")
    return coverage

def extract_coverage_percent(output):
    for line in output.splitlines():
        if line.startswith("TOTAL"):
            return line.split()[3]
    else:
        # If there was only one module, coverage doesn't report TOTAL.
        for line in output.splitlines():
            if "%" in line:
                return line.split()[3]
    raise GatheringError("Can't find coverage in the output.")

def cleanup_project(project_dir):
    notify("Cleaning up %s..." % project_dir)
    shutil.rmtree(project_dir)
    notify("Done.")

def path_exists(path):
    return os.path.exists(path) or glob.glob(path) != []

def gather_metrics_from_project(project, poes, snippets, appfile, testfile, cover_package, python_path=None):
    check_environment()
    temp_dir = prepare_project(project)
    project_dir = os.path.join(temp_dir, project)
    try:
        loc, functions, classes, methods = get_code_metrics(project_dir)
        do_pythoscope_init(project_dir)
        for poe in poes:
            put_point_of_entry(poe, project_dir)
        for snippet in snippets:
            run_snippet(snippet, project_dir)
        generate_tests_for_file(project_dir, appfile)
        test_path = os.path.join(project_dir, testfile)
        if not path_exists(test_path):
            raise GatheringError("Failed at test generation: test file not generated.")
        passed, skipped, errors, failures = run_nosetests(project_dir, test_path)
        coverage = run_nosetests_with_coverage(project_dir, test_path, cover_package)
        return GatheringResults(loc, functions, classes, methods, passed, skipped, errors, failures, coverage)
    finally:
        cleanup_project(temp_dir)

def main():
    projects = [
        dict(project="Reverend-r17924",
             poes=["Reverend_poe_from_readme.py", "Reverend_poe_from_homepage.py"],
             snippets=[],
             appfile="reverend/thomas.py",
             testfile="tests/test_reverend_thomas.py",
             cover_package="reverend"),
        dict(project="freshwall-1.1.2-lib",
             poes=[],
             snippets=["freshwall_bin_with_snippet.py"],
             appfile="freshwall/*.py",
             testfile="tests/*.py",
             cover_package="freshwall"),
        dict(project="http-parser-0.2.0",
             poes=[],
             snippets=["http-parser-example-1.py", "http-parser-example-2.py"],
             appfile="http_parser/*.py",
             testfile="tests/*.py",
             cover_package="http_parser"),
        dict(project="isodate-0.4.4-src",
             poes=["isodate_poe.py"],
             snippets=[],
             appfile="isodate/*.py",
             testfile="tests/*.py",
             cover_package="isodate"),
        dict(project="pyatom-1.2",
             poes=["pyatom_poe_from_readme.py"],
             snippets=[],
             appfile="pyatom.py",
             testfile="tests/*.py",
             cover_package="pyatom"),
        ]
    results = []
    for project in projects:
        try:
            results.append(gather_metrics_from_project(**project))
        except GatheringError, e:
            print e.args[0]
            results.append(None)
    for project, result in zip(projects, results):
        print
        print project['project']
        print "-"*40
        if result:
            print "%d LOC, %d functions, %d classes, %d methods" % \
                (result.loc, result.functions, result.classes, result.methods)
            print "%d test cases:" % result.total
            print "  %d passing" % result.passed
            print "  %d failing" % (result.failures + result.errors)
            print "  %d stubs" % result.skipped
            print "%s coverage" % result.coverage

if __name__ == '__main__':
    sys.exit(main())

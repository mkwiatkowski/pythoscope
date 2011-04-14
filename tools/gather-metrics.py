import commands
import os
import shutil
import sys
import tarfile
import tempfile


PREFIX = os.path.abspath(os.path.join(os.path.dirname(__file__), 'projects'))

class GatheringError(Exception):
    pass

class GatheringResults(object):
    def __init__(self, passed, skipped, errors, failures, coverage):
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
    status, output = commands.getstatusoutput("nosetests -w %s %s" % (project_dir, test_path))
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

def run_nosetests_with_coverage(project_dir, test_path):
    notify("Running nosetests with coverage on the generated test module...")
    status, output = commands.getstatusoutput("nosetests --with-coverage --cover-package=reverend -w %s %s" % (project_dir, test_path))
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
    raise GatheringError("Can't find coverage in the output.")

def cleanup_project(project_dir):
    notify("Cleaning up %s..." % project_dir)
    shutil.rmtree(project_dir)
    notify("Done.")

def gather_metrics_from_project(project, poes, appfile, testfile):
    check_environment()
    temp_dir = prepare_project(project)
    project_dir = os.path.join(temp_dir, project)
    try:
        do_pythoscope_init(project_dir)
        for poe in poes:
            put_point_of_entry(poe, project_dir)
        generate_tests_for_file(project_dir, appfile)
        test_path = os.path.join(project_dir, testfile)
        if not os.path.exists(test_path):
            raise GatheringError("Failed at test generation: test file not generated.")
        passed, skipped, errors, failures = run_nosetests(project_dir, test_path)
        coverage = run_nosetests_with_coverage(project_dir, test_path)
        return GatheringResults(passed, skipped, errors, failures, coverage)
    finally:
        cleanup_project(temp_dir)

def main():
    try:
        results = gather_metrics_from_project(project="Reverend-r17924",
            poes=["Reverend_poe_from_readme.py", "Reverend_poe_from_homepage.py"],
            appfile="reverend/thomas.py",
            testfile="tests/test_reverend_thomas.py")
        print "%d test cases:" % results.total
        print "  %d passing" % results.passed
        print "  %d failing" % (results.failures + results.errors)
        print "  %d stubs" % results.skipped
        print "%s coverage" % results.coverage
    except GatheringError, e:
        print e.args[0]

if __name__ == '__main__':
    sys.exit(main())

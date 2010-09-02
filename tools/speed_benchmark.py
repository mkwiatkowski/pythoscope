from __future__ import division

import gc
import os.path
import sys
import timeit

pythoscope_path = os.path.join(os.path.dirname(__file__), os.pardir)
sys.path.insert(0, os.path.abspath(pythoscope_path))

from pythoscope.cmdline import init_project
from pythoscope.store import get_pickle_path
from test.helper import putfile, rmtree, tmpdir


def make_class(name, methods_count=20):
    code = ["class %s(object):\n" % name]
    for i in range(methods_count):
        code.append("    def method_%d(self):\n        pass\n" % i)
    return ''.join(code)

def make_function(name):
    return "def %s():\n    pass\n" % name

def make_module(classes_count=10, functions_count=10):
    code = []
    for i in range(classes_count):
        code.append(make_class("Class%d" % i))
    for i in range(functions_count):
        code.append(make_function("function_%d" % i))
    return ''.join(code)

# Run the setup once, stmt n times and report the minimum running time.
#
# Based on timeit module. I had to modify it, because:
#  - timer.timeit(n) returns time of running stmt n times (the sum, not the minimum),
#  - min(timer.repeat(n, 1)) runs the setup n times.
timer_template = """
def inner(_n, _timer):
    _results = []
    %(setup)s
    for _i in range(_n):
        _t0 = _timer()
        %(stmt)s
        _t1 = _timer()
        _results.append(_t1 - _t0)
    return min(_results)
"""

def run_timer(stmt, setup, n=3, timer=timeit.default_timer):
    src = timer_template % {'stmt': stmt, 'setup': setup}
    code = compile(src, '', "exec")
    ns = {}
    exec code in globals(), ns
    inner = ns["inner"]

    gcold = gc.isenabled()
    gc.disable()
    timing = inner(n, timer)
    if gcold:
        gc.enable()
    return timing

def human_size(bytes, prefixes=['', 'K', 'M', 'G']):
    if bytes > 1024:
        return human_size(bytes/1024, prefixes[1:])
    return "%.2f%sb" % (bytes, prefixes[0])

def benchmark_project_load_performance(modules_count=25):
    print "==> Creating project with %d modules..." % modules_count
    project_path = tmpdir()
    module = make_module()
    for i in range(modules_count):
        putfile(project_path, "module%s.py" % i, module)
    init_project(project_path, skip_inspection=True)

    print "==> Inspecting project.."
    elapsed = run_timer("inspect_project(Project('%s'))" % project_path,
                        "from pythoscope.inspector import inspect_project; from pythoscope.store import Project")
    print "It took %f seconds to inspect." % elapsed

    print "==> Saving project information"
    elapsed = run_timer("project.save()",
                        """from pythoscope.inspector import inspect_project ;\
                           from pythoscope.store import Project ;\
                           project = Project('%s') ;\
                           inspect_project(project)""" % project_path)
    print "It took %f seconds to save the project information." % elapsed

    print "==> Reading project information"
    elapsed = run_timer("Project.from_directory('%s')" % project_path,
                        "from pythoscope.store import Project")
    print "It took %f seconds to read project information from %s pickle." % \
        (elapsed, human_size(os.path.getsize(get_pickle_path(project_path))))

    rmtree(project_path)

if __name__ == "__main__":
    benchmark_project_load_performance()

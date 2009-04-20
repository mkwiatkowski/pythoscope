import sys

import pythoscope
from pythoscope import inspect_project_statically
from pythoscope.store import Module, Class, Function, Method, CodeTree
from pympler import heapmonitor

if len(sys.argv) != 2:
    print "usage:\n  %s application_path\n" % sys.argv[0]
    print "application_path should point to a directory containing\n"\
          "the project you wish to test pythoscope memory usage on.\n"\
          "It should *not* be initialized (as in pythoscope --init)."
    sys.exit(1)

def setup_tracking(project):
    heapmonitor.track_object(project)
    heapmonitor.track_class(Module)
    heapmonitor.track_class(Class)
    heapmonitor.track_class(Function)
    heapmonitor.track_class(Method)
    heapmonitor.track_class(CodeTree)
    heapmonitor.create_snapshot()

    # Finally call the real inspector.
    inspect_project_statically(project)

def benchmark_project_memory_usage():
    # Take the argument to this script and inject it as an argument to
    # pythoscope's --init.
    application_path = sys.argv[1]
    sys.argv = ["pythoscope", "--init", application_path]

    # Inject a setup function before performing an inspection.
    pythoscope.inspect_project_statically = setup_tracking

    # Invoke pythoscope --init.
    pythoscope.main()

    # Show statistics.
    heapmonitor.create_snapshot()
    heapmonitor.print_stats(detailed=False)

if __name__ == "__main__":
    benchmark_project_memory_usage()

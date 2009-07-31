"""Module containing code that has to be executed before any of the tests.
"""

# Make pythoscope importable directly from the test modules.
import os, sys
pythoscope_path = os.path.join(os.path.dirname(__file__), os.pardir)
sys.path.insert(0, os.path.abspath(pythoscope_path))

# Make sys.stdout the logger's output stream, so nose capture
# plugin can get hold of it.
# We can't set_output to sys.stdout directly, because capture
# plugin changes that before each test.
class AlwaysCurrentStdout:
    def __getattr__(self, name):
        return getattr(sys.stdout, name)
from pythoscope.logger import DEBUG, log, set_output
set_output(AlwaysCurrentStdout())
log.level = DEBUG

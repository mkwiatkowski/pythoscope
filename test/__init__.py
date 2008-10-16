# Make pythoscope importable directly from the test modules.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Make sys.stdout the logger's output stream, so nose capture
# plugin can get hold of it.
from pythoscope.logger import set_output
set_output(sys.stdout)

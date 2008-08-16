# Make pythoscope importable directly from the test modules.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pythoscope.astbuilder import parse, regenerate

from assertions import *


class TestParser:
    def test_handles_inputs_without_newline(self):
        tree = parse("42 # answer")
        assert_equal("42 # answer", regenerate(tree))


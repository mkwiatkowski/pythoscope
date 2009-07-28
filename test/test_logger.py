from pythoscope.logger import log, path2modname

from assertions import *
from helper import CapturedLogger, CapturedDebugLogger, P


class TestLogger(CapturedLogger):
    def test_info_message_in_normal_mode(self):
        log.info("Log this")
        assert_equal_strings("INFO: Log this\n", self.captured.getvalue())

class TestDebugLogger(CapturedDebugLogger):
    def test_info_message_in_debug_mode(self):
        log.info("Log that")
        assert_matches(r"\d+\.\d+ .*test_logger:\d+ INFO: Log that\n",
                       self._get_log_output())

class TestPath2Modname:
    def test_path2modname(self):
        assert_equal('astvisitor', path2modname(P("sth/pythoscope/astvisitor.py")))
        assert_equal('generator', path2modname(P("sth/pythoscope/generator/__init__.py")))
        assert_equal('generator.adder', path2modname(P("sth/pythoscope/generator/adder.py")))

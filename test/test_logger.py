from helper import assert_equal_strings, assert_matches, CapturedLogger, \
    CapturedDebugLogger

from pythoscope.logger import log


class TestLogger(CapturedLogger):
    def test_info_message_in_normal_mode(self):
        log.info("Log this")
        assert_equal_strings("INFO: Log this\n", self.captured.getvalue())

class TestDebugLogger(CapturedDebugLogger):
    def test_info_message_in_debug_mode(self):
        log.info("Log that")
        assert_matches(r"\d+\.\d+ .*test_logger:\d+ INFO: Log that\n",
                       self._get_log_output())

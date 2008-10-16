from helper import assert_equal_strings, assert_matches, CapturedLogger

from pythoscope.logger import log, DEBUG, INFO


class TestLogger(CapturedLogger):
    def test_info_message_in_normal_mode(self):
        log.info("Log this")
        assert_equal_strings("INFO: Log this\n", self.captured.getvalue())

    def test_info_message_in_debug_mode(self):
        log.level = DEBUG
        try:
            log.info("Log that")
            assert_matches(r"\d+\.\d+ test_logger:\d+ INFO: Log that\n",
                           self._get_log_output())
        finally:
            log.level = INFO

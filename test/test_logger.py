from StringIO import StringIO

from helper import assert_equal_strings, assert_matches

from pythoscope.logger import log, get_output, set_output, DEBUG, INFO


class TestLogger:
    def setUp(self):
        self._old_output = get_output()
        self.captured = StringIO()
        set_output(self.captured)

    def tearDown(self):
        set_output(self._old_output)

    def test_info_message_in_normal_mode(self):
        log.info("Log this")
        assert_equal_strings("INFO: Log this\n", self.captured.getvalue())

    def test_info_message_in_debug_mode(self):
        log.level = DEBUG
        try:
            log.info("Log that")
            assert_matches(r"\d+\.\d+ test_logger:\d+ INFO: Log that\n",
                           self.captured.getvalue())
        finally:
            log.level = INFO

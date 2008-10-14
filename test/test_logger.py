import types
import unittest
from cStringIO import StringIO

from nose.tools import assert_equal
from pythoscope.logger import log
from helper import random_string


class TestLogger(unittest.TestCase):
    def test_info_message(self):
        log_str = random_string()
        captured_io = StringIO()
        old_stream = log.handlers[0].stream 
        log.handlers[0].stream = captured_io
        log.info(log_str)
        log.handlers[0].stream = old_stream
        assert_equal(captured_io.getvalue(),  'INFO: %s\n'%log_str)


if __name__ == '__main__':
    unittest.main()


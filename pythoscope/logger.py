"""This module defines the logging system.

To change the logging level, assign INFO, DEBUG or ERROR to log.level. Default
is INFO.

To change the output stream, call the set_output() function. Default is
sys.stderr.
"""

import logging

from time import strftime, localtime

INFO  = logging.INFO
DEBUG = logging.DEBUG
ERROR = logging.ERROR


class LogFormatter(logging.Formatter):
    def format(self, record):
        """Show a message with a loglevel in normal verbosity mode and much more
        in debug mode.
        """
        message = "%s: %s" % (record.levelname, record.getMessage())
        if log.level == DEBUG:
            return "%s.%d %s:%d %s" % \
                (strftime("%H%M%S", localtime(record.created)),
                 record.msecs,
                 record.module,
                 record.lineno,
                 message)
        return message

def setup():
    handler = logging.StreamHandler()
    handler.setFormatter(LogFormatter())
    log.addHandler(handler)
    log.level = INFO

def get_output():
    return log.handlers[0].stream

def set_output(stream):
    "Change the output of all the logging calls to go to given stream."
    log.handlers[0].stream = stream

log = logging.getLogger('pythoscope')
setup()

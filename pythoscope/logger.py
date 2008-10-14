""" This module defines the logging singleton.  All output should go though it.
"""
import sys
import logging
from time import strftime, localtime

INFO  = logging.INFO
DEBUG = logging.DEBUG
ERROR = logging.ERROR


class LogFormatter(logging.Formatter):
    """ This is the a custom formatter class """

    def format(self, record):
        """ The formatting is dependant verbosity level.
            When in debug it will show lots more information.
        """
        if log.level == DEBUG:
            format_str = "%(asctime)s.%(msecs)d %(module)s:"
            format_str += "%(lineno)d %(levelname)s %(message)s"
            msgDict = {}
            msgDict['asctime'] = strftime("%H%M%S", localtime(record.created))
            msgDict['msecs'] = record.msecs
            msgDict['module'] = record.module
            msgDict['lineno'] = record.lineno
            msgDict['levelname'] = record.levelname
            msgDict['message'] = record.getMessage()
            format_str %= msgDict
        else:
            format_str = '%s: %s' % (record.levelname, record.getMessage())
        return format_str


# Only assign log if it hasn't been assigned
try: 
    log
except:
    log = logging.getLogger('pythoscope')
    handler = logging.StreamHandler()
    formatter = LogFormatter()
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.level = logging.INFO

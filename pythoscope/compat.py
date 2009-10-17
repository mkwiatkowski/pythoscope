"""Portability code for different Python versions and platforms.
"""

import os
import warnings


try:
    all = all
except NameError:
    def all(iterable):
        for element in iterable:
            if not element:
                return False
        return True

try:
    any = any
except NameError:
    def any(iterable):
        for element in iterable:
            if element:
                return True
        return False

try:
    set = set
except NameError:
    from sets import Set as set

try:
    frozenset = frozenset
except NameError:
    from sets import ImmutableSet as frozenset

try:
    sorted = sorted
except NameError:
    def sorted(iterable, compare=cmp, key=None):
        if key:
            compare = lambda x,y: cmp(key(x), key(y))
        alist = list(iterable)
        alist.sort(compare)
        return alist

try:
    from itertools import groupby
except ImportError:
    # Code taken from http://docs.python.org/lib/itertools-functions.html .
    class groupby(object):
        def __init__(self, iterable, key=None):
            if key is None:
                key = lambda x: x
            self.keyfunc = key
            self.it = iter(iterable)
            self.tgtkey = self.currkey = self.currvalue = xrange(0)
        def __iter__(self):
            return self
        def next(self):
            while self.currkey == self.tgtkey:
                self.currvalue = self.it.next() # Exit on StopIteration
                self.currkey = self.keyfunc(self.currvalue)
            self.tgtkey = self.currkey
            return (self.currkey, self._grouper(self.tgtkey))
        def _grouper(self, tgtkey):
            while self.currkey == tgtkey:
                yield self.currvalue
                self.currvalue = self.it.next() # Exit on StopIteration
                self.currkey = self.keyfunc(self.currvalue)

try:
    from os.path import samefile
except ImportError:
    def samefile(file1, file2):
        return os.path.realpath(file1) == os.path.realpath(file2)

# Ignore Python's 2.6 deprecation warning for sets module.
warnings.simplefilter('ignore')
import sets
warnings.resetwarnings()

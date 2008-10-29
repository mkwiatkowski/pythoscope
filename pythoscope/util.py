import gc
import os
import re
import types
import warnings

# Portability code.
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
    def sorted(iterable, cmp=cmp, key=None):
        if key:
            cmp = lambda x,y: cmp(key(x), key(y))
        alist = list(iterable)
        alist.sort(cmp)
        return alist

try:
    all = all
except NameError:
    def all(iterable):
        for element in iterable:
            if not element:
                return False
        return True

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

def camelize(name):
    """Covert name into CamelCase.

    >>> camelize('underscore_name')
    'UnderscoreName'
    >>> camelize('AlreadyCamelCase')
    'AlreadyCamelCase'
    >>> camelize('')
    ''
    """
    def upcase(match):
        return match.group(1).upper()
    return re.sub(r'(?:^|_)(.)', upcase, name)


def underscore(name):
    """Convert name into underscore_name.

    >>> underscore('CamelCase')
    'camel_case'
    >>> underscore('already_underscore_name')
    'already_underscore_name'
    >>> underscore('BigHTMLClass')
    'big_html_class'
    >>> underscore('')
    ''
    """
    if name and name[0].isupper():
        name = name[0].lower() + name[1:]

    def capitalize(match):
        string = match.group(1).capitalize()
        return string[:-1] + string[-1].upper()

    def underscore(match):
        return '_' + match.group(1).lower()

    name = re.sub(r'([A-Z]+)', capitalize, name)
    return re.sub(r'([A-Z])', underscore, name)

def read_file_contents(filename):
    fd = file(filename)
    contents = fd.read()
    fd.close()
    return contents

def write_string_to_file(string, filename):
    fd = file(filename, 'w')
    fd.write(string)
    fd.close()

def all_of_type(objects, type):
    """Return all objects that are instances of a given type.
    """
    return [o for o in objects if isinstance(o, type)]

def max_by_not_zero(func, collection):
    """Return the element of a collection for which func returns the highest
    value, greater than 0.

    Return None if there is no such value.

    >>> max_by_not_zero(len, ["abc", "d", "ef"])
    'abc'
    >>> max_by_not_zero(lambda x: x, [0, 0, 0, 0]) is None
    True
    >>> max_by_not_zero(None, []) is None
    True
    """
    if not collection:
        return None

    def annotate(element):
        return (func(element), element)

    highest = max(map(annotate, collection))
    if highest and highest[0] > 0:
        return highest[1]
    else:
        return None

def python_modules_below(path):
    def is_python_module(path):
        return path.endswith(".py")
    return filter(is_python_module, rlistdir(path))

def rlistdir(path):
    """Resursive directory listing. Yield all files below given path,
    ignoring those which names begin with a dot.
    """
    if os.path.basename(path).startswith('.'):
        return

    if os.path.isdir(path):
        for entry in os.listdir(path):
            for subpath in rlistdir(os.path.join(path, entry)):
                yield subpath
    else:
        yield path

def get_names(objects):
    return map(lambda c: c.name, objects)

class DirectoryException(Exception):
    pass

def ensure_directory(directory):
    """Make sure given directory exists, creating it if necessary.
    """
    if os.path.exists(directory):
        if not os.path.isdir(directory):
            raise DirectoryException("Destination is not a directory.")
    else:
        os.makedirs(directory)

def get_last_modification_time(path):
    try:
        # Casting to int, because we don't need better resolution anyway and it
        # eases testing on different OSes.
        return int(os.path.getmtime(path))
    except OSError:
        # File may not exist, in which case it was never modified.
        return 0

def extract_subpath(path, prefix):
    """Remove prefix from given path to generate subpath, so the following
    correspondence is preserved:

      path <=> os.path.join(prefix, subpath)

    in terms of physical path (i.e. not necessarily strict string
    equality).
    """
    prefix_length = len(prefix)
    if not prefix.endswith(os.path.sep):
        prefix_length += 1
    return os.path.realpath(path)[prefix_length:]

def directories_under(path):
    """Return names of directories under given path (not recursive).
    """
    for entry in os.listdir(path):
        if os.path.isdir(os.path.join(path, entry)):
            yield entry

def findfirst(pred, seq):
    """Return the first element of given sequence that matches predicate.
    """
    for item in seq:
        if pred(item):
            return item

def contains_active_generator(frame):
    return bool(all_of_type(gc.get_referrers(frame), types.GeneratorType))

def is_generator_code(code):
    return code.co_flags & 0x20 != 0

def compile_without_warnings(stmt):
    """Compile single interactive statement with Python interpreter warnings
    disabled.
    """
    warnings.simplefilter('ignore')
    code = compile(stmt, '', 'single')
    warnings.resetwarnings()
    return code

def quoted_block(text):
    return ''.join(["> %s" % line for line in text.splitlines(True)])

# Regular expressions helpers.

RePatternType = type(re.compile(''))

def regexp_flags_as_string(flags):
    """Return an expression in string form that corresponds to given set of
    regexp flags.
    """
    strings = []
    if flags & re.IGNORECASE:
        strings.append('re.IGNORECASE')
    if flags & re.LOCALE:
        strings.append('re.LOCALE')
    if flags & re.MULTILINE:
        strings.append('re.MULTILINE')
    if flags & re.DOTALL:
        strings.append('re.DOTALL')
    if flags & re.VERBOSE:
        strings.append('re.VERBOSE')
    if flags & re.UNICODE:
        strings.append('re.UNICODE')
    return " | ".join(strings)

import gc
import itertools
import operator
import os
import re
import sys
import traceback
import types
import warnings

from pythoscope.compat import groupby, set, sorted


def compact(lst):
    "Remove all occurences of None from the given list."
    return [x for x in lst if x is not None]

def counted(objects):
    """Count how many times each object appears in a list and return
    list of (object, count) tuples.

    >>> counted(['a', 'b', 'c', 'a', 'b', 'a'])
    [('a', 3), ('b', 2), ('c', 1)]
    >>> counted([])
    []
    """
    return [(obj, len(list(group))) for obj, group in groupby(sorted(objects))]

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

def pluralize(word, count):
    """Depending on the counter, return a singular or a plural form of the
    given word.

    >>> pluralize("word", 1)
    'one word'
    >>> pluralize("word", 2)
    '2 words'
    """
    if count == 1:
        return "one %s" % word
    else:
        return "%d %ss" % (count, word)

# :: string -> string
def string2id(string):
    """Remove from string all characters that cannot be used in an identifier.
    """
    return re.sub(r'[^a-zA-Z0-9_]', '', re.sub(r'\s+', '_', string.strip()))

# :: string -> string
def string2filename(string):
    """Remove from string all characters that cannot be used in a file name.

    >>> string2filename('file.txt')
    'file.txt'
    >>> string2filename(os.path.join('package', 'module.py'))
    'package_module.py'
    >>> string2filename(os.path.join('directory with spaces', 'file.with.dots'))
    'directory with spaces_file.with.dots'
    """
    return re.sub(re.escape(os.path.sep), '_', string)

def file_mode(base, binary):
    if binary:
        return base + 'b'
    return base

def read_file_contents(filename, binary=False):
    fd = file(filename, file_mode('r', binary))
    contents = fd.read()
    fd.close()
    return contents

def write_content_to_file(string, filename, binary=False):
    fd = file(filename, file_mode('w', binary))
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
    VCS_PATHS = set([".bzr", "CVS", "_darcs", ".git", ".hg", ".svn"])
    def is_python_module(path):
        return path.endswith(".py")
    def not_vcs_file(path):
        return not set(path.split(os.path.sep)).intersection(VCS_PATHS)
    return filter(not_vcs_file, filter(is_python_module, rlistdir(path)))

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

def map_values(function, dictionary):
    new_dictionary = {}
    for key, value in dictionary.iteritems():
        new_dictionary[key] = function(value)
    return new_dictionary

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

def starts_with_path(path, prefix):
    """Return True if given path starts with given prefix and False otherwise.
    """
    return os.path.realpath(path).startswith(os.path.realpath(prefix))

def extract_subpath(path, prefix):
    """Remove prefix from given path to generate subpath, so the following
    correspondence is preserved:

      path <=> os.path.join(prefix, subpath)

    in terms of physical path (i.e. not necessarily strict string
    equality).
    """
    prefix = os.path.realpath(prefix)
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

def flatten(lst):
    """Flatten given list.

    >>> flatten([[1, 2, 3], [4, 5], [6, 7], [8]])
    [1, 2, 3, 4, 5, 6, 7, 8]
    """
    return list(itertools.chain(*lst))

# :: [set] -> set
def union(*sets):
    """Return a union of all the given sets.
    """
    # Since 2.6 set.union accepts multiple input iterables.
    if sys.version_info >= (2, 6):
        return set.union(*sets)
    else:
        return reduce(operator.or_, sets, set())

# :: dict, object -> object
def key_for_value(dictionary, value):
    """Return the first key of dictionary that maps to given value.

    >>> key_for_value({'a': 1, 'b': 2}, 2)
    'b'
    >>> key_for_value({}, 1)
    """
    for k, v in dictionary.iteritems():
        if v == value:
            return k

def get_generator_from_frame(frame):
    generators = all_of_type(gc.get_referrers(frame), types.GeneratorType)
    if generators:
        return generators[0]

def is_generator_code(code):
    return code.co_flags & 0x20 != 0

def generator_has_ended(generator):
    """Return True if the generator has been exhausted and False otherwise.

    >>> generator_has_ended(1)
    Traceback (most recent call last):
      ...
    TypeError: argument is not a generator
    """
    if not isinstance(generator, types.GeneratorType):
        raise TypeError("argument is not a generator")
    return _generator_has_ended(generator)

try:
    from _util import _generator_has_ended
except ImportError:
    if sys.version_info < (2, 5):
        # In Python 2.4 and earlier we can't reliably tell if a generator
        # is active or not without going to the C level. We assume it
        # has ended, as it will be true most of the time in our use case.
        def _generator_has_ended(generator):
            return True
        generator_has_ended.unreliable = True
    else:
        # This is a hack that uses the fact that in Python 2.5 and higher
        # generator frame is garbage collected once the generator has ended.
        def _generator_has_ended(generator):
            return generator.gi_frame is None

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

def class_of(obj):
    if hasattr(obj, "__class__"):
        return obj.__class__
    return type(obj)

def class_name(obj):
    return class_of(obj).__name__

def module_name(obj):
    return class_of(obj).__module__

def module_path_to_name(module_path, newsep="_"):
    return re.sub(r'(%s__init__)?\.py$' % re.escape(os.path.sep), '', module_path).\
        replace(os.path.sep, newsep)

def last_traceback():
    return "".join(traceback.format_tb(sys.exc_info()[2]))

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

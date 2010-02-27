import difflib
import re

from nose.tools import assert_equal, assert_not_equal, assert_raises

from pythoscope.compat import set
from pythoscope.util import quoted_block

__all__ = [
    # Nose assertions.
    "assert_equal",
    "assert_not_equal",
    "assert_raises",

    # Our assertions.
    "assert_contains",
    "assert_contains_once",
    "assert_contains_one_after_another",
    "assert_doesnt_contain",
    "assert_equal_sets",
    "assert_equal_strings",
    "assert_function",
    "assert_instance",
    "assert_length",
    "assert_matches",
    "assert_not_raises",
    "assert_single_class",
    "assert_single_function"]


def assert_contains(haystack, needle):
    assert needle in haystack,\
           "Expected\n%s\nto contain %r, but it didn't." % (quoted_block(haystack), needle)

def assert_contains_once(haystack, needle):
    repeated = len(re.findall(re.escape(needle), haystack))
    assert repeated == 1, "Expected\n%s\nto contain %r once, but it contained it %d times instead." %\
           (quoted_block(haystack), needle, repeated)

def assert_contains_one_after_another(haystack, needle1, needle2):
    assert re.search(''.join([needle1, '.*', needle2]), haystack, re.DOTALL), \
        "Expected\n%s\nto contain %r and then %r, but it didn't." %\
           (quoted_block(haystack), needle1, needle2)

def assert_doesnt_contain(haystack, needle):
    assert needle not in haystack,\
           "Expected\n%s\nto NOT contain %r, but it did." % (quoted_block(haystack), needle)

def assert_equal_sets(collection1, collection2):
    """Assert that both collections have the same number and set of elements.
    """
    # Checking length of both collections first, so we catch duplicates that
    # appear in one collection and not the other.
    assert_length(collection2, len(collection1))
    assert_equal(set(collection1), set(collection2))

def assert_equal_strings(s1, s2):
    assert_equal(s1, s2, "Strings not equal. Diff:\n\n%s" % ''.join(difflib.ndiff(s1.splitlines(True), s2.splitlines(True))))

def assert_function(function, name, args):
    assert_equal(name, function.name)
    assert_equal(args, function.args)

def assert_instance(obj, objtype):
    assert isinstance(obj, objtype), \
           "Expected object %r to be of type %r, it was of type %r instead." % \
           (obj, objtype, type(obj))

def assert_length(collection, expected_length):
    actual_length = len(collection)
    assert expected_length == actual_length,\
           "Expected collection to have %d elements, it had %d instead." %\
           (expected_length, actual_length)

def assert_matches(regexp, string, anywhere=False):
    if anywhere:
        match = re.search
    else:
        match = re.match
    assert match(regexp, string, re.DOTALL), \
        "Expected\n%s\nto match r'%s', but it didn't." % (quoted_block(string), regexp)

def assert_not_raises(exception, function):
    try:
        function()
    except exception:
        assert False, "Exception %s has been raised." % exception

def assert_single_class(info, name):
    assert_length(info.classes, 1)
    assert_equal(name, info.classes[0].name)

def assert_single_function(info, name, args=None):
    assert_length(info.functions, 1)
    assert_equal(name, info.functions[0].name)
    if args is not None:
        assert_equal(args, info.functions[0].args)

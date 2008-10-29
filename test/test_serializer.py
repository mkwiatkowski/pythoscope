import sets
import sys

from nose.exc import SkipTest
from helper import assert_equal_sets, assert_equal_strings

from pythoscope.serializer import get_reconstructor_with_imports


class TestSerializer:
    def test_reconstructs_set_from_sets_module(self):
        reconstructor, imports = get_reconstructor_with_imports(sets.Set([1, 2, 3]))

        assert_equal_strings("Set([1, 2, 3])", reconstructor)
        assert_equal_sets([("sets", "Set")], imports)

    def test_reconstructs_immutable_set_from_sets_module(self):
        reconstructor, imports = get_reconstructor_with_imports(sets.ImmutableSet([1, 2, 3]))

        assert_equal_strings("ImmutableSet([1, 2, 3])", reconstructor)
        assert_equal_sets([("sets", "ImmutableSet")], imports)

    def test_reconstructs_builtin_set(self):
        # Set builtin was added in Python 2.4.
        if sys.version_info < (2, 4):
            raise SkipTest

        reconstructor, imports = get_reconstructor_with_imports(set([1, 2, 3]))

        assert_equal_strings("set([1, 2, 3])", reconstructor)
        assert_equal_sets([], imports)

    def test_reconstructs_builtin_frozenset(self):
        # Frozenset builtin was added in Python 2.4.
        if sys.version_info < (2, 4):
            raise SkipTest

        reconstructor, imports = get_reconstructor_with_imports(frozenset([1, 2, 3]))

        assert_equal_strings("frozenset([1, 2, 3])", reconstructor)
        assert_equal_sets([], imports)

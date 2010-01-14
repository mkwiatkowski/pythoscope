"""An easy way to create domain objects with required parameters, which aren't
always important during testing.

This loosely follows Creation Method pattern (see
<http://xunitpatterns.com/Creation%20Method.html> for details).

First, register a factory for some domain object.
    >>> class Struct:
    ...     def __init__(self, name):
    ...         self.name = name
    >>> register_factory(Struct, name="nice_structure")

Now, use it in tests:
    >>> struct = create(Struct)
    >>> struct.name
    'nice_structure'

You can also overload defaults if you want:
    >>> struct = create(Struct, name="my_struct")
    >>> struct.name
    'my_struct'

Sometimes you want to generate an attribute each time the object is created.
In that cases use register_dynamic_factory:
    >>> class Tree:
    ...     def __init__(self, leaves):
    ...         self.leaves = leaves
    >>> register_dynamic_factory(Tree, lambda:dict(leaves=[]))
    >>> klass1 = create(Tree)
    >>> klass2 = create(Tree)
    >>> klass1.leaves is not klass2.leaves
    True
"""

DEFAULTS = {}

def create(klass, **kwds):
    args = DEFAULTS[klass]()
    args.update(kwds)
    return klass(**args)

def register_factory(klass, **kwds):
    DEFAULTS[klass] = kwds.copy

def register_dynamic_factory(klass, function):
    DEFAULTS[klass] = function

########################################################################
## A few handy factories for Pythoscope.
##
from pythoscope.astbuilder import parse
from pythoscope.store import TestClass, TestMethod

register_dynamic_factory(TestMethod,
  lambda:dict(name="test_method", code=parse("# a test method")))
register_dynamic_factory(TestClass,
  lambda:dict(name="TestClass", code=parse("# a test class")))

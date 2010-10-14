"""An easy way to create domain objects with required parameters, which aren't
always important during testing.

This loosely follows Creation Method pattern (see
<http://xunitpatterns.com/Creation%20Method.html> for details).

First, register a factory for some domain object.
    >>> class Struct:
    ...     def __init__(self, name):
    ...         self.name = name
    >>> register_factory(Struct, name="nice_structure") #doctest: +ELLIPSIS
    <test.factories.Factory object ...>

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
    >>> register_dynamic_factory(Tree, lambda:dict(leaves=[])) #doctest: +ELLIPSIS
    <test.factories.Factory object ...>
    >>> klass1 = create(Tree)
    >>> klass2 = create(Tree)
    >>> klass1.leaves is not klass2.leaves
    True
"""

FACTORIES = {}

def create(klass, **kwds):
    return FACTORIES[klass].invoke(klass, kwds)

def register_factory(klass, **kwds):
    factory = Factory(kwds.copy)
    FACTORIES[klass] = factory
    return factory

def register_dynamic_factory(klass, function):
    factory = Factory(function)
    FACTORIES[klass] = factory
    return factory

class Factory(object):
    def __init__(self, callback):
        self.args_callback = callback
        self.after_callback = None

    def after(self, callback):
        self.after_callback = callback
        return self

    def invoke(self, klass, kwargs):
        args = self.args_callback()
        args.update(kwargs)
        obj = klass(**args)
        if self.after_callback:
            self.after_callback(obj)
        return obj

########################################################################
## A few handy factories for Pythoscope.
##
from pythoscope.astbuilder import parse
from pythoscope.serializer import UnknownObject, ImmutableObject, SequenceObject
from pythoscope.store import Function, FunctionCall, Definition, TestClass,\
    TestMethod, Module, Project

register_factory(Project,
  path="/tmp/")
register_factory(Module,
  project=create(Project), subpath="module")
register_factory(Definition,
  name="definition")
register_factory(Function,
  name="function", module=create(Module))
register_factory(UnknownObject,
  obj=None)
register_factory(ImmutableObject,
  obj=1)
register_factory(SequenceObject,
  obj=[], serialize=lambda x: create(UnknownObject, obj=x))
register_dynamic_factory(FunctionCall,
  lambda:dict(definition=create(Function), args={}, output=create(ImmutableObject))).\
  after(lambda fc: fc.definition.add_call(fc))
register_dynamic_factory(TestMethod,
  lambda:dict(name="test_method", code=parse("# a test method")))
register_dynamic_factory(TestClass,
  lambda:dict(name="TestClass", code=parse("# a test class")))

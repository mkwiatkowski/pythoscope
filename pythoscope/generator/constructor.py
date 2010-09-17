from pythoscope.compat import sorted
from pythoscope.generator.code_string import CodeString, combine, join, \
    putinto, addimport
from pythoscope.serializer import BuiltinException, CompositeObject,\
    ImmutableObject, MapObject, UnknownObject, SequenceObject
from pythoscope.store import Class, Function, UserObject, MethodCall, Method,\
    GeneratorObject


# :: Definition -> (str, str)
def import_for(definition):
    return (definition.module.locator, definition.name)

# :: string -> string
def todo_value(value):
    """Wrap given value in a <TODO: value> block.
    """
    return "<TODO: %s>" % value

# :: [string] -> string
def list_of(strings):
    return "[%s]" % ', '.join(strings)

# :: MapObject -> {str: SerializedObject}
def map_as_kwargs(mapobject):
    # Keys of kwargs argument must be strings - assertion is checked by
    # the interpreter on runtime.
    return sorted([(eval(k.reconstructor), v) for k,v in mapobject.mapping])

# :: SerializedObject | [SerializedObject] -> string
def type_as_string(object):
    """Return a most common representation of the wrapped object type.

    >>> type_as_string([SequenceObject((), None), MapObject({}, None)])
    '[tuple, dict]'
    """
    if isinstance(object, list):
        return list_of(map(type_as_string, object))

    return object.type_name

# :: ([SerializedObject], {SerializedObject: str}) -> [CodeString]
def get_objects_collection_info(objs, assigned_names):
    for obj in objs:
        yield constructor_as_string(obj, assigned_names)

# :: ({SerializedObject: SerializedObject}, {SerializedObject: str}) -> [CodeString]
def get_objects_mapping_info(mapping, assigned_names):
    for key, value in mapping:
        keycs = constructor_as_string(key, assigned_names)
        valuecs = constructor_as_string(value, assigned_names)
        yield combine(keycs, valuecs, "%s: %s")

# :: (CompositeObject, {SerializedObject: str}) -> [CodeString]
def get_contained_objects_info(obj, assigned_names):
    """Return a list of CodeStrings describing each object contained within
    a composite object.
    """
    if isinstance(obj, SequenceObject):
        return list(get_objects_collection_info(obj.contained_objects, assigned_names))
    elif isinstance(obj, MapObject):
        return list(get_objects_mapping_info(obj.mapping, assigned_names))
    elif isinstance(obj, BuiltinException):
        return list(get_objects_collection_info(obj.args, assigned_names))
    else:
        raise TypeError("Wrong argument to get_contained_objects_info: %r." % obj)

# :: Definition -> [str]
def arguments_of(definition):
    if isinstance(definition, Method):
        return definition.args[1:] # Skip "self".
    return definition.args

# :: (string, dict, Definition, {SerializedObject: str}) -> CodeString
def call_as_string_for(object_name, args, definition, assigned_names={}):
    """Generate code for calling an object with given arguments.

    >>> from test.helper import make_fresh_serialize
    >>> serialize = make_fresh_serialize()

    Puts varargs at the end of arguments list.
        >>> call_as_string_for('build_url',
        ...     {'proto': serialize('http'), 'params': serialize(('user', 'session', 'new'))},
        ...     Function('build_url', ['proto', '*params']))
        "build_url('http', 'user', 'session', 'new')"

    Works for lone varargs too.
        >>> call_as_string_for('concat', {'args': serialize(([1,2,3], [4,5], [6]))},
        ...     Function('concat', ['*args']))
        'concat([1, 2, 3], [4, 5], [6])'

    Uses assigned name for varargs as well.
        >>> args = serialize((1, 2, 3))
        >>> call_as_string_for('add', {'args': args}, Function('add', ['*args']), {args: 'atuple'})
        'add(*atuple)'

    Inlines extra keyword arguments in the call...
        >>> call_as_string_for('dict', {'kwargs': serialize({'one': 1, 'two': 2})},
        ...     Function('dict', ['**kwargs']))
        'dict(one=1, two=2)'

    ...even when they are combined with varargs.
        >>> call_as_string_for('wrap', {'a': serialize((1, 2, 3)), 'k': serialize({'x': 4, 'y': 5})},
        ...     Function('wrap', ['*a', '**k']))
        'wrap(1, 2, 3, x=4, y=5)'

    Uses assigned name for kwarg if present.
        >>> kwargs = serialize({'id': 42, 'model': 'user'})
        >>> call_as_string_for('filter_params', {'kwargs': kwargs},
        ...    Function('filter_params', ['**kwargs']), {kwargs: 'params'})
        'filter_params(**params)'

    Generates valid code when vararg has been named and kwarg wasn't.
        >>> args = serialize((1, 2, 3))
        >>> call_as_string_for('wrap', {'args': args, 'kwargs': serialize({'a': 6, 'b': 7})},
        ...     Function('wrap', ['*args', '**kwargs']), {args: 'atuple'})
        'wrap(a=6, b=7, *atuple)'

    When varargs are present all preceding arguments are positioned, not named.
        >>> call_as_string_for('sum', {'x': serialize(1), 'rest': serialize((2, 3))},
        ...     Function('sum', ['x', '*rest']))
        'sum(1, 2, 3)'
    """
    positional_args = []
    keyword_args = []
    vararg = None
    kwarg = None

    def getvalue(argname):
        return args[argname.lstrip("*")]

    skipped_an_arg = False
    for argname in arguments_of(definition):
        try:
            value = getvalue(argname)
            if argname.startswith("**"):
                if value in assigned_names.keys():
                    kwarg = CodeString("**%s" % assigned_names[value])
                else:
                    for karg, kvalue in map_as_kwargs(value):
                        valuecs = constructor_as_string(kvalue, assigned_names)
                        keyword_args.append(combine(karg, valuecs, "%s=%s"))
            elif argname.startswith("*"):
                if value in assigned_names.keys():
                    vararg = CodeString("*%s" % assigned_names[value])
                else:
                    code_strings = get_contained_objects_info(value, assigned_names)
                    positional_args.extend(code_strings)
            else:
                constructor = constructor_as_string(value, assigned_names)
                if skipped_an_arg:
                    keyword_args.append(combine(argname, constructor, "%s=%s"))
                else:
                    positional_args.append(constructor)
        except KeyError:
            skipped_an_arg = True

    arguments = join(', ', filter(None, (positional_args + keyword_args + [vararg] + [kwarg])))
    return combine(object_name, arguments, "%s(%s)")

# :: (string, dict, {SerializedObject: str}) -> CodeString
def call_as_string(object_name, args, assigned_names={}):
    """Generate code for calling an arbitrary object with given arguments.
    Use `call_as_string_for` when you have a definition to base the call on.

    >>> from test.helper import make_fresh_serialize
    >>> serialize = make_fresh_serialize()

    Since we don't have a definition to base the generated call on, we use
    keywords to name all arguments:
        >>> call_as_string('fun', {'a': serialize(1), 'b': serialize(2)})
        'fun(a=1, b=2)'
        >>> call_as_string('capitalize', {'str': serialize('string')})
        "capitalize(str='string')"

    Uses references to existing objects where possible...
        >>> result = call_as_string('call', {'f': serialize(call_as_string)})
        >>> result
        'call(f=call_as_string)'
        >>> result.uncomplete
        False

    ...but marks the resulting call as uncomplete if at least one of objects
    appearing in a call cannot be constructed.
        >>> result = call_as_string('map', {'f': serialize(lambda x: 42), 'L': serialize([1,2,3])})
        >>> result
        'map(L=[1, 2, 3], f=<TODO: function>)'
        >>> result.uncomplete
        True

    Uses names already assigned to objects instead of inlining their
    construction code.
        >>> mutable = serialize([])
        >>> call_as_string('merge', {'seq1': mutable, 'seq2': serialize([1,2,3])},
        ...     {mutable: 'alist'})
        'merge(seq1=alist, seq2=[1, 2, 3])'
    """
    arguments = []
    for arg, value in sorted(args.iteritems()):
        constructor = constructor_as_string(value, assigned_names)
        arguments.append(combine(arg, constructor, template="%s=%s"))
    return combine(object_name, join(", ", arguments), template="%s(%s)")

# :: (SerializedObject | [SerializedObject], {SerializedObject: str}) -> CodeString
def constructor_as_string(object, assigned_names={}):
    """For a given object (either a SerializedObject or a list of them) return
    a string representing a code that will construct it.

    >>> from test.helper import make_fresh_serialize
    >>> serialize = make_fresh_serialize()

    It handles built-in types
        >>> constructor_as_string(serialize(123))
        '123'
        >>> constructor_as_string(serialize('string'))
        "'string'"
        >>> constructor_as_string([serialize(1), serialize('two')])
        "[1, 'two']"

    as well as instances of user-defined classes
        >>> obj = UserObject(None, Class('SomeClass'))
        >>> constructor_as_string(obj)
        'SomeClass()'

    interpreting their arguments correctly
        >>> obj.add_call(MethodCall(Method('__init__', ['self', 'arg']), {'arg': serialize('whatever')}, serialize(None)))
        >>> constructor_as_string(obj)
        "SomeClass('whatever')"

    even if they're user objects themselves:
        >>> otherobj = UserObject(None, Class('SomeOtherClass'))
        >>> otherobj.add_call(MethodCall(Method('__init__', ['self', 'object']), {'object': obj}, serialize(None)))
        >>> constructor_as_string(otherobj)
        "SomeOtherClass(SomeClass('whatever'))"

    or they are already named:
        >>> s = serialize("string")
        >>> anotherobj = UserObject(None, Class('AnotherClass'))
        >>> anotherobj.add_call(MethodCall(Method('__init__', ['self', 's']), {'s': s}, serialize(None)))
        >>> constructor_as_string(anotherobj, {s: 's'})
        'AnotherClass(s)'

    Handles composite objects:
        >>> constructor_as_string(serialize([1, "a", None]))
        "[1, 'a', None]"

    even when they contain instances of user-defined classes:
        >>> constructor_as_string(SequenceObject([obj], lambda x:x))
        "[SomeClass('whatever')]"

    or other composite objects:
        >>> constructor_as_string(serialize((23, [4, [5]], {'a': 'b'})))
        "(23, [4, [5]], {'a': 'b'})"

    or already named objects:
        >>> seq = serialize(["a", None])
        >>> astring = seq.contained_objects[0]
        >>> constructor_as_string(seq, {astring: 'astring'})
        '[astring, None]'

    Empty tuples are recreated properly:
        >>> constructor_as_string(serialize((((42,),),)))
        '(((42,),),)'
    """
    if isinstance(object, list):
        return list_of(map(constructor_as_string, object))
    elif assigned_names.has_key(object):
        return CodeString(assigned_names[object])
    elif isinstance(object, UserObject):
        # Look for __init__ call and base the constructor on that.
        init_call = object.get_init_call()
        if init_call:
            return call_as_string_for(object.klass.name, init_call.input,
                init_call.definition, assigned_names)
        else:
            return call_as_string(object.klass.name, {})
    elif isinstance(object, ImmutableObject):
        return CodeString(object.reconstructor, imports=object.imports)
    elif isinstance(object, CompositeObject):
        arguments = join(', ', get_contained_objects_info(object, assigned_names))
        return putinto(arguments, object.constructor_format, object.imports)
    elif isinstance(object, GeneratorObject):
        if object.is_activated():
            cs = call_as_string_for(object.definition.name, object.args,
                object.definition)
            return addimport(cs, import_for(object.definition))
        else:
            return CodeString(todo_value('generator'), uncomplete=True)
    elif isinstance(object, UnknownObject):
        return CodeString(todo_value(object.partial_reconstructor), uncomplete=True)
    else:
        raise TypeError("constructor_as_string expected SerializedObject at input, not %s" % object)

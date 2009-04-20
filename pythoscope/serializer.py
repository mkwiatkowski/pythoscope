import array
import re
import sets
import types

from pythoscope.util import RePatternType, all, class_name, frozenset, \
    module_name, regexp_flags_as_string, set, string2id, underscore


# :: SerializedObject | [SerializedObject] -> bool
def can_be_constructed(obj):
    if isinstance(obj, list):
        return all(map(can_be_constructed, obj))
    elif isinstance(obj, SequenceObject):
        return all(map(can_be_constructed, obj.contained_objects))
    return not isinstance(obj, UnknownObject)

# :: object -> string
def get_human_readable_id(obj):
    # Get human readable id based on object's value,
    if obj is True:
        return 'true'
    elif obj is False:
        return 'false'

    # ... based on object's type,
    objtype = type(obj)
    mapping = {list: 'list',
               dict: 'dict',
               tuple: 'tuple',
               unicode: 'unicode_string',
               types.GeneratorType: 'generator'}
    objid = mapping.get(objtype)
    if objid:
        return objid

    # ... or based on its supertype.
    if isinstance(obj, Exception):
        return underscore(objtype.__name__)
    elif isinstance(obj, RePatternType):
        return "%s_pattern" % string2id(obj.pattern)
    elif isinstance(obj, types.FunctionType):
        if obj.func_name == '<lambda>':
            return "function"
        return "%s_function" % obj.func_name
    else:
        # str() may raise an exception.
        try:
            string = str(obj)
        except:
            string = "<>"
        # Looks like an instance without a custom __str__ defined.
        if string.startswith("<"):
            return "%s_instance" % underscore(objtype.__name__)
        else:
            return string2id(string)

# :: object -> string
def get_type_name(obj):
    """
    >>> get_type_name([])
    'list'
    >>> get_type_name({})
    'dict'

    May contain dots, if type is not builtin.
        >>> get_type_name(lambda: None)
        'types.FunctionType'
    """
    mapping = {array.array: 'array.array',
               types.FunctionType: 'types.FunctionType',
               types.GeneratorType: 'types.GeneratorType'}
    objtype = type(obj)
    return mapping.get(objtype, class_name(obj))

class SerializedObject(object):
    """An object captured during execution.

    This is an abstract class, see subclasses for descriptions of different
    types of serialized objects.

    :IVariables:
      timestamp : float
        Number marking creation time of this SerializedObject. This number
        cannot be converted to a meaningful time description. It should only
        be used to arrange objects' creation on a timeline.
      human_readable_id : str
        A human-readable description of an object, suitable to be used as
        an identifier.
      module_name : str
        Location of the module this object's class was defined in. Should be
        usable in import statements.
      type_import : tuple(str, str) or None
        An import needed for the type to be available in the testing
        environment. None if no import is needed.
      type_name : str
        A canonical representation of the type this object is an instance of.
    """
    _last_timestamp = 0

    def __init__(self, obj):
        self.timestamp = SerializedObject.next_timestamp()
        self.human_readable_id = get_human_readable_id(obj)

    def _get_type_import(self):
        if self.module_name not in ['__builtin__', 'exceptions']:
            return (self.module_name, self.type_name)
    type_import = property(_get_type_import)

    def next_timestamp(cls):
        cls._last_timestamp += 1
        return cls._last_timestamp
    next_timestamp = classmethod(next_timestamp)

class ImmutableObject(SerializedObject):
    """A serialized object which identity doesn't matter.

    Immutable objects (like strings or integers) and objects with well-defined
    location (like non-anonymous functions) are all considered ImmutableObjects.

    ImmutableObjects are certain to have a reconstructor.

    :IVariables:
      reconstructor : str
        A string representing code that will construct the object.
      imports : set
        A set of import descriptions needed for the reconstructor code to work.
    """
    def __init__(self, obj):
        SerializedObject.__init__(self, obj)

        self.reconstructor, self.imports = ImmutableObject.get_reconstructor_with_imports(obj)

    def __eq__(self, other):
        return isinstance(other, ImmutableObject) and \
            self.reconstructor == other.reconstructor and \
            self.imports == other.imports

    def __hash__(self):
        return hash(self.reconstructor)

    def __repr__(self):
        return "ImmutableObject(%r, imports=%r)" % (self.reconstructor, self.imports)

    # :: object -> (string, set)
    def get_reconstructor_with_imports(obj):
        """
        >>> ImmutableObject.get_reconstructor_with_imports(re.compile('abcd'))
        ("re.compile('abcd')", set(['re']))
        >>> ImmutableObject.get_reconstructor_with_imports(re.compile('abcd', re.I | re.M))
        ("re.compile('abcd', re.IGNORECASE | re.MULTILINE)", set(['re']))
        """
        if isinstance(obj, (int, long, float, str, unicode, types.NoneType)):
            # Bultin types has very convienient representation.
            return repr(obj), set()
        elif isinstance(obj, RePatternType):
            flags = regexp_flags_as_string(obj.flags)
            if flags:
                return ('re.compile(%r, %s)' % (obj.pattern, flags), set(['re']))
            else:
                return ('re.compile(%r)' % obj.pattern, set(['re']))
        elif isinstance(obj, types.FunctionType):
            function = obj.func_name
            module = obj.__module__
            return (function, set([(module, function)]))
        else:
            raise TypeError("Unknown type of an ImmutableObject: %r." % obj)
    get_reconstructor_with_imports = staticmethod(get_reconstructor_with_imports)

class UnknownObject(SerializedObject):
    """A user object or a builtin value that we cannot recreate.

    :IVariables:
      partial_reconstructor : str
        A string representation of a partial object reconstructor. It doesn't
        have to be parsable, as it will be part of a comment. Partial
        reconstructor should give all possible hints about an object to help
        the user complete the code.
    """
    def __init__(self, obj):
        SerializedObject.__init__(self, obj)

        self.module_name = module_name(obj)
        self.type_name = get_type_name(obj)
        self.partial_reconstructor = UnknownObject.get_partial_reconstructor(obj)

    def __repr__(self):
        return "UnknownObject(%r)" % self.partial_reconstructor

    # :: object -> string
    def get_partial_reconstructor(obj):
        mapping = {types.FunctionType: 'function',
                   types.GeneratorType: 'generator'}
        objtype = type(obj)
        default = "%s.%s" % (objtype.__module__, objtype.__name__)
        return mapping.get(objtype, default)
    get_partial_reconstructor = staticmethod(get_partial_reconstructor)

class CompositeObject(SerializedObject):
    """An object of a builtin type that may contain other objects, e.g. a list
    or a dictionary.
    """
    def __init__(self, obj):
        SerializedObject.__init__(self, obj)

        self.module_name = module_name(obj)
        self.type_name = get_type_name(obj)

class SequenceObject(CompositeObject):
    """A builtin object that contains an ordered sequence of other objects
    inside it.

    Tuples and other immutable builtin types are still serialized into
    a SequenceObject, because they may contain a mutable element inside them.
    """
    type_formats_with_imports = {
        list: ("[%s]", set()),
        frozenset: ("frozenset([%s])", set()),
        set: ("set([%s])", set()),
        sets.ImmutableSet: ("ImmutableSet([%s])", set([("sets", "ImmutableSet")])),
        sets.Set: ("Set([%s])", set([("sets", "Set")])),
        tuple: ("(%s)", set()),
    }

    def __init__(self, obj, serialize):
        CompositeObject.__init__(self, obj)

        self.contained_objects = map(serialize, obj)

        # Arrays constructor needs to include a typecode.
        if isinstance(obj, array.array):
            self.constructor_format = "array.array('%s', [%%s])" % obj.typecode
            self.imports = set(["array"])
        # Special case for tuples with a single element.
        elif isinstance(obj, tuple) and len(obj) == 1:
            self.constructor_format = "(%s,)"
            self.imports = set()
        else:
            self.constructor_format = self.type_formats_with_imports[type(obj)][0]
            self.imports = self.type_formats_with_imports[type(obj)][1]

class MapObject(CompositeObject):
    """A mutable object that contains unordered mapping of key/value pairs.
    """
    def __init__(self, obj, serialize):
        CompositeObject.__init__(self, obj)

        self.mapping = [(serialize(k), serialize(v)) for k,v in obj.items()]
        self.constructor_format = "{%s}"
        self.imports = set()

def is_immutable(obj):
    # Bool class is a subclass of int, so True and False are included in this
    # condition.
    if isinstance(obj, (float, int, long, str, unicode, types.NoneType, RePatternType)):
        return True
    elif isinstance(obj, types.FunctionType) and obj.func_name != '<lambda>':
        return True
    return False

def is_mapping(obj):
    return isinstance(obj, dict)

def is_sequence(obj):
    return isinstance(obj, (array.array, list, frozenset, set,
                            sets.ImmutableSet, sets.Set, tuple))

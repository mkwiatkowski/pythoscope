import array
import exceptions
import re
import types

from pythoscope.compat import frozenset, set, sets
from pythoscope.event import Event
from pythoscope.util import RePatternType, class_name, class_of, \
    module_name, regexp_flags_as_string, string2id, underscore

# Filter out private attributes, like __doc__, __name__ and __package__.
BUILTIN_EXCEPTION_TYPES = set([v for k,v in exceptions.__dict__.items() if not k.startswith('_')])

# Exceptions with special semantics for the `args` attribute.
# See <http://docs.python.org/library/exceptions.html#exceptions.EnvironmentError>
# for details.
BUILTIN_ENVIRONMENT_ERROR_TYPES = [EnvironmentError, OSError, IOError]

# Include VMSError or WindowsError if they exist.
try:
    BUILTIN_ENVIRONMENT_ERROR_TYPES.append(WindowsError)
except NameError:
    try:
        BUILTIN_ENVIRONMENT_ERROR_TYPES.append(VMSError)
    except NameError:
        pass

# :: object -> string
def get_human_readable_id(obj):
    # Get human readable id based on object's value,
    if obj is True:
        return 'true'
    elif obj is False:
        return 'false'

    # ... based on object's type,
    objclass = class_of(obj)
    mapping = {list: 'list',
               dict: 'dict',
               tuple: 'tuple',
               unicode: 'unicode_string',
               types.GeneratorType: 'generator'}
    objid = mapping.get(objclass)
    if objid:
        return objid

    # ... or based on its supertype.
    if isinstance(obj, Exception):
        return underscore(objclass.__name__)
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
            return "%s_instance" % underscore(objclass.__name__)
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

class SerializedObject(Event):
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
    def __init__(self, obj):
        super(SerializedObject, self).__init__()
        self.human_readable_id = get_human_readable_id(obj)
        self.module_name = module_name(obj)
        self.type_name = get_type_name(obj)

    def _get_type_import(self):
        if self.module_name not in ['__builtin__', 'exceptions']:
            return (self.module_name, self.type_name)
    type_import = property(_get_type_import)

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
        if self.imports:
            return "ImmutableObject(%r, imports=%r)" % (self.reconstructor, self.imports)
        return "ImmutableObject(%r)" % self.reconstructor

    # :: object -> (string, set)
    def get_reconstructor_with_imports(obj):
        """
        >>> reconstructor, imports = ImmutableObject.get_reconstructor_with_imports(re.compile('abcd'))
        >>> reconstructor
        "re.compile('abcd')"
        >>> imports == set(['re'])
        True
        >>> reconstructor, imports = ImmutableObject.get_reconstructor_with_imports(re.compile('abcd', re.I | re.M))
        >>> reconstructor
        "re.compile('abcd', re.IGNORECASE | re.MULTILINE)"
        >>> imports == set(['re'])
        True
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
        self.partial_reconstructor = get_partial_reconstructor(obj)

    def __repr__(self):
        return "UnknownObject(%r)" % self.partial_reconstructor

# :: object -> string
def get_partial_reconstructor(obj):
    mapping = {types.FunctionType: 'function',
               types.GeneratorType: 'generator'}
    objtype = class_of(obj)
    default = "%s.%s" % (objtype.__module__, objtype.__name__)
    return mapping.get(objtype, default)

class LibraryObject(SerializedObject):
    type_formats_with_imports = {
        ('xml.dom.minidom', 'Element'):
            ("Element(%s)",
             ["tagName", "namespaceURI", "prefix"],
             set([("xml.dom.minidom", "Element")])),
        ('datetime', 'datetime'):
            ("datetime.datetime(%s)",
             ["year", "month", "day", "hour", "minute", "second", "microsecond", "tzinfo"],
             set(["datetime"])),
    }

    def __init__(self, obj, serialize):
        con, argnames, imp = self.type_formats_with_imports[id_of_class_of(obj)]

        self.constructor_format = con
        self.arguments = map(serialize, [getattr(obj, a, None) for a in argnames])
        self.imports = imp

        # Arguments were serialized first, before a call to super, so that they
        # get a lower timestamp than the whole object.
        SerializedObject.__init__(self, obj)

class CompositeObject(SerializedObject):
    """An object of a builtin type that may contain other objects, e.g. a list
    or a dictionary.

    :IVariables:
      constructor_format : str
        A format string that will reconstruct this CompositeObject. Should
        contain a single %s, which will be replaced with string representation
        of contained objects, separated with commas.
        E.g. "[%s]" is a good constructor_format for a list.
      imports : set
        Set of imports needed to bring this CompositeObject into current scope.
    """
    pass

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
        # Serialize the parts first and only after that call super, so that
        # the parts get a lower timestamp than the whole object.
        self.contained_objects = map(serialize, obj)

        CompositeObject.__init__(self, obj)

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

    def __repr__(self):
        return "SequenceObject(%s)" % (self.constructor_format % self.contained_objects)

class MapObject(CompositeObject):
    """A mutable object that contains unordered mapping of key/value pairs.
    """
    def __init__(self, obj, serialize):
        # Serialize the parts first and only after that call super, so that
        # the parts get a lower timestamp than the whole object.
        self.mapping = [(serialize(k), serialize(v)) for k,v in obj.items()]

        CompositeObject.__init__(self, obj)

        self.constructor_format = "{%s}"
        self.imports = set()

class BuiltinException(CompositeObject):
    """A built-in exception instance, which may hold any kind of objects in its
    `args` attribute.

    It doesn't matter if an exception was generated by the interpreter or by
    the user code, it will be serialized as BuiltinException nevertheless. This
    means we can't assume anything about the contents of `args`.

    User-defined exceptions, both deriving from BaseException and those not,
    are serialized as UserObjects.
    """
    def __init__(self, obj, serialize):
        CompositeObject.__init__(self, obj)

        self.args = map(serialize, obj.args)
        self.constructor_format = "%s(%%s)" % class_name(obj)
        self.imports = set()

        if class_of(obj) in BUILTIN_ENVIRONMENT_ERROR_TYPES and obj.filename is not None:
            self.args.append(serialize(obj.filename))

def is_immutable(obj):
    # Bool class is a subclass of int, so True and False are included in this
    # condition.
    if isinstance(obj, (float, int, long, str, unicode, types.NoneType, RePatternType)):
        return True
    elif isinstance(obj, types.FunctionType) and obj.func_name != '<lambda>':
        return True
    return False

def id_of_class_of(obj):
    klass = class_of(obj)
    return (klass.__module__, klass.__name__)

def is_library_object(obj):
    return id_of_class_of(obj) in LibraryObject.type_formats_with_imports.keys()

def is_mapping(obj):
    return type(obj) in [dict]

def is_sequence(obj):
    return type(obj) in [array.array, list, frozenset, set,
                         sets.ImmutableSet, sets.Set, tuple]

def is_builtin_exception(obj):
    """Return True if given object is an instance of a built-in exception, like
    NameError or EOFError. Return False for instances of user-defined
    exceptions.
    """
    return class_of(obj) in BUILTIN_EXCEPTION_TYPES

def is_serialized_string(obj):
    return isinstance(obj, ImmutableObject) and obj.type_name == 'str'

import array
import re
import sets
import types

from pythoscope.astvisitor import parse_fragment, ParseError
from pythoscope.util import RePatternType, all, frozenset, \
    regexp_flags_as_string, set, underscore


# :: SerializedObject | [SerializedObject] -> bool
def can_be_constructed(obj):
    if isinstance(obj, list):
        return all(map(can_be_constructed, obj))
    return obj.reconstructor_with_imports is not None

# :: string -> string
def string2id(string):
    """Remove from string all characters that cannot be used in an identifier.
    """
    return re.sub(r'[^a-zA-Z0-9_]', '', re.sub(r'\s+', '_', string.strip()))

# :: object -> string
def get_type_name(obj):
    """A canonical representation of the type.

    >>> get_type_name([])
    'list'
    >>> get_type_name({})
    'dict'

    May contain dots, if type is not builtin.
        >>> get_type_name(lambda: None)
        'types.FunctionType'
    """
    mapping = {types.FunctionType: 'types.FunctionType',
               types.GeneratorType: 'types.GeneratorType'}
    objtype = type(obj)
    return mapping.get(objtype, objtype.__name__)

# :: object -> string
def get_module_name(obj):
    return type(obj).__module__

# :: object -> string
def get_partial_reconstructor(obj):
    """A string representation of a partial object reconstructor.

    It doesn't have to be parsable, as it will be part of a comment. Partial
    reconstructor should give all possible hints about an object to help
    the user correct the code.
    """
    mapping = {types.FunctionType: 'function',
               types.GeneratorType: 'generator'}
    objtype = type(obj)
    default = "%s.%s" % (objtype.__module__, objtype.__name__)
    return mapping.get(objtype, default)

# :: object -> string
def get_human_readable_id(obj):
    """A human-readable description of an object, suitable to be used as
    an identifier.
    """
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
        string = str(obj)
        # Looks like an instance without a custom __str__ defined.
        if string.startswith("<"):
            return "%s_instance" % underscore(objtype.__name__)
        else:
            return string2id(string)

# :: string -> bool
def is_parsable(string):
    try:
        parse_fragment(string)
        return True
    except ParseError:
        return False

# :: object -> (string, set) | None
def get_reconstructor_with_imports(obj):
    """A string representing code that will construct the object plus
    a set of import descriptions needed for that code to work.

    Returns None when given object cannot be reconstructed.

    >>> get_reconstructor_with_imports(array.array('I', [1, 2, 3, 4]))
    ("array.array('I', [1L, 2L, 3L, 4L])", ['array'])
    >>> get_reconstructor_with_imports(array.array('d', [1, 2, 3, 4]))
    ("array.array('d', [1.0, 2.0, 3.0, 4.0])", ['array'])

    >>> get_reconstructor_with_imports(re.compile('abcd'))
    ("re.compile('abcd')", ['re'])
    >>> get_reconstructor_with_imports(re.compile('abcd', re.I | re.M))
    ("re.compile('abcd', re.IGNORECASE | re.MULTILINE)", ['re'])
    """
    if isinstance(obj, RePatternType):
        flags = regexp_flags_as_string(obj.flags)
        if flags:
            return ('re.compile(%r, %s)' % (obj.pattern, flags), ['re'])
        else:
            return ('re.compile(%r)' % obj.pattern, ['re'])
    elif isinstance(obj, types.FunctionType):
        function = obj.func_name
        if function != '<lambda>':
            module = obj.__module__
            return (function, [(module, function)])
    elif isinstance(obj, (int, long, float, str, unicode, types.NoneType)):
        # Bultin types has very convienient representation.
        return repr(obj), []
    elif isinstance(obj, array.array):
        return "array." + repr(obj), ["array"]
    elif isinstance(obj, (dict, frozenset, list, set, sets.ImmutableSet, sets.Set, tuple)):
        imports = set()
        if isinstance(obj, sets.ImmutableSet):
            imports.add(("sets", "ImmutableSet"))
        elif isinstance(obj, sets.Set):
            imports.add(("sets", "Set"))
        # Be careful not to generate wrong code.
        # TODO: Current solution is a hack. Right way to do this is to make
        # composite types call get_reconstructor_with_imports on all of their
        # elements recursively.
        if is_parsable(repr(obj)):
            return repr(obj), imports

class SerializedObject(object):
    __slots__ = ("human_readable_id", "module_name", "partial_reconstructor",
                 "reconstructor_with_imports", "type_import", "type_name")

    def __init__(self, obj):
        self.human_readable_id = get_human_readable_id(obj)
        self.module_name = get_module_name(obj)
        self.partial_reconstructor = get_partial_reconstructor(obj)
        self.reconstructor_with_imports = get_reconstructor_with_imports(obj)
        self.type_name = get_type_name(obj)

        # An import needed for the type to be available in the testing
        # environment.
        self.type_import = (self.module_name, self.type_name)

    def __eq__(self, other):
        if not isinstance(other, SerializedObject):
            return False
        for attr in SerializedObject.__slots__:
            if getattr(self, attr) != getattr(other, attr):
                return False
        return True

    def __hash__(self):
        return hash(self.partial_reconstructor)

    def __repr__(self):
        if self.reconstructor_with_imports is not None:
            return "SerializedObject(%r)" % self.reconstructor_with_imports[0]
        else:
            return "SerializedObject(%r)" % self.partial_reconstructor

def serialize(obj):
    return SerializedObject(obj)

def serialize_call_arguments(input):
    new_input = {}
    for key, value in input.iteritems():
        new_input[key] = serialize(value)
    return new_input

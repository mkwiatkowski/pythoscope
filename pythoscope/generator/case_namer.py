from pythoscope.generator.selector import testable_calls
from pythoscope.serializer import SerializedObject, ImmutableObject,\
    UnknownObject
from pythoscope.store import Function, GeneratorObject
from pythoscope.util import assert_argument_type, counted, key_for_value,\
    underscore


# :: SerializedObject -> string
def object2id(obj):
    """Convert object to string that can be used as an identifier.

    Generator objects that were never activated get a generic name...
        >>> def producer():
        ...     yield 1
        >>> gobject = GeneratorObject(producer())
        >>> object2id(gobject)
        'generator'

    ...but if we have a matching definition, the name is based on it.
        >>> definition = Function('producer', is_generator=True)
        >>> gobject.activate(definition, {}, definition)
        >>> object2id(gobject)
        'producer_instance'

    Accepts only SerializedObjects as arguments.
        >>> object2id(42)
        Traceback (most recent call last):
          ...
        TypeError: object2id() should be called with a SerializedObject argument, not 42
    """
    assert_argument_type(obj, SerializedObject)
    if isinstance(obj, GeneratorObject) and obj.is_activated():
        return "%s_instance" % obj.definition.name
    else:
        return obj.human_readable_id

def objects_list_to_id(objects):
    """Convert given list of objects into string that can be used as an
    identifier.
    """
    if not objects:
        return 'nothing'
    return '_then_'.join(map(object2id, objects))

def arguments_as_string(args, always_use_argnames=False):
    """Generate an underscored description of given arguments.

    >>> arguments_as_string({})
    ''
    >>> arguments_as_string({'x': ImmutableObject(7), 'y': ImmutableObject(13)})
    'x_equal_7_and_y_equal_13'

    Usually doesn't use argument names when there's only a single argument:
        >>> arguments_as_string({'x': ImmutableObject(1)})
        '1'

    but will use them if forced to:
        >>> arguments_as_string({'x': ImmutableObject(1)}, always_use_argnames=True)
        'x_equal_1'
    """
    if not always_use_argnames and len(args) == 1:
        return object2id(args.values()[0])
    return "_and_".join(["%s_equal_%s" % (arg, object2id(value))
                         for arg, value in sorted(args.iteritems())])

def objcall2testname(object_name, args, output):
    """Generate a test method name that describes given object call.

    >>> from test.helper import make_fresh_serialize
    >>> serialize = make_fresh_serialize()

    >>> objcall2testname('do_this', {}, serialize(True))
    'test_do_this_returns_true'
    >>> objcall2testname('compute', {}, serialize('whatever you say'))
    'test_compute_returns_whatever_you_say'
    >>> objcall2testname('square', {'x': serialize(7)}, serialize(49))
    'test_square_returns_49_for_7'
    >>> objcall2testname('capitalize', {'str': serialize('a word.')}, serialize('A word.'))
    'test_capitalize_returns_A_word_for_a_word'

    Two or more arguments are mentioned by name.
        >>> objcall2testname('ackermann', {'m': serialize(3), 'n': serialize(2)}, serialize(29))
        'test_ackermann_returns_29_for_m_equal_3_and_n_equal_2'

    Will sort arguments alphabetically.
        >>> objcall2testname('concat', {'s1': serialize('Hello '), 's2': serialize('world!')}, serialize('Hello world!'))
        'test_concat_returns_Hello_world_for_s1_equal_Hello_and_s2_equal_world'

    Always starts and ends a word with a letter or number.
        >>> objcall2testname('strip', {'n': serialize(1), 's': serialize('  A bit of whitespace  ')}, serialize(' A bit of whitespace '))
        'test_strip_returns_A_bit_of_whitespace_for_n_equal_1_and_s_equal_A_bit_of_whitespace'

    Uses argument name when argument is used as a return value.
        >>> alist = serialize([])
        >>> objcall2testname('identity', {'x': alist}, alist)
        'test_identity_returns_x_for_x_equal_list'
    """
    if args:
        # If return value is present in arguments list, use its name as an
        # identifier.
        output_name = key_for_value(args, output)
        if output_name:
            call_description = "%s_for_%s" % (output_name, arguments_as_string(args, always_use_argnames=True))
        else:
            call_description = "%s_for_%s" % (object2id(output), arguments_as_string(args))
    else:
        call_description = object2id(output)

    return "test_%s_returns_%s" % (underscore(object_name), call_description)

def exccall2testname(object_name, args, exception):
    """Generate a test method name that describes given object call raising
    an exception.

    >>> exccall2testname('do_this', {}, UnknownObject(Exception()))
    'test_do_this_raises_exception'
    >>> exccall2testname('square', {'x': ImmutableObject('a string')}, UnknownObject(TypeError()))
    'test_square_raises_type_error_for_a_string'
    """
    if args:
        call_description = "%s_for_%s" % (object2id(exception), arguments_as_string(args))
    else:
        call_description = object2id(exception)
    return "test_%s_raises_%s" % (underscore(object_name), call_description)

def gencall2testname(object_name, args, yields):
    """Generate a test method name that describes given generator object call
    yielding some values.

    >>> gencall2testname('generate', {}, [])
    'test_generate_yields_nothing'
    >>> gencall2testname('generate', {}, [ImmutableObject(1), ImmutableObject(2), ImmutableObject(3)])
    'test_generate_yields_1_then_2_then_3'
    >>> gencall2testname('backwards', {'x': ImmutableObject(321)}, [ImmutableObject('one'), ImmutableObject('two'), ImmutableObject('three')])
    'test_backwards_yields_one_then_two_then_three_for_321'
    """
    if args:
        call_description = "%s_for_%s" % (objects_list_to_id(yields), arguments_as_string(args))
    else:
        call_description = objects_list_to_id(yields)
    return "test_%s_yields_%s" % (underscore(object_name), call_description)

# :: (Call|GeneratorObject, str) -> str
def call2testname(call, object_name):
    # Generators can be treated as calls, which take arguments during
    # initialization and return a list of yielded values.
    if isinstance(call, GeneratorObject):
        exception = generator_object_exception(call)
        if exception:
            return exccall2testname(object_name, call.args, exception)
        else:
            return gencall2testname(object_name, call.args, generator_object_yields(call))
    elif call.raised_exception():
        return exccall2testname(object_name, call.input, call.exception)
    else:
        return objcall2testname(object_name, call.input, call.output)

# :: GeneratorObject -> SerializedObject | None
def generator_object_exception(gobject):
    assert_argument_type(gobject, GeneratorObject)
    for call in gobject.calls:
        if call.raised_exception():
            return call.exception

# :: GeneratorObject -> [SerializedObject]
def generator_object_yields(gobject):
    assert_argument_type(gobject, GeneratorObject)
    return [c.output for c in gobject.calls]

# :: str -> str
def name2testname(name):
    if name[0].isupper():
        return "Test%s" % name
    return "test_%s" % name

# :: MethodCall -> str
def initcall2testname(call):
    name = "test_creation"
    if call.input:
        name += "_with_%s" % arguments_as_string(call.input)
    if call.raised_exception():
        name += "_raises_%s" % object2id(call.exception)
    return name

# :: UserObject -> str
def userobject2testname(user_object):
    init_call = user_object.get_init_call()
    external_calls = testable_calls(user_object.get_external_calls())

    if len(external_calls) == 0 and init_call:
        test_name = initcall2testname(init_call)
    else:
        if len(external_calls) == 1:
            call = external_calls[0]
            test_name = call2testname(call, call.definition.name)
        # Methods with more than one external call use more brief
        # descriptions that don't include inputs and outputs.
        else:
            methods = []
            for method, calls_count in counted([call.definition.name for call in external_calls]):
                if calls_count == 1:
                    methods.append(method)
                else:
                    methods.append("%s_%d_times" % (method, calls_count))
            test_name = "test_%s" % '_and_'.join(methods)
        if init_call and init_call.input:
            test_name += "_after_creation_with_%s" % arguments_as_string(init_call.input)
    return test_name

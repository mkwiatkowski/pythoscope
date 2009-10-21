from pythoscope.astvisitor import descend, ASTVisitor
from pythoscope.astbuilder import parse_fragment, EmptyCode
from pythoscope.logger import log
from pythoscope.generator.adder import add_test_case_to_project
from pythoscope.serializer import BuiltinException, CompositeObject, \
    ImmutableObject, MapObject, UnknownObject, SequenceObject, \
    SerializedObject, can_be_constructed, is_serialized_string
from pythoscope.store import Class, Function, FunctionCall, TestClass, \
    TestMethod, ModuleNotFound, UserObject, MethodCall, Method, Project, \
    GeneratorObject
from pythoscope.compat import any, set, sorted
from pythoscope.util import camelize, compact, counted, flatten, \
    key_for_value, pluralize, underscore, union


# :: [string] -> string
def list_of(strings):
    return "[%s]" % ', '.join(strings)

# :: SerializedObject | [SerializedObject] -> string
def type_as_string(object):
    """Return a most common representation of the wrapped object type.

    >>> type_as_string([SequenceObject((), None), MapObject({}, None)])
    '[tuple, dict]'
    """
    if isinstance(object, list):
        return list_of(map(type_as_string, object))

    return object.type_name

# :: string -> string
def todo_value(value):
    """Wrap given value in a <TODO: value> block.
    """
    return "<TODO: %s>" % value

class CallString(str):
    """A string that holds information on the function/method call it
    represents.

    `uncomplete` attribute denotes whether it is a complete call
    or just a template.

    `imports` is a list of imports that this call requires.
    """
    def __new__(cls, string, uncomplete=False, imports=None):
        if imports is None:
            imports = set()
        call_string = str.__new__(cls, string)
        call_string.uncomplete = uncomplete
        call_string.imports = imports
        return call_string

    def extend(self, value, uncomplete=False, imports=set()):
        return CallString(value, self.uncomplete or uncomplete,
                          self.imports.union(imports))

# :: (SerializedObject | [SerializedObject], {SerializedObject: str}) -> CallString
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
        >>> obj.add_call(MethodCall(Method('__init__'), {'arg': serialize('whatever')}, serialize(None)))
        >>> constructor_as_string(obj)
        "SomeClass(arg='whatever')"

    even if they're user objects themselves:
        >>> otherobj = UserObject(None, Class('SomeOtherClass'))
        >>> otherobj.add_call(MethodCall(Method('__init__'), {'object': obj}, serialize(None)))
        >>> constructor_as_string(otherobj)
        "SomeOtherClass(object=SomeClass(arg='whatever'))"

    Handles composite objects:
        >>> constructor_as_string(serialize([1, "a", None]))
        "[1, 'a', None]"

    even when they contain instances of user-defined classes:
        >>> constructor_as_string(SequenceObject([obj], lambda x:x))
        "[SomeClass(arg='whatever')]"

    or other composite objects:
        >>> constructor_as_string(serialize((23, [4, [5]], {'a': 'b'})))
        "(23, [4, [5]], {'a': 'b'})"

    Empty tuples are recreated properly:
        >>> constructor_as_string(serialize((((42,),),)))
        '(((42,),),)'
    """
    if isinstance(object, list):
        return list_of(map(constructor_as_string, object))
    elif assigned_names.has_key(object):
        return CallString(assigned_names[object])
    elif isinstance(object, UserObject):
        args = {}
        # Look for __init__ call and base the constructor on that.
        init_call = object.get_init_call()
        if init_call:
            args = init_call.input
        return call_as_string(object.klass.name, args,
                              init_call and init_call.definition)
    elif isinstance(object, ImmutableObject):
        return CallString(object.reconstructor, imports=object.imports)
    elif isinstance(object, CompositeObject):
        try:
            reconstructors, imports, uncomplete = zip(*get_contained_objects_info(object, assigned_names))
        # In Python <= 2.3 zip can raise TypeError if no arguments were provided.
        # All Pythons can raise ValueError because of the wrong unpacking.
        except (ValueError, TypeError):
            reconstructors, imports, uncomplete = [], [], []
        return CallString(object.constructor_format % ', '.join(reconstructors),
                          imports=union(object.imports, *imports),
                          uncomplete=any(uncomplete))
    elif isinstance(object, UnknownObject):
        return CallString(todo_value(object.partial_reconstructor), uncomplete=True)
    else:
        raise TypeError("constructor_as_string expected SerializedObject at input, not %s" % object)

# :: ([SerializedObject], {SerializedObject: str}) -> [(str, set, bool)]
def get_objects_collection_info(objs, assigned_names):
    for obj in objs:
        cs = constructor_as_string(obj, assigned_names)
        yield (cs, cs.imports, cs.uncomplete)

# :: ({SerializedObject: SerializedObject}, {SerializedObject: str}) -> [(str, set, bool)]
def get_objects_mapping_info(mapping, assigned_names):
    for key, value in mapping:
        keycs = constructor_as_string(key, assigned_names)
        valuecs = constructor_as_string(value, assigned_names)
        yield ("%s: %s" % (keycs, valuecs),
               union(keycs.imports, valuecs.imports),
               keycs.uncomplete or valuecs.uncomplete)

# :: (CompositeObject, {SerializedObject: str}) -> [(str, set, bool)]
def get_contained_objects_info(obj, assigned_names):
    """Return a list of tuples (reconstructor, imports, uncomplete) describing
    each object contained within a composite object.
    """
    if isinstance(obj, SequenceObject):
        return get_objects_collection_info(obj.contained_objects, assigned_names)
    elif isinstance(obj, MapObject):
        return get_objects_mapping_info(obj.mapping, assigned_names)
    elif isinstance(obj, BuiltinException):
        return get_objects_collection_info(obj.args, assigned_names)
    else:
        raise TypeError("Wrong argument to get_contained_objects_info: %r." % obj)

# :: (string, dict, Definition, {SerializedObject: str}) -> CallString
def call_as_string(object_name, args, definition=None, assigned_names={}):
    """Generate code for calling an object with given arguments.

    >>> from test.helper import make_fresh_serialize
    >>> serialize = make_fresh_serialize()

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
        ...     None, {mutable: 'alist'})
        'merge(seq1=alist, seq2=[1, 2, 3])'

    Puts varargs at the end of arguments list.
        >>> call_as_string('build_url',
        ...     {'proto': serialize('http'), 'params': serialize(('user', 'session', 'new'))},
        ...     Function('build_url', ['proto', '*params']))
        "build_url(proto='http', 'user', 'session', 'new')"

    Works for lone varargs too.
        >>> call_as_string('concat', {'args': serialize(([1,2,3], [4,5], [6]))},
        ...     Function('concat', ['*args']))
        'concat([1, 2, 3], [4, 5], [6])'

    Uses assigned name for varargs as well.
        >>> args = serialize((1, 2, 3))
        >>> call_as_string('add', {'args': args}, Function('add', ['*args']), {args: 'atuple'})
        'add(*atuple)'

    Inlines extra keyword arguments in the call...
        >>> call_as_string('dict', {'kwargs': serialize({'one': 1, 'two': 2})},
        ...     Function('dict', ['**kwargs']))
        'dict(one=1, two=2)'

    ...even when they are combined with varargs.
        >>> call_as_string('wrap', {'a': serialize((1, 2, 3)), 'k': serialize({'x': 4, 'y': 5})},
        ...     Function('wrap', ['*a', '**k']))
        'wrap(1, 2, 3, x=4, y=5)'

    Uses assigned name for kwarg if present.
        >>> kwargs = serialize({'id': 42, 'model': 'user'})
        >>> call_as_string('filter_params', {'kwargs': kwargs},
        ...    Function('filter_params', ['**kwargs']), {kwargs: 'params'})
        'filter_params(**params)'
    """
    arguments = []
    varargs = []
    kwargs = []
    uncomplete = False
    imports = set()
    for arg, value in sorted(args.iteritems()):
        if definition and definition.is_vararg(arg):
            if value in assigned_names.keys():
                varargs = ["*%s" % assigned_names[value]]
            else:
                rec, imp, unc = zip(*get_contained_objects_info(value, assigned_names))
                uncomplete = uncomplete or any(unc)
                imports.update(union(*imp))
                varargs = list(rec)
        elif definition and definition.is_kwarg(arg):
            if value in assigned_names.keys():
                kwargs = ["**%s" % assigned_names[value]]
            else:
                for karg, kvalue in map_as_kwargs(value):
                    valuecs = constructor_as_string(kvalue, assigned_names)
                    uncomplete = uncomplete or valuecs.uncomplete
                    imports.update(valuecs.imports)
                    kwargs.append("%s=%s" % (karg, valuecs))
        else:
            constructor = constructor_as_string(value, assigned_names)
            uncomplete = uncomplete or constructor.uncomplete
            imports.update(constructor.imports)
            arguments.append("%s=%s" % (arg, constructor))
    return CallString("%s(%s)" % (object_name, ', '.join(arguments + varargs + kwargs)),
                      uncomplete=uncomplete, imports=imports)

# :: MapObject -> {str: SerializedObject}
def map_as_kwargs(mapobject):
    # Keys of kwargs argument must be strings - assertion is checked by
    # the interpreter on runtime.
    return sorted([(eval(k.reconstructor), v) for k,v in mapobject.mapping])

# :: SerializedObject | Call | [SerializedObject] -> [SerializedObject]
def get_contained_objects(obj):
    """Return a list of SerializedObjects this object requires during testing.

    This function will descend recursively if objects contained within given
    object are composite themselves.
    """
    if isinstance(obj, list):
        return flatten(map(get_contained_objects, obj))
    elif isinstance(obj, ImmutableObject):
        # ImmutableObjects are self-sufficient.
        return []
    elif isinstance(obj, UnknownObject):
        return []
    elif isinstance(obj, SequenceObject):
        return get_those_and_contained_objects(obj.contained_objects)
    elif isinstance(obj, MapObject):
        return get_those_and_contained_objects(flatten(obj.mapping))
    elif isinstance(obj, BuiltinException):
        return get_those_and_contained_objects(obj.args)
    elif isinstance(obj, UserObject):
        calls = compact([obj.get_init_call()]) + obj.get_external_calls()
        return get_contained_objects(calls)
    elif isinstance(obj, (FunctionCall, MethodCall)):
        if obj.raised_exception():
            output = obj.exception
        else:
            output = obj.output
        return get_those_and_contained_objects(obj.input.values() + [output])
    elif isinstance(obj, GeneratorObject):
        return get_those_and_contained_objects(obj.input.values() + obj.output)
    else:
        raise TypeError("Wrong argument to get_contained_objects: %r." % obj)

# :: [SerializedObject] -> [SerializedObject]
def get_those_and_contained_objects(objs):
    """Return a list containing given objects and all objects contained within
    them.
    """
    return objs + get_contained_objects(objs)

# :: UserObject | FunctionCall -> {SerializedObject : int}
def get_objects_usage_counts(context):
    """Get dictionary mapping SerializedObjects into their usage counts in
    the context of a given object or call.
    """
    return dict(counted(get_contained_objects(context)))

# :: {SerializedObject: int} -> [SerializedObject]
def objects_worth_naming(usage_counts_mapping):
    def generate():
        for obj, usage_count in usage_counts_mapping.iteritems():
            # ImmutableObjects don't need to be named, as their identity is always
            # unambiguous.
            if not isinstance(obj, ImmutableObject) and usage_count > 1:
                yield obj
    return list(generate())

# :: SerializedObject -> str
def get_name_base_for_object(obj):
    common_names = {'list': 'alist',
                    'dict': 'adict',
                    'array.array': 'array',
                    'types.FunctionType': 'function',
                    'types.GeneratorType': 'generator'}
    return common_names.get(obj.type_name, 'obj')

# :: [str], str -> str
def get_next_name(names, base):
    """Figure out a new name starting with base that doesn't appear in given
    list of names.

    >>> get_next_name(["alist", "adict1", "adict2"], "adict")
    'adict3'
    """
    base_length = len(base)
    def has_right_base(name):
        return name.startswith(base)
    def get_index(name):
        return int(name[base_length:])
    return base + str(max(map(get_index, filter(has_right_base, names))) + 1)

# :: SerializedObject, {SerializedObject: str} -> None
def assign_name_to_object(obj, assigned_names):
    """Assign a right name for given object.

    May reassign an existing name for an object as a side effect.
    """
    base = get_name_base_for_object(obj)
    other_obj = key_for_value(assigned_names, base)

    if other_obj:
        # Avoid overlapping names by numbering objects with the same base.
        assigned_names[other_obj] = base+"1"
        assigned_names[obj] = base+"2"
    elif base+"1" in assigned_names.values():
        # We have some objects already numbered, insert a name with a new index.
        assigned_names[obj] = get_next_name(assigned_names.values(), base)
    else:
        # It's the first object with that base.
        assigned_names[obj] = base

# :: [SerializedObject] -> [SerializedObject]
def objects_sorted_by_timestamp(objects):
    return sorted(objects, key=lambda o: o.timestamp)

# :: [SerializedObject] -> {SerializedObject: str}
def assign_names_to_objects(objects):
    names = {}
    for obj in objects_sorted_by_timestamp(objects):
        assign_name_to_object(obj, names)
    return names

# :: UserObject | FunctionCall -> {SerializedObject : str}
def assign_names_for(context):
    return assign_names_to_objects(objects_worth_naming(get_objects_usage_counts(context)))

# :: {SerializedObject: str} -> [(SerializedObject, str)]
def assigned_names_sorted_by_timestamp(items):
    return sorted(items, key=lambda i: i[0].timestamp)

# :: {SerializedObject: str} -> CallString
def create_setup_for_named_objects(assigned_names):
    full_setup = CallString("")
    already_assigned_names = {}
    # Note that since data we have was gathered during real execution there is
    # no way setup dependencies are cyclic, i.e. there is a strict order of
    # object creation. We've chosen to sort objects by their creation timestamp.
    for obj, name in assigned_names_sorted_by_timestamp(assigned_names.iteritems()):
        constructor = constructor_as_string(obj, already_assigned_names)
        setup = "%s = %s\n" % (name, constructor)
        if constructor.uncomplete:
            setup = "# %s" % setup
        full_setup = full_setup.extend("%s%s" % (full_setup, setup),
                                       constructor.uncomplete,
                                       constructor.imports)
        already_assigned_names[obj] = name
    return full_setup

# :: SerializedObject -> string
def object2id(object):
    """Convert object to string that can be used as an identifier.
    """
    if not isinstance(object, SerializedObject):
        raise TypeError("object2id() should be called with a SerializedObject argument, not %s" % object)
    return object.human_readable_id

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

def call2testname(call, object_name):
    # Note: order is significant. We may have a GeneratorObject that raised
    # an exception, and we care about exceptions more.
    if call.raised_exception():
        return exccall2testname(object_name, call.input, call.exception)
    elif isinstance(call, GeneratorObject):
        return gencall2testname(object_name, call.input, call.output)
    else:
        return objcall2testname(object_name, call.input, call.output)

def sorted_test_method_descriptions(descriptions):
    return sorted(descriptions, key=lambda md: md.name)

def name2testname(name):
    if name[0].isupper():
        return "Test%s" % name
    return "test_%s" % name

def in_lambda(string):
    return "lambda: %s" % string

def in_list(string):
    return "list(%s)" % string

def type_of(string):
    return "type(%s)" % string

def map_types(string):
    return "map(type, %s)" % string

def call_with_args(callable, args):
    """Return an example of a call to callable with all its standard arguments.

    >>> call_with_args('fun', ['x', 'y'])
    'fun(x, y)'
    >>> call_with_args('fun', [('a', 'b'), 'c'])
    'fun((a, b), c)'
    >>> call_with_args('fun', ['a', ('b', ('c', 'd'))])
    'fun(a, (b, (c, d)))'
    """
    def call_arglist(args):
        if isinstance(args, (list, tuple)):
            return "(%s)" % ', '.join(map(call_arglist, args))
        return args
    return "%s%s" % (callable, call_arglist(args))

def assertion_stub(callable, args):
    """Create assertion stub over function/method return value, including names
    of arguments.
    """
    return ('equal_stub', 'expected', call_with_args(callable, args))

def class_init_stub(klass):
    """Create setup that contains stub of object creation for given class.
    """
    args = []
    init_method = klass.get_creational_method()
    if init_method:
        args = init_method.get_call_args()
    return call_with_args(klass.name, args)

# :: (Call, CallString) -> CallString
def decorate_call(call, string):
    if isinstance(call, GeneratorObject):
        invocations = len(call.output)
        if call.raised_exception():
            invocations += 1
        # TODO: generators were added to Python 2.2, while itertools appeared in
        # release  2.3, so we may generate incompatible tests here.
        return string.extend("list(islice(%s, %d))" % (string, invocations),
                             imports=[("itertools", "islice")])
    return string

def should_ignore_method(method):
    return method.is_private()

def testable_calls(calls):
    return [c for c in calls if c.is_testable()]

class UnknownTemplate(Exception):
    def __init__(self, template):
        Exception.__init__(self, "Couldn't find template %r." % template)
        self.template = template

def find_method_code(code, method_name):
    """Return part of the code tree that corresponds to the given method
    definition.
    """
    class LocalizeMethodVisitor(ASTVisitor):
        def __init__(self):
            ASTVisitor.__init__(self)
            self.method_body = None
        def visit_function(self, name, args, body):
            if name == method_name:
                self.method_body = body

    return descend(code.children, LocalizeMethodVisitor).method_body

class TestMethodDescription(object):
    # Assertions should be tuples (type, attributes...), where type is a string
    # denoting a type of an assertion, e.g. 'equal' is an equality assertion.
    #
    # During test generation assertion attributes are passed to the corresponding
    # TestGenerator method as arguments. E.g. assertion of type 'equal' invokes
    # 'equal_assertion' method of the TestGenerator.
    def __init__(self, name, assertions=[], setup=""):
        self.name = name
        self.assertions = assertions
        self.setup = setup

    def contains_code(self):
        return self._has_complete_setup() or self._get_code_assertions()

    # :: str -> str
    def indented_setup(self, indentation):
        """Indent each line of setup with given amount of indentation.

        >>> TestMethodDescription("test", setup="x = 1\\n").indented_setup("  ")
        '  x = 1\\n'
        >>> TestMethodDescription("test", setup="x = 1\\ny = 2\\n").indented_setup("    ")
        '    x = 1\\n    y = 2\\n'
        """
        return ''.join([indentation + line for line in self.setup.splitlines(True)])

    def _get_code_assertions(self):
        return [a for a in self.assertions if a[0] in ['equal', 'missing', 'raises']]

    def _has_complete_setup(self):
        return self.setup and not self.setup.startswith("#")

class TestGenerator(object):
    main_snippet = EmptyCode()

    def from_template(cls, template):
        if template == 'unittest':
            return UnittestTestGenerator()
        elif template == 'nose':
            return NoseTestGenerator()
        else:
            raise UnknownTemplate(template)
    from_template = classmethod(from_template)

    def __init__(self):
        self.imports = []

    def ensure_import(self, import_):
        if import_ is not None and import_ not in self.imports:
            self.imports.append(import_)

    def ensure_imports(self, imports):
        for import_ in imports:
            self.ensure_import(import_)

    def add_tests_to_project(self, project, modnames, force=False):
        for modname in modnames:
            module = project.find_module_by_full_path(modname)
            self._add_tests_for_module(module, project, force)

    def comment_assertion(self, comment):
        return comment

    def equal_stub_assertion(self, expected, actual):
        return "# %s" % self.equal_assertion(expected, actual)

    def raises_stub_assertion(self, exception, code):
        return "# %s" % self.raises_assertion(exception, code)

    def _add_tests_for_module(self, module, project, force):
        log.info("Generating tests for module %s." % module.subpath)
        for test_case in self._generate_test_cases(module):
            add_test_case_to_project(project, test_case, self.main_snippet, force)

    def _generate_test_cases(self, module):
        for object in module.testable_objects:
            test_case = self._generate_test_case(object, module)
            if test_case:
                yield test_case

    def _generate_test_case(self, object, module):
        class_name = name2testname(camelize(object.name))
        method_descriptions = sorted_test_method_descriptions(self._generate_test_method_descriptions(object, module))

        # Don't generate empty test classes.
        if method_descriptions:
            body = self._generate_test_class_code(class_name, method_descriptions)
            return self._generate_test_class(class_name, method_descriptions, module, body)

    def _generate_test_class_code(self, class_name, method_descriptions):
        result = "%s\n" % (self.test_class_header(class_name))
        for method_description in method_descriptions:
            result += "    def %s(self):\n" % method_description.name
            if method_description.setup:
                result += method_description.indented_setup("        ")
            for assertion in method_description.assertions:
                apply_template = getattr(self, "%s_assertion" % assertion[0])
                result += "        %s\n" % apply_template(*assertion[1:])
            # We need at least one statement in a method to be syntatically correct.
            if not method_description.contains_code():
                result += "        pass\n"
            result += "\n"
        return result

    def _generate_test_class(self, class_name, method_descriptions, module, body):
        code = parse_fragment(body)
        def methoddesc2testmethod(method_description):
            name = method_description.name
            return TestMethod(name=name, code=find_method_code(code, name))
        return TestClass(name=class_name,
                         code=code,
                         test_cases=map(methoddesc2testmethod, method_descriptions),
                         imports=self.imports,
                         associated_modules=[module])

    def _generate_test_method_descriptions(self, object, module):
        if isinstance(object, Function):
            return self._generate_test_method_descriptions_for_function(object, module)
        elif isinstance(object, Class):
            return self._generate_test_method_descriptions_for_class(object, module)
        else:
            raise TypeError("Don't know how to generate test method descriptions for %s" % object)

    def _generate_test_method_descriptions_for_function(self, function, module):
        if testable_calls(function.calls):
            log.debug("Detected %s in function %s." % \
                          (pluralize("testable call", len(testable_calls(function.calls))),
                           function.name))

            # We're calling the function, so we have to make sure it will
            # be imported in the test
            self.ensure_import((module.locator, function.name))

            # We have at least one call registered, so use it.
            return self._method_descriptions_from_function(function)
        else:
            # No calls were traced, so we're go for a single test stub.
            log.debug("Detected _no_ testable calls in function %s." % function.name)
            name = name2testname(underscore(function.name))
            assertions = [assertion_stub(function.name, function.args), ('missing',)]
            return [TestMethodDescription(name, assertions)]

    def _generate_test_method_descriptions_for_class(self, klass, module):
        if klass.user_objects:
            # We're calling the method, so we have to make sure its class
            # will be imported in the test.
            self.ensure_import((module.locator, klass.name))

        for user_object in klass.user_objects:
            yield self._method_description_from_user_object(user_object)

        # No calls were traced for those methods, so we'll go for simple test stubs.
        for method in klass.get_untraced_methods():
            if not should_ignore_method(method):
                yield self._generate_test_method_description_for_method(klass, method)

    def _generate_test_method_description_for_method(self, klass, method):
        test_name = name2testname(method.name)
        object_name = underscore(klass.name)
        setup = '# %s = %s\n' % (object_name, class_init_stub(klass))
        assertions = [('missing',)]
        # Generate assertion stub, but only for non-creational methods.
        if not method.is_creational():
            assertions.insert(0, assertion_stub("%s.%s" % (object_name, method.name),
                                                method.get_call_args()))
        return TestMethodDescription(test_name, assertions=assertions, setup=setup)

    def _method_descriptions_from_function(self, function):
        for call in testable_calls(function.get_unique_calls()):
            assigned_names = assign_names_for(call)
            name = call2testname(call, function.name)
            setup = create_setup_for_named_objects(assigned_names)
            assertions = [self._create_assertion(function.name, call,
                                                 stub=setup.uncomplete,
                                                 assigned_names=assigned_names)]

            yield TestMethodDescription(name, assertions, setup)

    def _method_description_from_user_object(self, user_object):
        init_call = user_object.get_init_call()
        external_calls = testable_calls(user_object.get_external_calls())
        local_name = underscore(user_object.klass.name)

        assigned_names = assign_names_for(user_object)
        named_objects_setup = create_setup_for_named_objects(assigned_names)

        constructor = constructor_as_string(user_object, assigned_names)
        stub_all = constructor.uncomplete or named_objects_setup.uncomplete

        self.ensure_imports(constructor.imports)
        self.ensure_imports(named_objects_setup.imports)

        def test_name():
            if len(external_calls) == 0 and init_call:
                test_name = "test_creation"
                if init_call.input:
                    test_name += "_with_%s" % arguments_as_string(init_call.input)
                if init_call.raised_exception():
                    test_name += "_raises_%s" % object2id(init_call.exception)
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

        def assertions():
            if init_call and len(external_calls) == 0:
                # If the constructor raised an exception, object creation should be an assertion.
                if init_call.raised_exception():
                    yield self._create_assertion(user_object.klass.name, init_call, stub=stub_all, assigned_names=assigned_names)
                else:
                    yield(('comment', "# Make sure it doesn't raise any exceptions."))

            for call in external_calls:
                name = "%s.%s" % (local_name, call.definition.name)
                yield(self._create_assertion(name, call, stub=stub_all, assigned_names=assigned_names))

        def setup():
            if init_call and init_call.raised_exception():
                return ""
            else:
                setup = "%s = %s\n" % (local_name, constructor)
                # Comment out the constructor if it isn't complete.
                if stub_all:
                    setup = "# %s" % setup
                return setup

        return TestMethodDescription(test_name(),
                                     list(assertions()),
                                     named_objects_setup + setup())

    def _create_assertion(self, name, call, stub=False, assigned_names={}):
        """Create a new assertion based on a given call and a name provided
        for it.

        Generated assertion will be a stub if input of a call cannot be
        constructed or if stub argument is True.
        """
        callstring = decorate_call(call, call_as_string(name, call.input,
            call.definition, assigned_names))

        self.ensure_imports(callstring.imports)

        if call.raised_exception():
            return self._exception_assertion(call.exception, callstring, stub)
        else:
            if callstring.uncomplete or stub:
                assertion_type = 'equal_stub'
            else:
                assertion_type = 'equal'

            if can_be_constructed(call.output):
                return (assertion_type,
                        constructor_as_string(call.output, assigned_names),
                        callstring)
            else:
                # If we can't test for real values, let's at least test for the right type.
                output_type = type_as_string(call.output)
                if isinstance(call, GeneratorObject):
                    callstring_type = map_types(callstring)
                else:
                    callstring_type = type_of(callstring)
                self.ensure_import('types')
                return (assertion_type, output_type, callstring_type)

    def _exception_assertion(self, exception, callstring, stub):
        if is_serialized_string(exception):
            # We generate assertion stub because assertRaises handles string
            # exceptions by identity, not value. This is also the default
            # behavior of CPython's except clause, see:
            #
            # <http://docs.python.org/reference/executionmodel.html#exceptions>
            #     Exceptions can also be identified by strings, in which case
            #     the except clause is selected by object identity.
            #
            # TODO: It is possible to write assertRaisesString, which compares
            # string exceptions by value. We don't use this solution, because
            # currently in Pythoscope there is no facility for attaching and
            # using test helpers.
            return ('raises_stub',
                    todo_value(exception.reconstructor),
                    in_lambda(callstring))

        if callstring.uncomplete or stub:
            assertion_type = 'raises_stub'
        else:
            assertion_type = 'raises'
        self.ensure_import(exception.type_import)
        return (assertion_type, exception.type_name, in_lambda(callstring))

class UnittestTestGenerator(TestGenerator):
    main_snippet = parse_fragment("if __name__ == '__main__':\n    unittest.main()\n")

    def test_class_header(self, name):
        self.ensure_import('unittest')
        return "class %s(unittest.TestCase):" % name

    def equal_assertion(self, expected, actual):
        return "self.assertEqual(%s, %s)" % (expected, actual)

    def raises_assertion(self, exception, code):
        return "self.assertRaises(%s, %s)" % (exception, code)

    def missing_assertion(self):
        return "assert False # TODO: implement your test here"

class NoseTestGenerator(TestGenerator):
    def test_class_header(self, name):
        return "class %s:" % name

    def equal_assertion(self, expected, actual):
        self.ensure_import(('nose.tools', 'assert_equal'))
        return "assert_equal(%s, %s)" % (expected, actual)

    def raises_assertion(self, exception, code):
        self.ensure_import(('nose.tools', 'assert_raises'))
        return "assert_raises(%s, %s)" % (exception, code)

    def missing_assertion(self):
        self.ensure_import(('nose', 'SkipTest'))
        return "raise SkipTest # TODO: implement your test here"

def add_tests_to_project(project, modnames, template, force=False):
    generator = TestGenerator.from_template(template)
    generator.add_tests_to_project(project, modnames, force)

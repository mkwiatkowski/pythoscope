from pythoscope.compat import set, sorted
from pythoscope.generator.code_string import CodeString, combine
from pythoscope.generator.constructor import constructor_as_string, call_as_string_for
from pythoscope.serializer import BuiltinException, ImmutableObject,\
    MapObject, UnknownObject, SequenceObject, SerializedObject
from pythoscope.side_effect import ListAppend, ListExtend
from pythoscope.store import Call, FunctionCall, UserObject, MethodCall,\
    GeneratorObject, GeneratorObjectInvocation
from pythoscope.util import counted, flatten, key_for_value


# :: Call -> Call
def top_caller(call):
    if call.caller is None:
        return call
    return top_caller(call.caller)

# :: (Call, int) -> [Call]
def subcalls_before_timestamp(call, reference_timestamp):
    for c in call.subcalls:
        if c.timestamp < reference_timestamp:
            yield c
            for sc in subcalls_before_timestamp(c, reference_timestamp):
                yield sc

# :: Call -> [Call]
def calls_before(call):
    """Go up the call graph and return all calls that happened before
    the given one.

    >>> class Call(object):
    ...     def __init__(self, caller, timestamp):
    ...         self.subcalls = []
    ...         self.caller = caller
    ...         self.timestamp = timestamp
    ...         if caller:
    ...             caller.subcalls.append(self)
    >>> top = Call(None, 1)
    >>> branch1 = Call(top, 2)
    >>> leaf1 = Call(branch1, 3)
    >>> branch2 = Call(top, 4)
    >>> leaf2 = Call(branch2, 5)
    >>> leaf3 = Call(branch2, 6)
    >>> leaf4 = Call(branch2, 7)
    >>> branch3 = Call(top, 8)
    >>> calls_before(branch3) == [top, branch1, leaf1, branch2, leaf2, leaf3, leaf4]
    True
    >>> calls_before(leaf3) == [top, branch1, leaf1, branch2, leaf2]
    True
    >>> calls_before(branch2) == [top, branch1, leaf1]
    True
    >>> calls_before(branch1) == [top]
    True
    """
    top = top_caller(call)
    return [top] + list(subcalls_before_timestamp(top, call.timestamp))

# :: Call -> [SideEffect]
def side_effects_before(call):
    return flatten(map(lambda c: c.side_effects, calls_before(call)))

# :: SerializedObject | Call | [SerializedObject] | [Call] -> [SerializedObject]
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
        return get_contained_objects(obj.get_init_and_external_calls())
    elif isinstance(obj, (FunctionCall, MethodCall, GeneratorObjectInvocation)):
        if obj.raised_exception():
            output = obj.exception
        else:
            output = obj.output
        return get_those_and_contained_objects(obj.input.values() + [output])
    elif isinstance(obj, GeneratorObject):
        if obj.is_activated():
            return get_those_and_contained_objects(obj.args.values()) +\
                get_contained_objects(obj.calls)
        else:
            return []
    else:
        raise TypeError("Wrong argument to get_contained_objects: %r." % obj)

# :: [SerializedObject] -> [SerializedObject]
def get_those_and_contained_objects(objs):
    """Return a list containing given objects and all objects contained within
    them.
    """
    return objs + get_contained_objects(objs)

# :: [SerializedObject|Call] -> [SerializedObject|Call]
def sorted_by_timestamp(objects):
    return sorted(objects, key=lambda o: o.timestamp)

# :: [SideEffect] -> [SerializedObject]
def objects_referenced_by_side_effects(side_effects):
    return flatten(map(lambda se: se.referenced_objects, side_effects))

# :: ([SideEffect], set([SerializedObject])) -> [SideEffect]
def side_effects_that_affect_objects(side_effects, objects):
    "Filter out side effects that are irrelevant to given set of objects."
    for side_effect in side_effects:
        for obj in side_effect.referenced_objects:
            if obj in objects:
                yield side_effect

class Dependencies(object):
    def __init__(self, call):
        self.objects = []
        self.side_effects = set()

        self._calculate(call)

    def _calculate(self, call):
        """
        First, we gather all objects referenced by the call. Next, we look at all
        side effects that affected those objects before the call. Those side
        effects can reference more objects, which in turn can be affected by more
        side effects, so we do this back and forth until we have a complete set
        of objects and side effects that have direct or indirect relationship to
        the call.
        """
        sebc = side_effects_before(call)
        def update(objects):
            self.objects.extend(objects)

            # We have some objects, let's see how many side effects affect them.
            new_side_effects = set(side_effects_that_affect_objects(sebc, objects))
            previous_side_effects_count = len(self.side_effects)
            self.side_effects.update(new_side_effects)
            if len(self.side_effects) == previous_side_effects_count:
                return

            # Similarly, new side effects may yield some new objects, let's recur.
            update(get_those_and_contained_objects(objects_referenced_by_side_effects(new_side_effects)))
        # We start with objects required for the call itself.
        update(get_contained_objects(call))

    def fold(self):
        return self # TODO

    def remove_objects_unworthty_of_naming(self):
        referenced_objects = objects_referenced_by_side_effects(self.side_effects)
        for obj, usage_count in counted(self.objects):
            # ImmutableObjects don't need to be named, as their identity is
            # always unambiguous.
            if not isinstance(obj, ImmutableObject):
                # Anything mentioned more than once have to be named.
                if usage_count > 1:
                    continue
                # Anything with side effects is also worth naming.
                if obj in referenced_objects:
                    continue
            for i in range(usage_count):
                self.objects.remove(obj)
        return self

    def all(self):
        return list(set(self.objects).union(self.side_effects))

    def sorted(self):
        """
        Since data we have was gathered during real execution there is no way setup
        dependencies are cyclic, i.e. there is a strict order of object creation.
        We've chosen to sort objects by their creation timestamp.
        """
        return sorted_by_timestamp(self.all())

    def unique_objects(self):
        return set(self.objects)

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

# :: ([SerializedObject], {SerializedObject: str}) -> None
def assign_names_to_objects(objects, names):
    """Modifies names dictionary as a side effect.
    """
    for obj in sorted_by_timestamp(objects):
        assign_name_to_object(obj, names)

# :: (SerializedObject, str, {SerializedObject: str}) -> CodeString
def setup_for_named_object(obj, name, already_assigned_names):
    constructor = constructor_as_string(obj, already_assigned_names)
    setup = combine(name, constructor, "%s = %s\n")
    if constructor.uncomplete:
        setup = combine("# ", setup)
    return setup

# :: CodeString -> CodeString
def add_newline(code_string):
    return combine(code_string, "\n")

# :: (SideEffect, {SerializedObject: str}) -> CodeString
def setup_for_side_effect(side_effect, already_assigned_names):
    object_name = already_assigned_names[side_effect.alist]
    if isinstance(side_effect, ListAppend):
        return add_newline(call_as_string_for("%s.%s" % (object_name, ListAppend.definition.name),
                                              {'object': side_effect.element},
                                              ListAppend.definition,
                                              already_assigned_names))
    elif isinstance(side_effect, ListExtend):
        return add_newline(call_as_string_for("%s.%s" % (object_name, ListExtend.definition.name),
                                              {'iterable': side_effect.iterable},
                                              ListExtend.definition,
                                              already_assigned_names))
    else:
        raise TypeError("Unknown side effect type: %r" % side_effect)

# :: (Dependencies, {SerializedObject: str}) -> CodeString
def create_setup_for_dependencies(dependencies, names):
    """Returns a setup code string. Modifies names dictionary as a side effect.
    """
    already_assigned_names = names.copy()
    assign_names_to_objects(dependencies.unique_objects(), names)
    full_setup = CodeString("")
    for dependency in dependencies.sorted():
        if isinstance(dependency, SerializedObject):
            name = names[dependency]
            setup = setup_for_named_object(dependency, name, already_assigned_names)
            already_assigned_names[dependency] = name
        else:
            setup = setup_for_side_effect(dependency, already_assigned_names)
        full_setup = combine(full_setup, setup)
    return full_setup

# :: (Call, {SerializedObject : str}) -> CodeString
def assign_names_and_setup(call, names):
    """Returns a setup code string. Modifies names dictionary as a side effect.
    """
    if not isinstance(call, Call):
        raise TypeError("Tried to call assign_names_and_setup with %r instead of a call." % call)
    dependencies = Dependencies(call).fold().remove_objects_unworthty_of_naming()
    return create_setup_for_dependencies(dependencies, names)

# :: ([Call], {SerializedObject : str}) -> CodeString
def assign_names_and_setup_for_multiple_calls(calls, names):
    """Returns a setup code string. Modifies names dictionary as a side effect.
    """
    full_setup = CodeString("")
    for call in sorted_by_timestamp(calls):
        setup = assign_names_and_setup(call, names)
        full_setup = combine(full_setup, setup)
    return full_setup

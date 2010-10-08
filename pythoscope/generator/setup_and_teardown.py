from pythoscope.compat import all, set
from pythoscope.generator.code_string import CodeString, combine
from pythoscope.generator.constructor import constructor_as_string, call_as_string_for
from pythoscope.generator.dependencies import Dependencies, sorted_by_timestamp,\
    older_than, side_effects_before, side_effects_that_affect_objects,\
    objects_affected_by_side_effects
from pythoscope.generator.setup_optimizer import optimize
from pythoscope.serializer import BuiltinException, ImmutableObject, MapObject,\
    UnknownObject, SequenceObject, SerializedObject
from pythoscope.side_effect import BuiltinMethodWithPositionArgsSideEffect, SideEffect
from pythoscope.store import Call, FunctionCall, UserObject, MethodCall,\
    GeneratorObject, GeneratorObjectInvocation
from pythoscope.util import counted, flatten, key_for_value


# :: SerializedObject | [SerializedObject] -> bool
def can_be_constructed(obj):
    if isinstance(obj, list):
        return all(map(can_be_constructed, obj))
    elif isinstance(obj, SequenceObject):
        return all(map(can_be_constructed, obj.contained_objects))
    elif isinstance(obj, GeneratorObject):
        return obj.is_activated()
    return not isinstance(obj, UnknownObject)

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

# :: [SideEffect] -> [SerializedObject]
def objects_referenced_by_side_effects(side_effects):
    return flatten(map(lambda se: se.referenced_objects, side_effects))

class CallDependencies(Dependencies):
    """Dependencies for making a call and later asserting its output and side
    effects.
    """
    def __init__(self, call):
        super(CallDependencies, self).__init__()
        objects = get_those_and_contained_objects(call.input.values())
        if call.output is not None:
            # If pieces of the output (or even the output itself) have been
            # created before the call we want to reuse them at assertion time.
            # To make sure those pieces get named we bump their usage counts
            # by one.
            objects += older_than(get_those_and_contained_objects([call.output]), call.timestamp)
        self._calculate(objects, side_effects_before(call), call.side_effects)

    def _calculate(self, objects, relevant_side_effects, additional_affecting_side_effects):
        """
        First, we look at all objects required for the call's input/output
        (pre- and post- call dependencies each do one of those). Next, we look
        at all side effects that affected those objects before the call. Those
        side effects can reference more objects, which in turn can be affected
        by more side effects, so we do this back and forth until we have
        a complete set of objects and side effects that have direct or indirect
        relationship to the call.
        """
        all_objects = []
        all_side_effects = set()
        def update(objects):
            all_objects.extend(objects)

            # We have some objects, let's see how many side effects affect them.
            new_side_effects = set(side_effects_that_affect_objects(relevant_side_effects, objects))
            previous_side_effects_count = len(all_side_effects)
            all_side_effects.update(new_side_effects)
            if len(all_side_effects) == previous_side_effects_count:
                return

            # Similarly, new side effects may yield some new objects, let's recur.
            update(get_those_and_contained_objects(objects_referenced_by_side_effects(new_side_effects)))
        # We start with objects required for the call itself.
        update(objects)

        # Finally assemble the whole timeline of dependencies.
        # Since data we have was gathered during real execution there is no way setup
        # dependencies are cyclic, i.e. there is a strict order of object creation.
        # We've chosen to sort objects by their creation timestamp.
        self.all = sorted_by_timestamp(set(all_objects).union(all_side_effects))

        self._remove_objects_unworthy_of_naming(dict(counted(all_objects)),
                                                self.get_side_effects() + additional_affecting_side_effects)

        optimize(self)

    def _remove_objects_unworthy_of_naming(self, objects_usage_counts, side_effects):
        affected_objects = objects_affected_by_side_effects(side_effects)
        for obj, usage_count in objects_usage_counts.iteritems():
            # ImmutableObjects don't need to be named, as their identity is
            # always unambiguous.
            if not isinstance(obj, ImmutableObject):
                # Anything mentioned more than once have to be named.
                if usage_count > 1:
                    continue
                # Anything affected by side effects is also worth naming.
                if obj in affected_objects:
                    continue
            self.all.remove(obj)

    def get_side_effects(self):
        return filter(lambda x: isinstance(x, SideEffect), self.all)

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

# :: SerializedObject, {SerializedObject: str}, bool -> None
def assign_name_to_object(obj, assigned_names, rename=True):
    """Assign a right name for given object.

    May reassign an existing name for an object as a side effect, unless
    `rename` is False.
    """
    if assigned_names.has_key(obj):
        return
    base = get_name_base_for_object(obj)
    other_obj = key_for_value(assigned_names, base)

    if other_obj:
        # Avoid overlapping names by numbering objects with the same base.
        if rename:
            assigned_names[other_obj] = base+"1"
        assigned_names[obj] = base+"2"
    elif base+"1" in assigned_names.values():
        # We have some objects already numbered, insert a name with a new index.
        assigned_names[obj] = get_next_name(assigned_names.values(), base)
    else:
        # It's the first object with that base.
        assigned_names[obj] = base

# :: ([SerializedObject], {SerializedObject: str}), bool -> None
def assign_names_to_objects(objects, names, rename=True):
    """Modifies names dictionary as a side effect.
    """
    for obj in sorted_by_timestamp(objects):
        assign_name_to_object(obj, names, rename)

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
    object_name = already_assigned_names[side_effect.obj]
    if isinstance(side_effect, BuiltinMethodWithPositionArgsSideEffect):
        return add_newline(call_as_string_for("%s.%s" % (object_name, side_effect.definition.name),
                                              side_effect.args_mapping(),
                                              side_effect.definition,
                                              already_assigned_names))
    else:
        raise TypeError("Unknown side effect type: %r" % side_effect)

# :: (Dependencies, {SerializedObject: str}) -> CodeString
def create_setup_for_dependencies(dependencies, names, rename=True):
    """Returns a setup code string. Modifies names dictionary as a side effect.
    """
    already_assigned_names = names.copy()
    assign_names_to_objects(dependencies.get_objects(), names, rename)
    full_setup = CodeString("")
    for dependency in dependencies.all:
        if isinstance(dependency, SerializedObject):
            name = names[dependency]
            setup = setup_for_named_object(dependency, name, already_assigned_names)
            already_assigned_names[dependency] = name
        else:
            setup = setup_for_side_effect(dependency, already_assigned_names)
        full_setup = combine(full_setup, setup)
    return full_setup

# :: (Call, {SerializedObject : str}), bool -> CodeString
def assign_names_and_setup(call, names, rename=True):
    """Returns a setup code string. Modifies names dictionary as a side effect.
    """
    if not isinstance(call, Call):
        raise TypeError("Tried to call assign_names_and_setup with %r instead of a call." % call)
    dependencies = CallDependencies(call)
    return create_setup_for_dependencies(dependencies, names, rename)

# :: ([Call], {SerializedObject : str}) -> CodeString
def assign_names_and_setup_for_multiple_calls(calls, names):
    """Returns a setup code string. Modifies names dictionary as a side effect.
    """
    full_setup = CodeString("")
    rename = True
    for call in sorted_by_timestamp(calls):
        setup = assign_names_and_setup(call, names, rename)
        full_setup = combine(full_setup, setup)
        rename = False # We can't rename after the first setup is already done.
    return full_setup

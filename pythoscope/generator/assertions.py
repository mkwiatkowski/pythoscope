from copy import copy

from pythoscope.compat import set
from pythoscope.generator.code_string import CodeString
from pythoscope.generator.dependencies import sorted_by_timestamp,\
    side_effects_before, objects_affected_by_side_effects, side_effects_of,\
    older_than, resolve_dependencies
from pythoscope.generator.method_call_context import MethodCallContext
from pythoscope.generator.lines import *
from pythoscope.generator.selector import testable_calls
from pythoscope.serializer import BuiltinException, ImmutableObject, MapObject,\
    UnknownObject, SequenceObject
from pythoscope.side_effect import SideEffect, GlobalRead, GlobalRebind,\
    BuiltinMethodWithPositionArgsSideEffect
from pythoscope.store import Function, FunctionCall, UserObject, MethodCall,\
    GeneratorObject, GeneratorObjectInvocation, Call, CallToC, Method
from pythoscope.util import all_of_type, compact, flatten, underscore


# :: Call | GeneratorObject | UserObject | Method | Function -> [Event]
def assertions_for_interaction(testable_interaction):
    if isinstance(testable_interaction, (Method, Function)):
        timeline = []
    else:
        timeline = expand_into_timeline(testable_interaction)
    if isinstance(testable_interaction, UserObject):
        test_timeline = test_timeline_for_user_object(timeline, testable_interaction)
    elif isinstance(testable_interaction, Method):
        test_timeline = test_timeline_for_method(testable_interaction)
    elif isinstance(testable_interaction, Function):
        test_timeline = test_timeline_for_function(testable_interaction)
    else:
        test_timeline = test_timeline_for_call(timeline, testable_interaction)
    return remove_duplicates_and_bare_method_contexts(sorted_by_timestamp(include_requirements(test_timeline, timeline)))

# :: Method -> [Event]
def test_timeline_for_method(method):
    object_name = underscore(method.klass.name)
    init_stub = '# %s = %s' % (object_name, class_init_stub(method.klass))
    timeline = [CommentLine(init_stub, 1)]
    # Generate assertion stub, but only for non-creational methods.
    if not method.is_creational():
        actual = call_with_args("%s.%s" % (object_name, method.name),
                                method.get_call_args())
        timeline.append(EqualAssertionStubLine(actual, 2))
    timeline.append(SkipTestLine(3))
    return timeline

# :: Function -> [Event]
def test_timeline_for_function(function):
    actual = call_with_args(function.name, function.args)
    return [EqualAssertionStubLine(actual, 1), SkipTestLine(2)]

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

def class_init_stub(klass):
    """Create setup that contains stub of object creation for given class.
    """
    args = []
    init_method = klass.get_creational_method()
    if init_method:
        args = init_method.get_call_args()
    return call_with_args(klass.name, args)

# :: ([Event], UserObject) -> [Event]
def test_timeline_for_user_object(execution_events, user_object):
    """Construct a new timeline for a test case based on real execution timeline
    and a user object that needs to be tested.

    The new timeline in most cases will contain assertions.
    """
    init_call = user_object.get_init_call()
    external_calls = testable_calls(user_object.get_external_calls())
    # If the constructor raised an exception, object creation should be an assertion.
    if init_call and init_call.raised_exception():
        call_return_timestamp = last_call_action_timestamp(init_call)
        return [RaisesAssertionLine(init_call.exception, MethodCallContext(init_call, user_object), call_return_timestamp+0.25)]
    timeline = give_context_to_method_calls(compact([init_call]) + flatten(map(lambda call: test_timeline_for_call(execution_events, call), external_calls)), user_object)
    if init_call and len(external_calls) == 0:
        timeline.append(CommentLine("# Make sure it doesn't raise any exceptions.", timeline[-1].timestamp))
    return timeline

# :: Call | GeneratorObject -> int
def last_call_action_timestamp(call):
    if isinstance(call, GeneratorObject):
        return max(map(last_call_action_timestamp, call.calls))
    if call.side_effects:
        return call.side_effects[-1].timestamp
    return call.timestamp

# :: ([Event], UserObject) -> [Event|MethodCallContext]
def give_context_to_method_calls(events, user_object):
    def contextize(event):
        if isinstance(event, EqualAssertionLine) and isinstance(event.actual, Call):
            event.actual = MethodCallContext(event.actual, user_object)
            return event
        elif isinstance(event, RaisesAssertionLine):
            event.call = MethodCallContext(event.call, user_object)
            return event
        elif isinstance(event, GeneratorAssertionLine):
            event.generator_call = MethodCallContext(event.generator_call, user_object)
            return event
        elif isinstance(event, MethodCall):
            return MethodCallContext(event, user_object)
        else:
            return event
    return map(contextize, events)

# :: ([Event], [Event], Call|GeneratorObject) -> None
def add_test_events_for_output(events, execution_events, call):
    def copy_object_at(obj, timestamp):
        if isinstance(obj, ImmutableObject):
            return obj, []
        new_obj = event_copy(obj)
        new_ses = older_than(side_effects_that_affect_object(execution_events, obj), timestamp)
        return new_obj, copy_side_effects(new_ses, obj, new_obj)
    call_return_timestamp = last_call_action_timestamp(call)
    if call.raised_exception():
        events.extend([RaisesAssertionLine(call.exception, call, call_return_timestamp+0.25)])
    else:
        if isinstance(call, GeneratorObject):
            events.extend([GeneratorAssertionLine(call, call_return_timestamp+0.25)])
        else:
            # We want a copy of the output right after the call, so we pass a timestamp
            # slightly bigger than the call return.
            output_copy, output_side_effects = copy_object_at(call.output, call_return_timestamp+0.01)
            events.extend([output_copy] + output_side_effects)
            if call.output.timestamp < call.timestamp and not isinstance(call.output, ImmutableObject):
                # If object existed before the call and is mutable we need two
                # assertions: one for identity, the other for value.
                events.extend([EqualAssertionLine(call.output, call, call_return_timestamp+0.25),
                               EqualAssertionLine(output_copy, call.output, call_return_timestamp+0.75)])
            else:
                # If it didn't exist before the call we just need a value assertion.
                events.extend([EqualAssertionLine(output_copy, call, call_return_timestamp+0.75)])

# :: ([Event], [SideEffect]) -> None
def add_test_events_for_side_effects(events, side_effects):
    globals_already_setup = set()
    step = 0
    first_timestamp = events[0].timestamp
    last_timestamp = events[-1].timestamp
    for side_effect in side_effects:
        if isinstance(side_effect, GlobalRead) and\
                side_effect.get_full_name() not in globals_already_setup:
            tmp_name = "old_%s_%s" % (side_effect.module.replace(".", "_"), side_effect.name)
            ref = VariableReference(side_effect.module, side_effect.name, first_timestamp-4.2-step)
            # SETUP: old_module_variable = module.variable
            events.insert(0, Assign(tmp_name, ref, first_timestamp-3.2-step))
            # SETUP: module.variable = value
            events.insert(1, Assign(side_effect.get_full_name(), side_effect.value, first_timestamp-2.2-step))
            # TEARDOWN: module.variable = old_module_variable
            # TODO: Crazy hack, teardowns should always be at the end, I'll fix
            # that someday.
            events.append(Assign(side_effect.get_full_name(), tmp_name, last_timestamp+300.2+step))
            globals_already_setup.add((side_effect.get_full_name()))
        elif isinstance(side_effect, GlobalRebind):
            events.append(EqualAssertionLine(side_effect.value,
                VariableReference(side_effect.module, side_effect.name, last_timestamp+1.1+step),
                last_timestamp+2.1+step))
        step += 5

# :: Call|GeneratorObject -> [SideEffect]
def side_effects_of_call(call):
    if isinstance(call, GeneratorObject):
        return flatten([c.side_effects for c in call.calls])
    return call.side_effects

# :: ([Event], Call|GeneratorObject) -> [Event]
def test_timeline_for_call(execution_events, call):
    """Construct a new timeline for a test case based on real execution timeline
    and a call that needs to be tested.

    The new timeline in most cases will contain assertions.
    """
    events = []
    add_test_events_for_output(events, execution_events, call)
    add_test_events_for_side_effects(events, side_effects_of_call(call))
    return events

# :: Event -> Event
def event_copy(event):
    new_event = copy(event)
    new_event.timestamp = event.timestamp+0.5
    return new_event

# :: (list, object, object) -> None
def replace(alist, old_element, new_element):
    def pass_or_replace(element):
        if element is old_element:
            return new_element
        return element
    return map(pass_or_replace, alist)

# :: (SideEffect, SerializedObject, SerializedObject) -> SideEffect
def copy_side_effects(side_effects, old_obj, new_obj):
    "Copy side effects replacing occurences of old_obj with new_obj."
    new_side_effects = []
    for side_effect in side_effects:
        new_side_effect = event_copy(side_effect)
        new_side_effect.affected_objects = replace(new_side_effect.affected_objects, old_obj, new_obj)
        new_side_effect.referenced_objects = replace(new_side_effect.referenced_objects, old_obj, new_obj)
        if isinstance(side_effect, BuiltinMethodWithPositionArgsSideEffect):
            new_side_effect.obj = new_side_effect.affected_objects[0]
            new_side_effect.args = new_side_effect.referenced_objects[1:]
        new_side_effects.append(new_side_effect)
    return new_side_effects

# :: (Event, ...) -> [Event]
def expand_into_timeline(*events):
    """Return a sorted list of all events related to given events in any way.
    """
    return sorted_by_timestamp(set(enumerate_events(list(events))))

# :: [Event] -> [Event]
def enumerate_events(objs):
    """Return a list of all events needed for testing by the objects passed.

    Avoids infinite recursion by keeping a list of events already traversed.
    """
    events_so_far = set()
    def get_those_and_contained_events(objs):
        """Return a list containing given objects and all objects contained within
        them.
        """
        return objs + get_contained_events(objs)
    def get_contained_events(obj):
        """Return a list of Events this object requires during testing.

        This function will descend recursively if objects contained within given
        object are composite themselves.
        """
        if isinstance(obj, list):
            return flatten(map(get_contained_events, obj))
        # Lists are unhashable anyway, so we don't remember them.
        if obj in events_so_far:
            return []
        else:
            events_so_far.add(obj)
        if isinstance(obj, ImmutableObject):
            # ImmutableObjects are self-sufficient.
            return []
        elif isinstance(obj, UnknownObject):
            return []
        elif isinstance(obj, SequenceObject):
            return get_those_and_contained_events(obj.contained_objects)
        elif isinstance(obj, MapObject):
            return get_those_and_contained_events(flatten(obj.mapping))
        elif isinstance(obj, BuiltinException):
            return get_those_and_contained_events(obj.args)
        elif isinstance(obj, UserObject):
            return get_contained_events(obj.get_init_and_external_calls())
        elif isinstance(obj, (FunctionCall, MethodCall, GeneratorObjectInvocation)):
            ret = get_those_and_contained_events(obj.input.values() + list(obj.side_effects))
            if obj.caller:
                ret += side_effects_before_and_affected_objects(obj)
            return ret
        elif isinstance(obj, GeneratorObject):
            if obj.is_activated():
                return get_those_and_contained_events(obj.args.values()) +\
                    get_contained_events(obj.calls)
            else:
                return []
        elif isinstance(obj, SideEffect):
            return [obj] + get_those_and_contained_events(list(obj.affected_objects))
        elif isinstance(obj, CallToC):
            return side_effects_before_and_affected_objects(obj)
        else:
            raise TypeError("Wrong argument to get_contained_events: %s." % repr(obj))
    return get_those_and_contained_events(objs)

def side_effects_before_and_affected_objects(call):
    se = side_effects_before(call)
    return se + objects_affected_by_side_effects(se)

# :: [Event] -> [Event]
def remove_duplicates_and_bare_method_contexts(events):
    new_events = list()
    for event in events:
        if not isinstance(event, MethodCallContext) and event not in new_events:
            new_events.append(event)
    return new_events

def include_requirements(test_events, execution_events):
    ignored_side_effects = side_effects_of(explicit_calls(test_events))
    new_events = []
    for event in test_events:
        for new_event in objects_required_for(event, event.timestamp, execution_events):
            # If a call appears explicitly in the test body we should
            # ignore all side effects caused by it.
            if new_event not in ignored_side_effects:
                new_events.append(new_event)
    return new_events + test_events

# [Event] -> [Call]
def explicit_calls(event):
    if isinstance(event, list):
        return flatten(map(explicit_calls, event))
    if isinstance(event, Call):
        return [event] + explicit_calls(event.subcalls)
    elif isinstance(event, GeneratorObject):
        return explicit_calls(event.calls)
    elif isinstance(event, EqualAssertionLine) and isinstance(event.actual, Call):
        return explicit_calls(event.actual)
    elif isinstance(event, GeneratorAssertionLine):
        return explicit_calls(event.generator_call)
    elif isinstance(event, RaisesAssertionLine):
        return explicit_calls(event.call)
    elif isinstance(event, MethodCallContext):
        return explicit_calls(event.call)
    return []

# :: (Event, int, [Event]) -> [SerializedObject|SideEffect]
def objects_required_for(test_event, timestamp, execution_events):
    required_objects = []
    required_side_effects = []
    objects = resolve_dependencies(test_event)
    while objects:
        new_objects, new_side_effects = copy_events_over(objects, timestamp, execution_events)
        required_objects.extend(new_objects)
        required_side_effects.extend(new_side_effects)
        objects = list(new_only(objects_affected_by_side_effects(new_side_effects), required_objects))
    return required_objects + required_side_effects

# :: ([SerializedObject], int, [Event]) -> ([SerializedObject], [SideEffect])
def copy_events_over(objects, timestamp, execution_events):
    copied_objects = []
    copied_side_effects = []
    def side_effects_of(obj):
        return older_than(side_effects_that_affect_object(execution_events, obj), timestamp)
    for obj in objects:
        copied_objects.append(obj)
        copied_side_effects.extend(side_effects_of(obj))
    return copied_objects, copied_side_effects

def new_only(affected, so_far):
    for obj in affected:
        if obj not in so_far:
            yield obj

# :: ([Event], SerializedObject) -> [SideEffect]
def side_effects_that_affect_object(events, obj):
    "Filter out side effects that are irrelevant to given object."
    for side_effect in all_of_type(events, SideEffect):
        if obj in side_effect.affected_objects:
            yield side_effect


from copy import copy

from pythoscope.event import Event
from pythoscope.generator.code_string import addimport, CodeString, combine,\
    putinto
from pythoscope.generator.constructor import constructor_as_string,\
    call_as_string_for, import_for, type_as_string, todo_value
from pythoscope.generator.dependencies import sorted_by_timestamp,\
    objects_affected_by_side_effects, older_than
from pythoscope.generator.namer import assign_names_to_objects

from pythoscope.serializer import BuiltinException, ImmutableObject, MapObject,\
    UnknownObject, SequenceObject, SerializedObject, is_serialized_string
from pythoscope.side_effect import SideEffect, BuiltinMethodWithPositionArgsSideEffect
from pythoscope.store import FunctionCall, UserObject, MethodCall,\
    GeneratorObject, GeneratorObjectInvocation, Call, CallToC
from pythoscope.util import assert_argument_type, counted, flatten, all_of_type


# :: GeneratorObject -> [SerializedObject]
def generator_object_yields(gobject):
    assert_argument_type(gobject, GeneratorObject)
    return [c.output for c in gobject.calls]

# :: Call -> [Event]
def assertions_for_call(call):
    return test_timeline_for_call(expand_into_timeline(call), call)

# :: Call -> CodeString
def generate_test_case(call, template):
    """This functions binds all other functions from this module together,
    implementing full test generation process, from the object to a test case
    string.

    Call -> assertions_for_call ->
      [Event] -> remove_objects_unworthy_of_naming ->
        [Event] -> name_objects_on_timeline ->
          [Event] -> generate_test_contents ->
            CodeString
    """
    return \
        generate_test_contents(
        name_objects_on_timeline(
            remove_objects_unworthy_of_naming(
                assertions_for_call(call))),
        template)

class AssertionLine(Event):
    def __init__(self, timestamp):
        # We don't call Event.__init__ on purpose, we set our own timestamp.
        self.timestamp = timestamp

class EqualAssertionLine(AssertionLine):
    def __init__(self, expected, actual, timestamp):
        AssertionLine.__init__(self, timestamp)
        self.expected = expected
        self.actual = actual

class GeneratorAssertionLine(AssertionLine):
    def __init__(self, generator_call, timestamp):
        AssertionLine.__init__(self, timestamp)
        self.generator_call = generator_call

class RaisesAssertionLine(AssertionLine):
    def __init__(self, expected_exception, call, timestamp):
        AssertionLine.__init__(self, timestamp)
        self.expected_exception = expected_exception
        self.call = call

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

# :: Call | GeneratorObject -> int
def last_call_action_timestamp(call):
    if isinstance(call, GeneratorObject):
        return max(map(last_call_action_timestamp, call.calls))
    if call.side_effects:
        return call.side_effects[-1].timestamp
    return call.timestamp

# :: ([Event], SerializedObject) -> [SideEffect]
def side_effects_that_affect_object(events, obj):
    "Filter out side effects that are irrelevant to given object."
    for side_effect in all_of_type(events, SideEffect):
        if obj in side_effect.affected_objects:
            yield side_effect

# :: [Event] -> [Event]
def without_calls(events):
    def not_call(event):
        return not isinstance(event, Call)
    return filter(not_call, events)

# :: ([Event], Call) -> [Event]
def test_timeline_for_call(execution_events, call):
    """Construct a new timeline for a test case based on real execution timeline
    and a call that needs to be tested.

    The new timeline in most cases will contain assertions.
    """
    events = older_than(without_calls(execution_events), call.timestamp)
    def copy_object_at(obj, timestamp):
        new_obj = event_copy(obj) # TODO use timestamp
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
    return events

# :: (Event, ...) -> [Event]
def expand_into_timeline(*events):
    return sorted_by_timestamp(set(enumerate_events(list(events))))

# :: [Event] -> [SerializedObject]
def objects_only(events):
    return all_of_type(events, SerializedObject)

# :: [Event] -> [Event]
def not_objects_only(events):
    return [e for e in events if not isinstance(e, SerializedObject)]

class Assign(Event):
    def __init__(self, name, obj, timestamp):
        self.name = name
        self.obj = obj
        # We don't call Event.__init__ on purpose, we set our own timestamp.
        self.timestamp = timestamp

# :: [Event] -> [Event]
def name_objects_on_timeline(events):
    names = {}
    assign_names_to_objects(objects_only(events), names)
    def map_object_to_assign(event):
        if isinstance(event, SerializedObject):
            return Assign(names[event], event, event.timestamp)
        return event
    return map(map_object_to_assign, events)

class Template(object):
    # :: (CodeString, CodeString) -> CodeString
    def equal_assertion(self, expected, actual):
        raise NotImplementedError("Method equal_assertion() not defined.")
    # :: (CodeString, CodeString) -> CodeString
    def raises_assertion(self, exception, call):
        raise NotImplementedError("Method raises_assertion() not defined.")

class UnittestTemplate(Template):
    def equal_assertion(self, expected, actual):
        return combine(expected, actual, "self.assertEqual(%s, %s)")
    def raises_assertion(self, exception, call):
        return combine(exception, call, "self.assertRaises(%s, %s)")

# :: CodeString -> CodeString
def add_newline(code_string):
    return combine(code_string, "\n")

# :: CodeString -> CodeString
def map_types(string):
    return putinto(string, "map(type, %s)")

# :: CodeString -> CodeString
def type_of(string):
    return putinto(string, "type(%s)")

# :: CodeString -> CodeString
def in_lambda(string):
    return putinto(string, "lambda: %s")

# :: (CodeString, CodeString, Template) -> CodeString
def equal_assertion_on_values_or_types(expected, actual, template):
    if expected.uncomplete:
        pass
    else:
        return template.equal_assertion(expected, actual)

def call_input(call):
    if isinstance(call, GeneratorObject):
        return call.args
    return call.input

def call_in_test(call, already_assigned_names):
    if isinstance(call, GeneratorObject):
        callstring = call_as_string_for(call.definition.name, call.args,
                                    call.definition, already_assigned_names)
        callstring = combine(callstring, str(len(call.calls)), template="list(islice(%s, %s))")
        callstring = addimport(callstring, ("itertools", "islice"))
    else:
        callstring = call_as_string_for(call.definition.name, call.input,
                                    call.definition, already_assigned_names)
        # TODO method calls should be different
        callstring = addimport(callstring, import_for(call.definition))
    return callstring

# :: ([Event], Template) -> CodeString
def generate_test_contents(events, template):
    contents = CodeString("")
    already_assigned_names = {}
    for event in events:
        if isinstance(event, Assign):
            constructor = constructor_as_string(event.obj, already_assigned_names)
            line = combine(event.name, constructor, "%s = %s")
            already_assigned_names[event.obj] = event.name
        elif isinstance(event, EqualAssertionLine):
            expected = constructor_as_string(event.expected, already_assigned_names)
            if isinstance(event.actual, Call):
                actual = call_in_test(event.actual, already_assigned_names)
            else:
                actual = constructor_as_string(event.actual, already_assigned_names)
            if expected.uncomplete:
                expected = type_as_string(event.expected)
                actual = type_of(actual)
                actual = addimport(actual, 'types')
            line = template.equal_assertion(expected, actual)
        elif isinstance(event, GeneratorAssertionLine):
            call = event.generator_call
            yields = generator_object_yields(call)
            expected = constructor_as_string(yields, already_assigned_names)
            actual = call_in_test(call, already_assigned_names)
            if expected.uncomplete:
                expected = type_as_string(yields)
                actual = map_types(actual)
                actual = addimport(actual, 'types')
            line = template.equal_assertion(expected, actual)
        elif isinstance(event, RaisesAssertionLine):
            actual = call_in_test(event.call, already_assigned_names)
            actual = in_lambda(actual)
            if is_serialized_string(event.expected_exception):
                exception = todo_value(event.expected_exception.reconstructor)
            else:
                exception = CodeString(event.expected_exception.type_name)
                exception = addimport(exception, event.expected_exception.type_import)
            line = template.raises_assertion(exception, actual)
        elif isinstance(event, BuiltinMethodWithPositionArgsSideEffect):
            # All objects affected by side effects are named.
            object_name = already_assigned_names[event.obj]
            line = call_as_string_for("%s.%s" % (object_name, event.definition.name),
                                      event.args_mapping(),
                                      event.definition,
                                      already_assigned_names)
        else:
            raise TypeError("Don't know how to generate test contents for event %r." % event)
        if line.uncomplete:
            line = combine("# ", line)
        contents = combine(contents, add_newline(line))
    return contents

# :: [Event] -> [Event]
def remove_objects_unworthy_of_naming(events):
    new_events = list(events)
    side_effects = all_of_type(events, SideEffect)
    affected_objects = objects_affected_by_side_effects(side_effects)
    objects_with_duplicates = objects_only(enumerate_events(not_objects_only(events)))
    objects_usage_counts = dict(counted(objects_with_duplicates))
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
        try:
            new_events.remove(obj)
        except ValueError:
            pass # If the element wasn't on the timeline, even better.
    return new_events

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
                ret += get_contained_events(obj.caller)
            return ret
        elif isinstance(obj, GeneratorObject):
            if obj.is_activated():
                return get_those_and_contained_events(obj.args.values()) +\
                    get_contained_events(obj.calls)
            else:
                return []
        elif isinstance(obj, SideEffect):
            return [obj] + get_those_and_contained_events(list(obj.affected_objects))
        elif isinstance(obj, EqualAssertionLine):
            objs = [obj.expected]
            if not isinstance(obj.actual, Call):
                objs.append(obj.actual)
            return objs + get_contained_events([obj.expected, obj.actual])
        elif isinstance(obj, GeneratorAssertionLine):
            return get_contained_events(obj.generator_call)
        elif isinstance(obj, RaisesAssertionLine):
            return [obj.expected_exception] + get_contained_events([obj.call, obj.expected_exception])
        elif isinstance(obj, CallToC):
            return get_contained_events(obj.caller)
        else:
            raise TypeError("Wrong argument to get_contained_events: %s." % repr(obj))
    return get_those_and_contained_events(objs)

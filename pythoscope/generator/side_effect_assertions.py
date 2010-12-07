from pythoscope.event import Event
from pythoscope.generator.assertions import assertions
from pythoscope.generator.lines import *
from pythoscope.generator.code_string import addimport, CodeString, combine,\
    putinto
from pythoscope.generator.constructor import constructor_as_string,\
    call_as_string_for, type_as_string, todo_value
from pythoscope.generator.method_call_context import MethodCallContext
from pythoscope.generator.dependencies import objects_affected_by_side_effects,\
    resolve_dependencies
from pythoscope.generator.namer import assign_names_to_objects

from pythoscope.serializer import BuiltinException, ImmutableObject, MapObject,\
    UnknownObject, SequenceObject, SerializedObject, is_serialized_string
from pythoscope.side_effect import SideEffect, BuiltinMethodWithPositionArgsSideEffect
from pythoscope.store import Function, FunctionCall, UserObject, MethodCall,\
    GeneratorObject, GeneratorObjectInvocation, Call, CallToC, Method
from pythoscope.util import assert_argument_type, compact, counted, flatten,\
    underscore, all_of_type


# :: Call | UserObject | Method | Function -> CodeString
def generate_test_case(testable_interaction, template):
    """This functions binds all other functions from this module together,
    implementing full test generation process, from an object to a test case
    string.

    Call|UserObject -> assertions ->
      [Event] -> remove_objects_unworthy_of_naming ->
        [Event] -> name_objects_on_timeline ->
          [Event] -> generate_test_contents ->
            CodeString
    """
    return \
        generate_test_contents(
            name_objects_on_timeline(
                remove_objects_unworthy_of_naming(
                    assertions(testable_interaction))),
            template)

# :: [Event] -> [Event]
def without_calls(events):
    def not_call(event):
        return not isinstance(event, Call)
    return filter(not_call, events)

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
    # :: () -> CodeString
    def skip_test(self):
        raise NotImplementedError("Method skip_test() not defined.")

class UnittestTemplate(Template):
    def equal_assertion(self, expected, actual):
        return combine(expected, actual, "self.assertEqual(%s, %s)")
    def raises_assertion(self, exception, call):
        return combine(exception, call, "self.assertRaises(%s, %s)")
    def skip_test(self):
        return CodeString("assert False # TODO: implement your test here")

class NoseTemplate(Template):
    def equal_assertion(self, expected, actual):
        return addimport(combine(expected, actual, "assert_equal(%s, %s)"),
                         ('nose.tools', 'assert_equal'))
    def raises_assertion(self, exception, call):
        return addimport(combine(exception, call, "assert_raises(%s, %s)"),
                         ('nose.tools', 'assert_raises'))
    def skip_test(self):
        return addimport(CodeString("raise SkipTest # TODO: implement your test here"),
                         ('nose', 'SkipTest'))

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

# :: Definition -> (str, str)
def import_for(definition):
    if isinstance(definition, Method):
        return import_for(definition.klass)
    return (definition.module.locator, definition.name)

# :: (CodeString, CodeString, Template) -> CodeString
def equal_assertion_on_values_or_types(expected, actual, template):
    if expected.uncomplete:
        pass
    else:
        return template.equal_assertion(expected, actual)

def call_name(call, assigned_names):
    if isinstance(call, MethodCallContext):
        if call.call.definition.is_creational():
            return call.call.definition.klass.name
        return "%s.%s" % (assigned_names[call.user_object], call.call.definition.name)
    return call.definition.name

def call_in_test(call, already_assigned_names):
    if isinstance(call, GeneratorObject) or (isinstance(call, MethodCallContext) and isinstance(call.call, GeneratorObject)):
        callstring = call_as_string_for(call_name(call, already_assigned_names), call.args,
                                        call.definition, already_assigned_names)
        callstring = combine(callstring, str(len(call.calls)), template="list(islice(%s, %s))")
        callstring = addimport(callstring, ("itertools", "islice"))
    else:
        callstring = call_as_string_for(call_name(call, already_assigned_names), call.input,
                                        call.definition, already_assigned_names)
        callstring = addimport(callstring, import_for(call.definition))
    return callstring

# :: GeneratorObject -> [SerializedObject]
def generator_object_yields(gobject):
    assert_argument_type(gobject, (GeneratorObject, MethodCallContext))
    return [c.output for c in gobject.calls]

# :: ([Event], Template) -> CodeString
def generate_test_contents(events, template):
    contents = CodeString("")
    all_uncomplete = False
    already_assigned_names = {}
    for event in events:
        if isinstance(event, Assign):
            constructor = constructor_as_string(event.obj, already_assigned_names)
            line = combine(event.name, constructor, "%s = %s")
            already_assigned_names[event.obj] = event.name
        elif isinstance(event, EqualAssertionLine):
            expected = constructor_as_string(event.expected, already_assigned_names)
            if isinstance(event.actual, (Call, MethodCallContext)):
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
        elif isinstance(event, CommentLine):
            line = CodeString(event.comment)
        elif isinstance(event, SkipTestLine):
            line = template.skip_test()
        elif isinstance(event, EqualAssertionStubLine):
            line = template.equal_assertion(CodeString('expected', uncomplete=True), event.actual)
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
            all_uncomplete = True
        if all_uncomplete and not isinstance(event, SkipTestLine):
            line = combine("# ", line)
        contents = combine(contents, add_newline(line))
    return contents

# :: [Event] -> [SerializedObject]
def objects_with_method_calls(events):
    def objects_from_methods(event):
        if isinstance(event, MethodCallContext):
            return event.user_object
        elif isinstance(event, EqualAssertionLine):
            return objects_from_methods(event.actual)
        elif isinstance(event, RaisesAssertionLine):
            return objects_from_methods(event.call)
        elif isinstance(event, GeneratorAssertionLine):
            return objects_from_methods(event.generator_call)
        else:
            return None
    return compact(map(objects_from_methods, events))

# :: [Event] -> [Event]
def remove_objects_unworthy_of_naming(events):
    new_events = list(events)
    side_effects = all_of_type(events, SideEffect)
    affected_objects = objects_affected_by_side_effects(side_effects)
    invoked_objects = objects_with_method_calls(events)
    for obj, usage_count in object_usage_counts(events):
        # ImmutableObjects don't need to be named, as their identity is
        # always unambiguous.
        if not isinstance(obj, ImmutableObject):
            # Anything mentioned more than once have to be named.
            if usage_count > 1:
                continue
            # Anything affected by side effects is also worth naming.
            if obj in affected_objects:
                continue
            # All user objects with method calls should also get names for
            # readability.
            if obj in invoked_objects:
                continue
        try:
            while True:
                new_events.remove(obj)
        except ValueError:
            pass # If the element wasn't on the timeline, even better.
    return new_events

# :: [Event] -> {SerializedObject: int}
def object_usage_counts(timeline):
    return counted(resolve_dependencies(timeline))

from pythoscope.generator.dependencies import objects_affected_by_side_effects,\
    resolve_dependencies
from pythoscope.generator.lines import *
from pythoscope.generator.method_call_context import MethodCallContext
from pythoscope.side_effect import SideEffect
from pythoscope.serializer import ImmutableObject
from pythoscope.util import all_of_type, compact, counted


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

# :: [Event] -> {SerializedObject: int}
def object_usage_counts(timeline):
    return counted(resolve_dependencies(timeline))

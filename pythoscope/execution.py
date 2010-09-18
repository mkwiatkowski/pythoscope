import itertools
import time
import types

from pythoscope.serializer import BuiltinException, ImmutableObject, MapObject,\
    UnknownObject, SequenceObject, is_immutable, is_sequence,\
    is_mapping, is_builtin_exception
from pythoscope.store import Call, Class, Function, FunctionCall,\
    GeneratorObject, GeneratorObjectInvocation, MethodCall, Project, UserObject
from pythoscope.timeline import Timeline
from pythoscope.util import all_of_type, assert_argument_type, class_name,\
    generator_has_ended, get_generator_from_frame, is_generator_code,\
    map_values, module_name


class Execution(object):
    """A single run of a user application.

    To start an execution context, simply create a new Execution() object.
        >>> e = Execution(Project("."))
        >>> e.ended is None
        True

    When you're done tracing, call the finalize() method. Objects protected
    from the garbage collector will be released and the execution context
    will be closed:
        >>> e.finalize()
        >>> e.ended is not None
        True

    To erase any information collected during this run, call the destroy()
    method:
        >>> e.destroy()

    In create_method_call/create_function_call if we can't find a class or
    function in Project, we don't care about it. This way we don't record any
    information about thid-party and dynamically created code.
    """
    def __init__(self, project):
        self.project = project

        self.started = time.time()
        self.ended = None

        self.timeline = Timeline()

        # References to objects and calls created during the run.
        self.captured_objects = {}
        self.captured_calls = []

        # After an inspection run, this will be a reference to the top level
        # call. Call graph can be traveresed by descending to `subcalls`
        # attribute of a call.
        self.call_graph = None

        # References to objects we don't want to be garbage collected just yet.
        self._preserved_objects = []

    def finalize(self):
        """Mark execution as finished.
        """
        self._preserved_objects = []
        self.ended = time.time()
        self._fix_generator_objects()

    def destroy(self):
        """Erase any serialized objects and references created during this run.
        """
        self.destroy_references()
        self.captured_objects = {}
        self.captured_calls = []
        self.call_graph = None

    def destroy_references(self):
        for obj in itertools.chain(self.captured_calls, self.captured_objects.values()):
            # Method calls will also be erased, implicitly during removal of
            # their UserObjects.
            if isinstance(obj, UserObject):
                obj.klass.user_objects.remove(obj)
            # FunctionCalls have to be removed from their definition classes.
            elif isinstance(obj, FunctionCall):
                obj.definition.calls.remove(obj)
            # GeneratorObjectInvocations will also be erased, implicitly
            # during removal of their GeneratObjects.
            elif isinstance(obj, GeneratorObject):
                # GeneratorObjects are registered as calls both in Functions
                # and in UserObjects. Since we remove UserObjects altogether
                # we only have to care about Functions here.
                if isinstance(obj.definition, Function):
                    obj.definition.calls.remove(obj)
            # Other serializables, like ImmutableObject are not referenced from
            # anywhere outside of calls in self.captured_calls.

    # :: object -> SerializedObject
    def serialize(self, obj):
        """Return description of the given object in the form of a subclass of
        SerializedObject.
        """
        return self._retrieve_or_capture(obj, self.create_serialized_object)

    # :: {str: object, ...} -> {str: SerializedObject, ...}
    def serialize_call_arguments(self, args):
        return map_values(self.serialize, args)

    # :: object -> UserObject | None
    def try_serializing_as_user_object(self, obj):
        """This method either find/creates a UserObject or returns None, without
        serializing the object to anything else.
        """
        sobject = self._retrieve_or_capture(obj, self.create_serialized_user_object)
        if isinstance(sobject, UserObject):
            return sobject

    # :: object -> UserObject | None
    def create_serialized_user_object(self, obj):
        klass = self.project.find_object(Class, class_name(obj), module_name(obj))
        if klass:
            serialized = UserObject(obj, klass)
            klass.add_user_object(serialized)
            return serialized

    # :: object -> SerializedObject
    def create_serialized_object(self, obj):
        # Generator object has been passed as a value. We don't have enough
        # information to create a complete GeneratorObject instance here, so
        # we create a stub to be activated later.
        if isinstance(obj, types.GeneratorType):
            return GeneratorObject(obj)
        user_object = self.create_serialized_user_object(obj)
        if user_object:
            return user_object
        elif is_immutable(obj):
            return ImmutableObject(obj)
        elif is_sequence(obj):
            return SequenceObject(obj, self.serialize)
        elif is_mapping(obj):
            return MapObject(obj, self.serialize)
        elif is_builtin_exception(obj):
            return BuiltinException(obj, self.serialize)
        else:
            return UnknownObject(obj)

    # :: (type, Definition, Callable, args, code, frame) -> Call
    def create_call(self, call_type, definition, callable, args, code, frame):
        sargs = self.serialize_call_arguments(args)
        if is_generator_code(code):
            generator = get_generator_from_frame(frame)
            # Each generator invocation is related to some generator object,
            # so we have to create one if it wasn't captured yet.
            def create_generator_object(_):
                gobject = GeneratorObject(generator, definition, sargs, callable)
                save_generator_inside(gobject, generator)
                return gobject
            gobject = self._retrieve_or_capture(generator, create_generator_object)
            # It may have been captured, but not necessarily invoked yet, so
            # we activate it if that's the case.
            if not gobject.is_activated():
                gobject.activate(definition, sargs, callable)
                save_generator_inside(gobject, generator)
            # In case of generators the call is really an invocation (resume) of
            # a specific generator object. Input arguments were already saved
            # in the GeneratorObject, and there's no need for duplicating them.
            call_type = GeneratorObjectInvocation
            callable = gobject
            sargs = {}
        call = call_type(definition, sargs)
        self.captured_calls.append(call)
        self.timeline.put(call)
        callable.add_call(call)
        return call

    # :: (str, object, dict, code, frame) -> MethodCall | None
    def create_method_call(self, name, obj, args, code, frame):
        user_object = self.try_serializing_as_user_object(obj)

        # We ignore the call if we can't find the class of this object.
        if user_object:
            method = user_object.klass.find_method_by_name(name)
            if method:
                return self.create_call(MethodCall, method, user_object, args, code, frame)
            else:
                # TODO: We're lacking a definition of a method in a known class,
                # so at least issue a warning.
                pass

    # :: (str, dict, code, frame) -> FunctionCall | None
    def create_function_call(self, name, args, code, frame):
        if self.project.contains_path(code.co_filename):
            modulename = self.project._extract_subpath(code.co_filename)
            function = self.project.find_object(Function, name, modulename)
            if function:
                return self.create_call(FunctionCall, function, function,
                                        args, code, frame)

    # :: (str, *object) -> SideEffect
    def create_side_effect(self, klass, *args):
        se = klass(*map(self.serialize, args))
        self.timeline.put(se)
        return se

    # :: (object, callable) -> SerializedObject | None
    def _retrieve_or_capture(self, obj, capture_callback):
        """Return existing description of the given object or create and return
        new one if the description wasn't captured yet.

        Preserves identity of objects, by storing them in `captured_objects`
        list.

        Returns None, when an obj wasn't serialized earlier and capture_callback
        returns None:
            >>> e = Execution(Project("."))
            >>> e._retrieve_or_capture(123, lambda x: None) is None
            True
            >>> e._preserved_objects
            []
        """
        try:
            return self.captured_objects[object_id(obj)]
        except KeyError:
            captured = capture_callback(obj)
            if captured:
                self._preserve(obj)
                self.timeline.put(captured)
                self.captured_objects[object_id(obj)] = captured
                return captured

    def _preserve(self, obj):
        """Preserve an object from garbage collection, so its id won't get
        occupied by any other object.
        """
        self._preserved_objects.append(obj)

    def iter_captured_generator_objects(self):
        return all_of_type(self.captured_objects.values(), GeneratorObject)

    def remove_call_from_call_graph(self, call_to_remove):
        assert_argument_type(call_to_remove, Call)
        def remove(calls):
            try:
                calls.remove(call_to_remove)
                return True
            except ValueError:
                for call in calls:
                    if remove(call.subcalls):
                        return True
        remove(self.call_graph)

    def _fix_generator_objects(self):
        """Remove last yielded values of generator objects, as those are
        just bogus Nones placed on generator stop.
        """
        for gobject in self.iter_captured_generator_objects():
            if is_exhaused_generator_object(gobject) \
                   and gobject.calls \
                   and gobject.calls[-1].output == ImmutableObject(None):
                removed_invocation = gobject.calls.pop()
                self.remove_call_from_call_graph(removed_invocation)
            # Once we know if the generator is active or not, we can discard it.
            if hasattr(gobject, '_generator'):
                del gobject._generator

def object_id(obj):
    return id(obj)

def save_generator_inside(gobject, generator):
    # Generator objects return None to the tracer when stopped. That
    # extra None we have to filter out manually (see
    # Execution._fix_generator_objects method). We distinguish between active
    # and stopped generators using the generator_has_ended() function.
    # It needs the generator object itself, so we save it for later
    # inspection inside the GeneratorObject.
    gobject._generator = generator

def is_exhaused_generator_object(gobject):
    return hasattr(gobject, '_generator') and generator_has_ended(gobject._generator)

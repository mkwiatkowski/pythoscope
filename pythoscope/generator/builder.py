from pythoscope.generator.lines import *
from pythoscope.generator.code_string import addimport, CodeString, combine,\
    putinto
from pythoscope.generator.constructor import constructor_as_string,\
    call_as_string_for, type_as_string, todo_value
from pythoscope.generator.method_call_context import MethodCallContext
from pythoscope.generator.objects_namer import Assign

from pythoscope.serializer import is_serialized_string
from pythoscope.side_effect import BuiltinMethodWithPositionArgsSideEffect
from pythoscope.store import GeneratorObject, Call, Method
from pythoscope.util import assert_argument_type


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
            elif isinstance(event.actual, VariableReference):
                actual = CodeString("%s.%s" % (event.actual.module, event.actual.name),
                                    imports=set([event.actual.module]))
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

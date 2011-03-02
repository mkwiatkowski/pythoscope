from pythoscope.serializer import SequenceObject, ImmutableObject
from pythoscope.store import Function, FunctionCall
from pythoscope.side_effect import SideEffect, ListAppend, GlobalRead,\
    GlobalRebind
from pythoscope.generator.assertions import assertions_for_interaction
from pythoscope.generator.objects_namer import name_objects_on_timeline, Assign
from pythoscope.generator.cleaner import remove_objects_unworthy_of_naming,\
    object_usage_counts
from pythoscope.generator.builder import generate_test_contents, UnittestTemplate
from pythoscope.generator.lines import Line, EqualAssertionLine, VariableReference
from pythoscope.generator import generate_test_case

from pythoscope.util import all_of_type

from assertions import *
from factories import create
from generator_helper import put_on_timeline, create_parent_call_with_side_effects


def assert_is_copy_of(obj, copy):
    assert copy is not obj,\
        "%r was supposed to be copy of object, but was the object instead" % copy
    for attr in dir(obj):
        if attr.startswith('_'):
            continue
        if attr == 'timestamp':
            assert_equal(obj.timestamp+0.5, copy.timestamp)
        else:
            assert_equal(getattr(obj, attr), getattr(copy, attr))

def assert_is_equal_assertion_line(assertion, expected, actual, expected_a_copy=False):
    assert_instance(assertion, EqualAssertionLine)
    if expected_a_copy:
        assert_is_copy_of(expected, assertion.expected)
    else:
        assert_equal(expected, assertion.expected)
    assert_equal(actual, assertion.actual)

class TestAssertionsForCall:
    def setUp(self):
        self.alist = create(SequenceObject)
        self.call = create(FunctionCall, args={}, output=self.alist)

    def test_returns_one_assertion_if_output_object_didnt_exist_before_the_call(self):
        put_on_timeline(self.call, self.alist)

        assertion_lines = all_of_type(assertions_for_interaction(self.call), Line)
        assertion = assert_one_element_and_return(assertion_lines)
        assert_is_equal_assertion_line(assertion, expected_a_copy=True,
                                       expected=self.call.output,
                                       actual=self.call)
        assert assertion.timestamp > self.call.timestamp

    def test_returns_two_assertions_if_output_object_existed_before_the_call(self):
        put_on_timeline(self.alist, self.call)

        assertion_lines = all_of_type(assertions_for_interaction(self.call), Line)
        assert_length(assertion_lines, 2)

        assert_is_equal_assertion_line(assertion_lines[0],
                                       expected=self.call.output, actual=self.call)
        assert_is_equal_assertion_line(assertion_lines[1], expected_a_copy=True,
                                       expected=self.call.output, actual=self.call.output)
        assert assertion_lines[0].timestamp < assertion_lines[1].timestamp

    def test_assertion_gets_timestamp_075_higher_than_the_last_call_action(self):
        se = SideEffect([self.alist], [])
        self.call.add_side_effect(se)
        put_on_timeline(self.call, self.alist, se)

        assertion_lines = all_of_type(assertions_for_interaction(self.call), Line)
        assertion = assert_one_element_and_return(assertion_lines)
        assert_equal(se.timestamp+0.75, assertion.timestamp)

    def test_object_copy_includes_its_side_effects(self):
        se = SideEffect([self.alist], [])
        self.call.add_side_effect(se)
        put_on_timeline(self.alist, se, self.call)

        timeline = assertions_for_interaction(self.call)

        alists = all_of_type(timeline, SequenceObject)
        assert_length(alists, 2)
        assert alists[0] is not alists[1]

        side_effects = all_of_type(timeline, SideEffect)
        side_effect = assert_one_element_and_return(side_effects)
        assert alists[1] in side_effect.affected_objects

def assert_timeline_length_and_return_elements(timeline, expected_length, indexes):
    assert_length(timeline, expected_length)
    ret = []
    for idx in indexes:
        ret.append(timeline[idx])
    return ret

def assert_assignment(event, expected_name, expected_object):
    assert_instance(event, Assign)
    assert_equal(expected_name, event.name)
    assert_equal(expected_object, event.obj)

def assert_assignment_with_variable_reference(event, expected_name, expected_var_module, expected_var_name):
    assert_instance(event, Assign)
    assert_equal(expected_name, event.name)
    assert_variable_reference(event.obj, expected_var_module, expected_var_name)

class TestSideEffectSetupTeardownAndAssertions:
    def test_creates_setup_and_teardown_for_global_read_side_effect(self):
        call = create(FunctionCall, args={})
        old_value = ImmutableObject('old_value')
        se = GlobalRead('mod', 'var', old_value)
        call.add_side_effect(se)
        put_on_timeline(se, call, call.output)

        timeline = assertions_for_interaction(call)
        setup_1, setup_2, teardown = assert_timeline_length_and_return_elements(timeline, 6, [0, 1, 4])
        assert_assignment_with_variable_reference(setup_1, 'old_mod_var', 'mod', 'var')
        assert_assignment(setup_2, 'mod.var', old_value)
        assert_assignment(teardown, 'mod.var', 'old_mod_var')

    def test_names_globals_from_submodules_properly(self):
        call = create(FunctionCall, args={})
        old_value = ImmutableObject('old_value')
        se = GlobalRead('mod.submod', 'var', old_value)
        call.add_side_effect(se)
        put_on_timeline(se, call, call.output)

        timeline = assertions_for_interaction(call)
        setup_1, setup_2, teardown = assert_timeline_length_and_return_elements(timeline, 6, [0, 1, 4])
        assert_assignment_with_variable_reference(setup_1, 'old_mod_submod_var', 'mod.submod', 'var')
        assert_assignment(setup_2, 'mod.submod.var', old_value)
        assert_assignment(teardown, 'mod.submod.var', 'old_mod_submod_var')

    def test_creates_setup_and_teardown_for_two_different_global_read_side_effects(self):
        call = create(FunctionCall, args={})
        old_value = ImmutableObject('old_value')
        se = GlobalRead('mod', 'var', old_value)
        se2 = GlobalRead('mod', 'other_var', old_value)
        call.add_side_effect(se)
        call.add_side_effect(se2)
        put_on_timeline(se, se2, call, call.output)

        timeline = assertions_for_interaction(call)
        varSetup1, varSetup2, varTeardown = assert_timeline_length_and_return_elements(timeline, 9, [2, 3, 6])
        assert_assignment_with_variable_reference(varSetup1, 'old_mod_var', 'mod', 'var')
        assert_assignment(varSetup2, 'mod.var', old_value)
        assert_assignment(varTeardown, 'mod.var', 'old_mod_var')

        otherVarSetup1, otherVarSetup2, otherVarTeardown = assert_timeline_length_and_return_elements(timeline, 9, [0, 1, 7])
        assert_assignment_with_variable_reference(otherVarSetup1, 'old_mod_other_var', 'mod', 'other_var')
        assert_assignment(otherVarSetup2, 'mod.other_var', old_value)
        assert_assignment(otherVarTeardown, 'mod.other_var', 'old_mod_other_var')

    def test_creates_only_one_setup_and_teardown_for_multiple_global_read_side_effects_of_the_same_variable(self):
        call = create(FunctionCall, args={})
        old_value = ImmutableObject('old_value')
        se = GlobalRead('mod', 'var', old_value)
        se2 = GlobalRead('mod', 'var', old_value)
        call.add_side_effect(se)
        call.add_side_effect(se2)
        put_on_timeline(se, se2, call, call.output)

        timeline = assertions_for_interaction(call)
        setup_1, setup_2, teardown = assert_timeline_length_and_return_elements(timeline, 6, [0, 1, 4])
        assert_assignment_with_variable_reference(setup_1, 'old_mod_var', 'mod', 'var')
        assert_assignment(setup_2, 'mod.var', old_value)
        assert_assignment(teardown, 'mod.var', 'old_mod_var')

    def test_creates_assertion_for_global_rebind_side_effect(self):
        call = create(FunctionCall, args={})
        new_value = ImmutableObject('new_value')
        se = GlobalRebind('mod', 'var', new_value)
        call.add_side_effect(se)
        put_on_timeline(se, call, call.output)

        timeline = assertions_for_interaction(call)
        assert_length(timeline, 4)
        rebind_assertion = timeline[2]
        assert_equal(new_value, rebind_assertion.expected)
        assert_variable_reference(rebind_assertion.actual, 'mod', 'var')

def assert_variable_reference(ref, expected_module, expected_name):
    assert_instance(ref, VariableReference)
    assert_equal(expected_module, ref.module)
    assert_equal(expected_name, ref.name)

class TestObjectUsageCounts:
    def setUp(self):
        self.alist = create(SequenceObject)
        self.call = create(FunctionCall, args={'x': self.alist},
                      definition=create(Function, args=['x']))
        self.aline = EqualAssertionLine(self.alist, self.call, 0)

    def test_returns_objects_in_assertion_sorted_by_timestamp(self):
        put_on_timeline(self.alist, self.call, self.aline)

        assert_equal([(self.alist, 2)], object_usage_counts(self.aline))

    def test_includes_relevant_side_effects_in_the_output(self):
        se = SideEffect([self.alist], [])
        create_parent_call_with_side_effects(self.call, [se])
        put_on_timeline(self.alist, se, self.call, self.aline)

        assert_equal([(self.alist, 2)], object_usage_counts(self.aline))

    def test_doesnt_include_relevant_objects_affected_by_side_effects_in_the_output(self):
        alist2 = create(SequenceObject)
        se = SideEffect([self.alist, alist2], [])
        create_parent_call_with_side_effects(self.call, [se])
        put_on_timeline(self.alist, alist2, se, self.call, self.aline)

        assert_equal([(self.alist, 2)], object_usage_counts(self.aline))

class TestRemoveObjectsUnworthyOfNaming:
    def test_keeps_objects_used_more_than_once(self):
        alist = create(SequenceObject)
        call = create(FunctionCall, args={'x': alist, 'y': alist},
                      definition=create(Function, args=['x', 'y']))
        put_on_timeline(alist, call)
        assert_equal([alist, call], remove_objects_unworthy_of_naming([alist, call]))

    def test_removes_objects_used_only_once(self):
        alist = create(SequenceObject)
        call = create(FunctionCall, args={'x': alist})
        put_on_timeline(alist, call)
        assert_equal([call], remove_objects_unworthy_of_naming([alist, call]))

    def test_removes_all_immutable_objects(self):
        obj = create(ImmutableObject)
        call = create(FunctionCall, args={'x': obj}, output=obj,
                      definition=create(Function, args=['x']))
        put_on_timeline(obj, call)
        assert_equal([call], remove_objects_unworthy_of_naming([obj, call]))

    def test_keeps_objects_affected_by_side_effects(self):
        output = create(SequenceObject)
        seq = create(SequenceObject, obj=[1])
        call = create(FunctionCall, output=output)
        se = SideEffect([output, seq], [])

        put_on_timeline(seq, se, output, call)

        assert_equal([seq, se, output, call],
                     remove_objects_unworthy_of_naming([seq, se, output, call]))

    def test_removes_objects_only_referenced_by_side_effects(self):
        seq = create(SequenceObject, obj=[1])
        output = create(SequenceObject)
        se = SideEffect([output], [seq])
        call = create(FunctionCall, args={'x': seq}, output=output,
                      definition=create(Function, args=['x']))

        put_on_timeline(seq, output, se, call)

        assert_equal([output, se, call],
                     remove_objects_unworthy_of_naming([seq, output, se, call]))

class TestNameObjectsOnTimeline:
    def test_names_objects_appropriatelly(self):
        obj = create(SequenceObject)
        call = create(FunctionCall, args={'x': obj}, output=obj,
                      definition=create(Function, args=['x']))
        obj2 = create(SequenceObject)
        put_on_timeline(obj, call, obj2)

        timeline = name_objects_on_timeline([obj, call, obj2])
        assert_assignment(timeline[0], 'alist1', obj)
        assert_equal(call, timeline[1])
        assert_assignment(timeline[2], 'alist2', obj2)

unittest_template = UnittestTemplate()

class TestGenerateTestContents:
    def test_generates_assignment_line_with_object(self):
        assign = Assign('foo', create(SequenceObject), 1)
        assert_equal_strings("foo = []\n",
                             generate_test_contents([assign], None))

    def test_generates_assignment_line_with_name(self):
        assign = Assign('foo', 'bar', 1)
        assert_equal_strings("foo = bar\n",
                             generate_test_contents([assign], None))

    def test_generates_assignment_line_with_variable_reference(self):
        assign = Assign('foo', VariableReference('mod', 'var', 0), 1)
        assert_equal_strings("foo = mod.var\n",
                             generate_test_contents([assign], None))

    def test_generates_assertion_line(self):
        aline = EqualAssertionLine(create(SequenceObject), create(FunctionCall), 1)
        assert_equal_strings("self.assertEqual([], function())\n",
                             generate_test_contents([aline], unittest_template))

    def test_adds_import_for_an_assertion_line(self):
        aline = EqualAssertionLine(create(SequenceObject), create(FunctionCall), 1)
        assert_equal(set([('module', 'function')]),
                     generate_test_contents([aline], unittest_template).imports)

    def test_generates_side_effect_line(self):
        alist = create(SequenceObject)
        assign = Assign('alist', alist, 1)
        se = ListAppend(alist, create(ImmutableObject, obj=1))
        assert_equal_strings("alist = []\nalist.append(1)\n",
                             generate_test_contents([assign, se], None))

    def test_generates_line_with_variable_reference(self):
        line = EqualAssertionLine(ImmutableObject('string'),
            VariableReference('mod', 'var', 1.5), 2)
        result = generate_test_contents([line], unittest_template)
        assert_equal_strings("self.assertEqual('string', mod.var)\n", result)
        assert_equal(set(['mod']), result.imports)

class TestGenerateTestCase:
    def test_generates_full_test_case_for_a_call(self):
        alist = create(SequenceObject)
        call = create(FunctionCall, args={}, output=alist)
        put_on_timeline(call, alist)
        code_string = generate_test_case(call, template=unittest_template)
        assert_equal_strings("self.assertEqual([], function())\n", code_string)
        assert_equal(set([('module', 'function')]), code_string.imports)

    def test_generates_full_test_case_for_a_call_with_side_effects_and_two_assertions_required(self):
        alist = create(SequenceObject)
        call = create(FunctionCall, args={'x': alist}, output=alist,
                      definition=create(Function, args=['x']))
        se = ListAppend(alist, create(ImmutableObject, obj=1))
        call.add_side_effect(se)
        put_on_timeline(alist, call, se)

        assert_equal_strings("alist1 = []\n"
                             "alist2 = []\n"
                             "self.assertEqual(alist1, function(alist1))\n"
                             "alist2.append(1)\n"
                             "self.assertEqual(alist2, alist1)\n",
                             generate_test_case(call, template=unittest_template))

from pythoscope.serializer import SequenceObject
from pythoscope.store import Function, FunctionCall
from pythoscope.side_effect import SideEffect
from pythoscope.generator.side_effect_assertions import assertions_for_call,\
    EqualAssertionLine, expand_into_timeline

from assertions import *
from factories import create
from generator_helper import put_on_timeline


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

        assertion = assert_one_element_and_return(assertions_for_call(self.call))
        assert_is_equal_assertion_line(assertion, expected_a_copy=True,
                                       expected=self.call.output,
                                       actual=self.call)
        assert assertion.timestamp > self.call.timestamp

    def test_returns_two_assertions_if_output_object_existed_before_the_call(self):
        put_on_timeline(self.alist, self.call)

        assertions = assertions_for_call(self.call)
        assert_length(assertions, 2)

        assert_is_equal_assertion_line(assertions[0],
                                       expected=self.call.output, actual=self.call)
        assert_is_equal_assertion_line(assertions[1], expected_a_copy=True,
                                       expected=self.call.output, actual=self.call.output)
        assert assertions[0].timestamp < assertions[1].timestamp

    def test_assertion_gets_timestamp_half_higher_than_the_last_call_action(self):
        se = SideEffect([self.alist], [])
        self.call.add_side_effect(se)
        put_on_timeline(self.call, self.alist, se)

        assertion = assert_one_element_and_return(assertions_for_call(self.call))
        assert_equal(se.timestamp+0.5, assertion.timestamp)

class TestExpandIntoTimeline:
    def setUp(self):
        self.alist = create(SequenceObject)
        self.call = create(FunctionCall, args={}, output=self.alist)
        self.aline = EqualAssertionLine(self.alist, self.call, 0)

    def test_returns_objects_in_assertion_sorted_by_timestamp(self):
        put_on_timeline(self.alist, self.call, self.aline)

        assert_equal([self.alist, self.aline], expand_into_timeline(self.aline))

    def test_includes_relevant_side_effects_in_the_output(self):
        se = SideEffect([self.alist], [])
        self.call.add_side_effect(se)
        put_on_timeline(self.alist, self.call, se, self.aline)

        assert_equal([self.alist, se, self.aline], expand_into_timeline(self.aline))

    def test_includes_relevant_objects_affected_by_side_effects_in_the_output(self):
        alist2 = create(SequenceObject)
        se = SideEffect([self.alist, alist2], [])
        self.call.add_side_effect(se)
        put_on_timeline(self.alist, alist2, self.call, se, self.aline)

        assert_equal([self.alist, alist2, se, self.aline], expand_into_timeline(self.aline))

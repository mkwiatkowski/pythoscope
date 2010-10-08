from pythoscope.serializer import SequenceObject
from pythoscope.store import Function, FunctionCall
from pythoscope.generator.side_effect_assertions import assertions_for_call,\
    EqualAssertionLine

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
        self.function = create(Function, args=[])
        self.alist = create(SequenceObject)
        self.call = create(FunctionCall, args={}, output=self.alist, definition=self.function)

    def test_returns_one_assertion_if_output_object_didnt_exist_before_the_call(self):
        put_on_timeline(self.call, self.alist)

        assertion = assert_one_element_and_return(assertions_for_call(self.call))
        assert_is_equal_assertion_line(assertion, expected_a_copy=True,
                                       expected=self.call.output,
                                       actual=self.call)

    def test_returns_two_assertions_if_output_object_existed_before_the_call(self):
        put_on_timeline(self.alist, self.call)

        assertions = assertions_for_call(self.call)
        assert_length(assertions, 2)

        assert_is_equal_assertion_line(assertions[0],
                                       expected=self.call.output, actual=self.call)
        assert_is_equal_assertion_line(assertions[1], expected_a_copy=True,
                                       expected=self.call.output, actual=self.call.output)

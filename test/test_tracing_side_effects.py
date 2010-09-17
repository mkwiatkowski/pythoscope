from pythoscope.side_effect import ListAppend

from assertions import *
from inspector_assertions import *
from inspector_helper import *


class TestMutation:
    def test_handles_list_append(self):
        def fun():
            def foo(x):
                x.append(1)
            foo([])
        call = inspect_returning_single_call(fun)
        se = assert_one_element_and_return(call.side_effects)
        assert isinstance(se, ListAppend)
        assert_serialized([], se.alist)
        assert_serialized(1, se.element)

from nose.tools import assert_equal
from helper import assert_length

import pythoscope

new_style_class = """
class AClass(object):
    def amethod(self):
        pass
"""

stand_alone_function = """
def a_function():
    pass
"""

class TestCollector:
    def test_collects_information_about_top_level_classes(self):
        info = pythoscope.collect_information(new_style_class)

        assert_length(info.classes, 1)
        assert_equal("AClass", info.classes[0].name)

    def test_collects_information_about_top_level_functions(self):
        info = pythoscope.collect_information(stand_alone_function)

        assert_length(info.functions, 1)
        assert_equal("a_function", info.functions[0].name)

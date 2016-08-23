import unittest


class TestSimpleClass(unittest.TestCase):
    def test_method_with_one_arg(self):
        # simple_class = SimpleClass()
        # self.assertEqual(expected, simple_class.method_with_one_arg(argument))
        assert False  # TODO: implement your test here

    def test_simple_method(self):
        # simple_class = SimpleClass()
        # self.assertEqual(expected, simple_class.simple_method())
        assert False  # TODO: implement your test here

class TestClassWithInit(unittest.TestCase):
    def test___init__(self):
        # class_with_init = ClassWithInit()
        assert False  # TODO: implement your test here

    def test_method(self):
        # class_with_init = ClassWithInit()
        # self.assertEqual(expected, class_with_init.method(arg))
        assert False  # TODO: implement your test here

class TestOldStyleClass(unittest.TestCase):
    def test_m(self):
        # old_style_class = OldStyleClass()
        # self.assertEqual(expected, old_style_class.m())
        assert False  # TODO: implement your test here

class TestSubclassOfEmpty(unittest.TestCase):
    def test_new_method(self):
        # subclass_of_empty = SubclassOfEmpty()
        # self.assertEqual(expected, subclass_of_empty.new_method())
        assert False  # TODO: implement your test here

class TestStandAloneFunction(unittest.TestCase):
    def test_stand_alone_function(self):
        # self.assertEqual(expected, stand_alone_function(arg1, arg2))
        assert False  # TODO: implement your test here

class TestTopLevelClass(unittest.TestCase):
    def test_method(self):
        # top_level_class = TopLevelClass()
        # self.assertEqual(expected, top_level_class.method())
        assert False  # TODO: implement your test here

if __name__ == '__main__':
    unittest.main()

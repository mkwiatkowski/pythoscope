import unittest

class TestSomeClass(unittest.TestCase):
    def test___init__(self):
        assert True # implemented test case

    def test_some_method(self):
        assert True # implemented test case

    def test_new_method(self):
        # some_class = SomeClass()
        # self.assertEqual(expected, some_class.new_method())
        assert False  # TODO: implement your test here

if __name__ == '__main__':
    unittest.main()

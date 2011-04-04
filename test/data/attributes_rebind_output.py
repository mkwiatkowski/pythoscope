from module import OldStyle
import unittest
from module import NewStyle
from module import UsingOther
from module import main

class TestOldStyle(unittest.TestCase):
    def test_setx_returns_None_for_42(self):
        old_style = OldStyle()
        self.assertEqual(None, old_style.setx(42))
        self.assertEqual(42, old_style.x)

class TestNewStyle(unittest.TestCase):
    def test_incrx_2_times_after_creation_with_13(self):
        new_style = NewStyle(13)
        self.assertEqual(None, new_style.incrx())
        self.assertEqual(14, new_style.x)
        self.assertEqual(None, new_style.incrx())
        self.assertEqual(15, new_style.x)

    def test_incrx_returns_None_after_creation_with_3(self):
        new_style = NewStyle(3)
        self.assertEqual(None, new_style.incrx())
        self.assertEqual(4, new_style.x)

class TestUsingOther(unittest.TestCase):
    def test_create_and_process(self):
        using_other = UsingOther()
        result = using_other.create()
        new_style = NewStyle(13)
        result.x = 13
        result.x = 14
        self.assertEqual(new_style, result)
        self.assertEqual(None, using_other.process(result))

class TestMain(unittest.TestCase):
    def test_main_returns_None(self):
        self.assertEqual(None, main())

if __name__ == '__main__':
    unittest.main()

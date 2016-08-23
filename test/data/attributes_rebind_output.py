from module import OldStyle
import unittest
from module import NewStyle
from module import UsingOther
from module import UsingOtherInternally
from module import main


class TestOldStyle(unittest.TestCase):
    def test_setx_returns_None_for_42(self):
        old_style = OldStyle()
        self.assertEqual(None, old_style.setx(42))
        self.assertEqual(42, old_style.x)

class TestNewStyle(unittest.TestCase):
    def test_creation_with_100(self):
        new_style = NewStyle(100)
        # Make sure it doesn't raise any exceptions.

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

class TestUsingOtherInternally(unittest.TestCase):
    def test_use_returns_None(self):
        using_other_internally = UsingOtherInternally()
        self.assertEqual(None, using_other_internally.use())
        self.assertEqual(211, using_other_internally.internal.x)
        self.assertEqual('private', using_other_internally.internal._y)

class TestMain(unittest.TestCase):
    def test_main_returns_None(self):
        self.assertEqual(None, main())

if __name__ == '__main__':
    unittest.main()

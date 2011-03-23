from module import OldStyle
import unittest
from module import NewStyle
from module import main

class TestOldStyle(unittest.TestCase):
    def test_setx_returns_None_for_42(self):
        old_style = OldStyle()
        self.assertEqual(None, old_style.setx(42))
        self.assertEqual(42, old_style.x)

class TestNewStyle(unittest.TestCase):
    def test_incrx_returns_None_after_creation_with_3(self):
        new_style = NewStyle(3)
        self.assertEqual(None, new_style.incrx())
        self.assertEqual(4, new_style.x)

class TestMain(unittest.TestCase):
    def test_main_returns_None(self):
        self.assertEqual(None, main())

if __name__ == '__main__':
    unittest.main()

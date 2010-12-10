from module import main
import unittest
import module

class TestMain(unittest.TestCase):
    def test_main_returns_1(self):
        self.assertEqual(1, main())
        self.assertEqual(2, module.var)

if __name__ == '__main__':
    unittest.main()

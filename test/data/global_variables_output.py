from module import main
import unittest
import module


class TestMain(unittest.TestCase):
    def test_main_returns_1(self):
        old_module_var = module.var
        module.var = 1
        self.assertEqual(module.var, main())
        self.assertEqual(2, module.var)
        module.var = old_module_var

if __name__ == '__main__':
    unittest.main()

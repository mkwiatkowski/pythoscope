from module import before
import unittest
from module import after
from module import main


class TestBefore(unittest.TestCase):
    def test_before_returns_list(self):
        alist = [1]
        alist.extend([3, 2])
        alist.insert(0, 4)
        alist.pop()
        alist.remove(3)
        alist.sort()
        self.assertEqual(alist, before())

class TestAfter(unittest.TestCase):
    def test_after_returns_alist_for_alist_equal_list(self):
        alist1 = []
        alist2 = []
        alist1.append(1)
        alist2.append(1)
        alist1.extend([3, 2])
        alist2.extend([3, 2])
        alist1.insert(0, 4)
        alist2.insert(0, 4)
        alist1.pop()
        alist2.pop()
        alist1.remove(3)
        alist2.remove(3)
        alist1.sort()
        alist2.sort()
        alist2.reverse()
        self.assertEqual(alist1, after(alist1))
        self.assertEqual(alist2, alist1)

class TestMain(unittest.TestCase):
    def test_main_returns_None(self):
        self.assertEqual(None, main())

if __name__ == '__main__':
    unittest.main()
